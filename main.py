# © Todos os direitos reservados – github.com/Wbad-02
import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, get_db, Base
from auth import verificar_senha, criar_token, hash_senha, registrar_log
from middleware_seguranca import MiddlewareSeguranca, REDES_PERMITIDAS, WHITELIST_IP_ATIVA
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

# CORS_ORIGINS: domínios permitidos separados por vírgula.
# Ex: https://meudominio.trycloudflare.com
# Deixe vazio para permitir qualquer origem (menos seguro).
_cors_env = os.environ.get("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
        _checar_senha_padrao(db)
    finally:
        db.close()
    if WHITELIST_IP_ATIVA:
        print(f"Redes autorizadas: {', '.join(REDES_PERMITIDAS)}")
    else:
        print("Whitelist de IP desativada — acesso liberado para qualquer origem (modo internet)")
    print(f"CORS origins: {_cors_origins}")
    print("Rate limit: 60 req/min geral | 10 tentativas/5min no login")
    print("Security headers HTTP ativos")


def _checar_senha_padrao(db: Session):
    admin = db.query(models.Usuario).filter(
        models.Usuario.email == "admin@estoque.local"
    ).first()
    if admin and verificar_senha("admin123", admin.senha_hash):
        print("=" * 60)
        print("AVISO CRITICO: Admin ainda usa a senha padrao 'admin123'.")
        print("Troque imediatamente apos o primeiro login!")
        print("=" * 60)


app.mount("/", StaticFiles(directory="static", html=True), name="static")
