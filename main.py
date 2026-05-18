# © Todos os direitos reservados – github.com/Wbad-02
import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import engine, get_db, Base
from auth import verificar_senha, criar_token, hash_senha, registrar_log, get_usuario_atual
from middleware_seguranca import MiddlewareSeguranca, REDES_PERMITIDAS, WHITELIST_IP_ATIVA
from routers import usuarios, categorias, materiais, relatorios, grupos, importacao, retiradas, patrimonio, ativos, ativos_categorias, notificacoes, motivos, requerimentos, solicitacoes
import models, schemas

APP_VERSION = "3.3.0"

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sistema de Controle de Estoque",
    version=APP_VERSION,
    docs_url=None,       # desabilita /docs em producao
    redoc_url=None,      # desabilita /redoc em producao
    openapi_url=None,    # desabilita /openapi.json em producao
)

# CORS_ORIGINS: dominios permitidos separados por virgula.
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

# ── Middleware de seguranca principal (IP whitelist + rate limit + headers) ──
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
app.include_router(requerimentos.router)
app.include_router(solicitacoes.router)


@app.post("/api/auth/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(
        models.Usuario.email == payload.email,
        models.Usuario.ativo == True,
    ).first()
    if not usuario or not verificar_senha(payload.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha invalidos")
    token = criar_token({"sub": str(usuario.id)})
    registrar_log(db, usuario.id, "login", "usuario", usuario.id)
    return schemas.TokenResponse(
        access_token=token, grupo=usuario.grupo.value, nome=usuario.nome, email=usuario.email,
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


def _seed_templates_requerimento(db: Session):
    """Garante que existam templates de e-mail para requerimentos."""
    defaults = [
        {
            "tipo":    "requerimento",
            "assunto": "Novo requerimento de compra: {titulo}",
            "corpo": (
                "Um novo requerimento de compra foi criado.\n\n"
                "Titulo:     {titulo}\n"
                "Criado por: {criador}\n"
                "Itens:      {itens_count}\n"
                "Total:      {total}\n\n"
                "Acesse para aprovar ou rejeitar: {link}"
            ),
        },
        {
            "tipo":    "requerimento_decisao",
            "assunto": "Requerimento '{titulo}' foi {status}",
            "corpo": (
                "O requerimento de compra abaixo teve uma decisao registrada.\n\n"
                "Titulo:      {titulo}\n"
                "Status:      {status}\n"
                "Decisao por: {aprovador}\n"
                "Observacao:  {observacao}"
            ),
        },
        {
            "tipo":    "solicitacao",
            "assunto": "Nova solicitação de estoque: {material}",
            "corpo": (
                "Uma nova solicitação de material foi aberta e aguarda aprovação.\n\n"
                "Material:      {material}\n"
                "Quantidade:    {quantidade}\n"
                "Solicitante:   {criador}\n"
                "Motivo:        {motivo}\n"
                "Ativo destino: {ativo}\n"
                "Data:          {data}\n\n"
                "Acesse para aprovar ou rejeitar: {link}"
            ),
        },
        {
            "tipo":    "solicitacao_decisao",
            "assunto": "Solicitação de '{material}' foi {status}",
            "corpo": (
                "Sua solicitação de material teve uma decisão registrada.\n\n"
                "Material:     {material}\n"
                "Quantidade:   {quantidade}\n"
                "Status:       {status}\n"
                "Decidido por: {decididor}\n"
                "Observação:   {observacao}"
            ),
        },
    ]
    for d in defaults:
        existe = db.query(models.NotificacaoTemplate).filter(
            models.NotificacaoTemplate.tipo == d["tipo"]
        ).first()
        if not existe:
            db.add(models.NotificacaoTemplate(**d))
    db.commit()


def _checar_senha_padrao(db: Session):
    admin = db.query(models.Usuario).filter(
        models.Usuario.email == "admin@estoque.local"
    ).first()
    if admin and verificar_senha("admin123", admin.senha_hash):
        print("=" * 60)
        print("AVISO CRITICO: Admin ainda usa a senha padrao 'admin123'.")
        print("Troque imediatamente apos o primeiro login!")
        print("=" * 60)


@app.on_event("startup")
def startup():
    db = next(get_db())
    try:
        _seed_admin(db)
        _checar_senha_padrao(db)
        _seed_templates_requerimento(db)
    finally:
        db.close()
    if WHITELIST_IP_ATIVA:
        print(f"Redes autorizadas: {', '.join(REDES_PERMITIDAS)}")
    else:
        print("Whitelist de IP desativada — acesso liberado para qualquer origem (modo internet)")
    print(f"CORS origins: {_cors_origins}")
    print("Rate limit: 60 req/min geral | 10 tentativas/5min no login")
    print("Security headers HTTP ativos")


@app.get("/api/poll")
def poll_estado(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    """Endpoint leve para polling de mudanças. Retorna o timestamp máximo de cada entidade
    e a versão do app — o frontend recarrega apenas a seção afetada quando algo muda."""
    def max_ts(col):
        r = db.query(func.max(col)).scalar()
        return r.isoformat() if r else ""

    return {
        "versao":        APP_VERSION,
        "materiais":     max_ts(models.Material.atualizado_em),
        "movimentacoes": max_ts(models.Movimentacao.criado_em),
        "requerimentos": max_ts(models.Requerimento.atualizado_em),
        "ativos":        max_ts(models.AtivoItem.atribuido_em),
        "solicitacoes":  max_ts(models.SolicitacaoEstoque.atualizado_em),
    }


app.mount("/", StaticFiles(directory="static", html=True), name="static")
