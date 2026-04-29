# © Todos os direitos reservados – github.com/Wbad-02
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_admin, requer_mestre, get_usuario_atual, hash_senha, verificar_senha, registrar_log
import models, schemas

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])

# ── Rotas /me DEVEM vir antes de /{usuario_id} ──────────────
# FastAPI resolve rotas em ordem de registro. Se /{usuario_id}
# vier primeiro, "me" é interpretado como ID inteiro → erro 422.

@router.get("/me", response_model=schemas.UsuarioOut)
def meu_perfil(atual: models.Usuario = Depends(get_usuario_atual)):
    return atual


@router.put("/me/perfil", response_model=schemas.UsuarioOut)
def atualizar_meu_perfil(
    payload: schemas.AtualizarPerfil,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(get_usuario_atual),
):
    atual.nome = payload.nome.strip()
    db.commit(); db.refresh(atual)
    registrar_log(db, atual.id, "editar_perfil", "usuario", atual.id)
    return atual


@router.put("/me/senha", status_code=204)
def alterar_minha_senha(
    payload: schemas.AlterarSenhaPropria,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(get_usuario_atual),
):
    if not verificar_senha(payload.senha_atual, atual.senha_hash):
        raise HTTPException(401, "Senha atual incorreta")
    atual.senha_hash = hash_senha(payload.nova_senha)
    db.commit()
    registrar_log(db, atual.id, "alterar_senha", "usuario", atual.id, "própria senha")


# ── Rotas administrativas (/  e  /{id}) ──────────────────────

@router.get("/", response_model=list[schemas.UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    q = db.query(models.Usuario).order_by(models.Usuario.nome)
    # Mestre é invisível para não-mestres
    if atual.grupo != models.GrupoPermissao.mestre:
        q = q.filter(models.Usuario.grupo != models.GrupoPermissao.mestre)
    return q.all()


@router.post("/", response_model=schemas.UsuarioOut, status_code=201)
def criar_usuario(
    payload: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    # Admin não pode criar mestre nem outro admin; só mestre pode
    if payload.grupo == models.GrupoPermissao.mestre:
        raise HTTPException(403, "Não é permitido criar usuário com perfil mestre")
    if payload.grupo == models.GrupoPermissao.admin and atual.grupo != models.GrupoPermissao.mestre:
        raise HTTPException(403, "Somente o mestre pode criar usuários admin")

    if db.query(models.Usuario).filter(models.Usuario.email == payload.email).first():
        raise HTTPException(409, "E-mail já cadastrado")
    usuario = models.Usuario(
        nome=payload.nome, email=payload.email,
        senha_hash=hash_senha(payload.senha), grupo=payload.grupo,
    )
    db.add(usuario); db.commit(); db.refresh(usuario)
    registrar_log(db, atual.id, "criar", "usuario", usuario.id, f"email={payload.email}")
    return usuario


@router.put("/{usuario_id}/senha", status_code=204)
def alterar_senha_admin(
    usuario_id: int,
    payload: schemas.AlterarSenhaAdmin,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    """Admin redefine senha de usuário; mestre pode redefinir qualquer um."""
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(404, "Usuário não encontrado")
    # Admin não pode alterar senha de admin ou mestre (só mestre pode)
    if usuario.grupo in (models.GrupoPermissao.admin, models.GrupoPermissao.mestre):
        if atual.grupo != models.GrupoPermissao.mestre:
            raise HTTPException(403, "Somente o mestre pode alterar senha de administradores")
    usuario.senha_hash = hash_senha(payload.nova_senha)
    db.commit()
    registrar_log(db, atual.id, "alterar_senha", "usuario", usuario_id, "via admin")


@router.put("/{usuario_id}", response_model=schemas.UsuarioOut)
def atualizar_usuario(
    usuario_id: int,
    payload: schemas.UsuarioUpdate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(404, "Usuário não encontrado")
    # Admin não pode editar admin/mestre (só mestre pode)
    if usuario.grupo in (models.GrupoPermissao.admin, models.GrupoPermissao.mestre):
        if atual.grupo != models.GrupoPermissao.mestre:
            raise HTTPException(403, "Somente o mestre pode editar administradores")
    # Admin não pode promover alguém a admin ou mestre (só mestre pode)
    if payload.grupo in (models.GrupoPermissao.admin, models.GrupoPermissao.mestre):
        if atual.grupo != models.GrupoPermissao.mestre:
            raise HTTPException(403, "Somente o mestre pode atribuir o perfil admin ou mestre")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(usuario, campo, valor)
    db.commit(); db.refresh(usuario)
    registrar_log(db, atual.id, "editar", "usuario", usuario_id)
    return usuario


@router.delete("/{usuario_id}", status_code=204)
def desativar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    if usuario_id == atual.id:
        raise HTTPException(400, "Você não pode se desativar")
    usuario = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(404, "Usuário não encontrado")
    # Admin não pode desativar admin/mestre (só mestre pode)
    if usuario.grupo in (models.GrupoPermissao.admin, models.GrupoPermissao.mestre):
        if atual.grupo != models.GrupoPermissao.mestre:
            raise HTTPException(403, "Somente o mestre pode desativar administradores")
    usuario.ativo = False
    db.commit()
    registrar_log(db, atual.id, "desativar", "usuario", usuario_id)
