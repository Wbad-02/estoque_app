# © Todos os direitos reservados – github.com/Wbad-02
"""
Módulo de autenticação e autorização.

Segurança aplicada:
  - Senhas com bcrypt (cost factor 12 — mais lento para brute-force)
  - JWT com expiração de 8h e algoritmo HS256
  - Chave secreta carregada de variável de ambiente (com fallback seguro)
  - Tokens inválidos ou expirados retornam 401 sem revelar o motivo exato
  - Logs de auditoria para toda ação sensível
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
import models

# ── Chave secreta ─────────────────────────────────────────────
# Em produção: defina a variável de ambiente ESTOQUE_SECRET_KEY
# com um valor aleatório de pelo menos 32 caracteres.
# Geração: python -c "import secrets; print(secrets.token_hex(32))"
_SECRET_ENV = os.environ.get("ESTOQUE_SECRET_KEY", "")
if not _SECRET_ENV or len(_SECRET_ENV) < 32:
    # Gera uma chave aleatória a cada reinício se não configurada.
    # Isso invalida todos os tokens ao reiniciar o servidor — aceitável
    # em ambiente de desenvolvimento, mas defina a variável em produção.
    _SECRET_ENV = secrets.token_hex(32)
    print("⚠️  ESTOQUE_SECRET_KEY não definida. Tokens são invalidados ao reiniciar.")
    print(f"   Defina no sistema: ESTOQUE_SECRET_KEY={_SECRET_ENV}")

SECRET_KEY              = _SECRET_ENV
ALGORITHM               = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

# bcrypt com cost factor 12 — mais resistente a brute-force
pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verificar_senha(senha: str, hash_: str) -> bool:
    return pwd_context.verify(senha, hash_)


def criar_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    expire  = datetime.utcnow() + (
        expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    payload.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_usuario_atual(
    token: str = Depends(oauth2_scheme),
    db:    Session = Depends(get_db),
) -> models.Usuario:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sessão inválida ou expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload     = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id  = payload.get("sub")
        if usuario_id is None:
            raise exc
    except JWTError:
        raise exc

    usuario = db.query(models.Usuario).filter(
        models.Usuario.id   == int(usuario_id),
        models.Usuario.ativo == True,
    ).first()

    if not usuario:
        raise exc
    return usuario


def requer_admin(usuario: models.Usuario = Depends(get_usuario_atual)):
    if usuario.grupo not in (models.GrupoPermissao.admin, models.GrupoPermissao.mestre):
        raise HTTPException(status_code=403, detail="Acesso restrito: requer perfil admin")
    return usuario


def requer_mestre(usuario: models.Usuario = Depends(get_usuario_atual)):
    if usuario.grupo != models.GrupoPermissao.mestre:
        raise HTTPException(status_code=403, detail="Acesso restrito: requer perfil mestre")
    return usuario


def requer_editor_ou_admin(usuario: models.Usuario = Depends(get_usuario_atual)):
    if usuario.grupo == models.GrupoPermissao.viewer:
        raise HTTPException(status_code=403, detail="Acesso restrito: requer perfil editor ou admin")
    return usuario


def registrar_log(
    db:         Session,
    usuario_id: Optional[int],
    acao:       str,
    entidade:   str,
    entidade_id: Optional[int] = None,
    detalhe:    Optional[str]  = None,
):
    log = models.LogAuditoria(
        usuario_id  = usuario_id,
        acao        = acao,
        entidade    = entidade,
        entidade_id = entidade_id,
        detalhe     = detalhe,
    )
    db.add(log)
    db.commit()
