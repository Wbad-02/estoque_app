# © Todos os direitos reservados – github.com/Wbad-02
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, get_db, Base
from auth import verificar_senha, criar_token, hash_senha, registrar_log
from middleware_seguranca import MiddlewareSeguranca, REDES_PERMITIDAS
from routers import usuarios, categorias, materiais, relatorios, grupos, importacao, retiradas, patrimonio, ativos, ativos_categorias, notificacoes, motivos
import models, schemas

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sistema de Controle de Estoque",
    version="3.1.0",
    docs_url=None,       # desabilita /docs em produção
    redoc_url=None,      # desabilita /redoc em produção
    openapi_url=None,    # desabilita /openapi.json em produção
)

# ── Segurança: CORS restrito à rede interna ───────────────────
# Permite apenas origens da própria máquina.
# Em rede local os clientes acessam pelo IP do servidor — o CORS
# aqui bloqueia tentativas de sites externos fazerem chamadas à API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # wildcard necessário pois clientes usam IPs diferentes
    allow_credentials=True,
    allow_methods=["GET","POST","PUT","PATCH","DELETE"],
    allow_headers=["Authorization","Content-Type"],
    max_age=600,
)

# ── Middleware de segurança principal (IP whitelist + rate limit + headers) ──
app.add_middleware(MiddlewareSeguranca)

# ── Routers ───────────────────────────────────────────────────
app.include_router(usuarios.router)
app.include_router(categorias.router)
app.include_router(grupos.router)
app.include_router(materiais.router)
app.include_router(retiradas.router)
app.include_router(relatorios.router)
app.include_router(importacao.router)
app.include_router(patrimonio.router)
app.include_router(ativos_categorias.router)
app.include_router(ativos.router)
app.include_router(notificacoes.router)
app.include_router(motivos.router)


@app.post("/api/auth/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(
        models.Usuario.email == payload.email,
        models.Usuario.ativo == True,
    ).first()
    if not usuario or not verificar_senha(payload.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
    token = criar_token({"sub": str(usuario.id)})
    registrar_log(db, usuario.id, "login", "usuario", usuario.id)
    return schemas.TokenResponse(
        access_token=token, grupo=usuario.grupo.value, nome=usuario.nome,
    )


def _seed_admin(db: Session):
    if not db.query(models.Usuario).filter(
        models.Usuario.email == "admin@estoque.local"
    ).first():
        db.add(models.Usuario(
            nome="Administrador", email="admin@estoque.local",
            senha_hash=hash_senha("admin123"),
            grupo=models.GrupoPermissao.admin,
        ))
        db.commit()
        print("Admin criado  ->  admin@estoque.local / admin123")
        print("AVISO: Troque a senha apos o primeiro login!")


@app.on_event("startup")
def startup():
    db = next(get_db())
    try:
        _seed_admin(db)
    finally:
        db.close()
    print(f"Redes autorizadas: {', '.join(REDES_PERMITIDAS)}")
    print("Rate limit: 60 req/min geral | 10 tentativas/5min no login")
    print("Security headers HTTP ativos")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
