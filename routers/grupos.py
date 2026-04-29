# © Todos os direitos reservados – github.com/Wbad-02
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_editor_ou_admin, get_usuario_atual, registrar_log
import models, schemas

router = APIRouter(prefix="/api/grupos", tags=["grupos"])


@router.get("/", response_model=list[schemas.GrupoOut])
def listar_grupos(
    categoria_id: int | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    q = db.query(models.GrupoMaterial)
    if categoria_id:
        q = q.filter(models.GrupoMaterial.categoria_id == categoria_id)
    return q.order_by(models.GrupoMaterial.nome).all()


@router.post("/", response_model=schemas.GrupoOut, status_code=201)
def criar_grupo(
    payload: schemas.GrupoCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    cat = db.query(models.Categoria).filter(models.Categoria.id == payload.categoria_id).first()
    if not cat:
        raise HTTPException(404, "Categoria não encontrada")

    duplicado = db.query(models.GrupoMaterial).filter(
        models.GrupoMaterial.nome == payload.nome,
        models.GrupoMaterial.categoria_id == payload.categoria_id,
    ).first()
    if duplicado:
        raise HTTPException(409, "Grupo já existe nesta categoria")

    grupo = models.GrupoMaterial(**payload.model_dump())
    db.add(grupo)
    db.commit()
    db.refresh(grupo)
    registrar_log(db, atual.id, "criar", "grupo", grupo.id, payload.nome)
    return grupo


@router.put("/{grupo_id}", response_model=schemas.GrupoOut)
def atualizar_grupo(
    grupo_id: int,
    payload: schemas.GrupoUpdate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    grupo = db.query(models.GrupoMaterial).filter(models.GrupoMaterial.id == grupo_id).first()
    if not grupo:
        raise HTTPException(404, "Grupo não encontrado")

    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(grupo, campo, valor)

    db.commit()
    db.refresh(grupo)
    registrar_log(db, atual.id, "editar", "grupo", grupo_id)
    return grupo


@router.delete("/{grupo_id}", status_code=204)
def remover_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    grupo = db.query(models.GrupoMaterial).filter(models.GrupoMaterial.id == grupo_id).first()
    if not grupo:
        raise HTTPException(404, "Grupo não encontrado")

    tem_materiais = db.query(models.Material).filter(
        models.Material.grupo_id == grupo_id,
        models.Material.ativo == True,
    ).first()
    if tem_materiais:
        raise HTTPException(409, "Grupo possui materiais ativos. Remova-os primeiro.")

    # Remover materiais inativos que ainda referenciam este grupo
    db.query(models.Material).filter(
        models.Material.grupo_id == grupo_id,
        models.Material.ativo == False,
    ).delete(synchronize_session=False)

    db.delete(grupo)
    db.commit()
    registrar_log(db, atual.id, "remover", "grupo", grupo_id)
