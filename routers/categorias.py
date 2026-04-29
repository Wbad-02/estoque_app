# © Todos os direitos reservados – github.com/Wbad-02
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_editor_ou_admin, get_usuario_atual, registrar_log
import models, schemas

router = APIRouter(prefix="/api/categorias", tags=["categorias"])


@router.get("/", response_model=list[schemas.CategoriaOut])
def listar_categorias(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    return db.query(models.Categoria).order_by(models.Categoria.nome).all()


@router.post("/", response_model=schemas.CategoriaOut, status_code=201)
def criar_categoria(
    payload: schemas.CategoriaCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    if db.query(models.Categoria).filter(models.Categoria.nome == payload.nome).first():
        raise HTTPException(409, "Categoria já existe")
    cat = models.Categoria(**payload.model_dump())
    db.add(cat); db.commit(); db.refresh(cat)
    registrar_log(db, atual.id, "criar", "categoria", cat.id, payload.nome)
    return cat


@router.put("/{cat_id}", response_model=schemas.CategoriaOut)
def atualizar_categoria(
    cat_id: int,
    payload: schemas.CategoriaUpdate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    cat = db.query(models.Categoria).filter(models.Categoria.id == cat_id).first()
    if not cat:
        raise HTTPException(404, "Categoria não encontrada")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(cat, campo, valor)
    db.commit(); db.refresh(cat)
    registrar_log(db, atual.id, "editar", "categoria", cat_id)
    return cat


@router.delete("/{cat_id}", status_code=204)
def remover_categoria(
    cat_id: int,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    cat = db.query(models.Categoria).filter(models.Categoria.id == cat_id).first()
    if not cat:
        raise HTTPException(404, "Categoria não encontrada")

    # Verificar materiais ATIVOS vinculados via grupo (Material não tem mais categoria_id direto)
    tem_ativos = (
        db.query(models.Material)
        .join(models.GrupoMaterial, models.Material.grupo_id == models.GrupoMaterial.id)
        .filter(
            models.GrupoMaterial.categoria_id == cat_id,
            models.Material.ativo == True,
        )
        .first()
    )
    if tem_ativos:
        raise HTTPException(
            409,
            "Categoria possui materiais ativos. Remova os materiais antes de apagar a categoria.",
        )

    # Limpar materiais inativos dos grupos desta categoria antes de deletar
    grupos_ids = [
        g.id for g in db.query(models.GrupoMaterial)
        .filter(models.GrupoMaterial.categoria_id == cat_id).all()
    ]
    if grupos_ids:
        db.query(models.Material).filter(
            models.Material.grupo_id.in_(grupos_ids),
            models.Material.ativo == False,
        ).delete(synchronize_session=False)

    db.delete(cat)
    db.commit()
    registrar_log(db, atual.id, "remover", "categoria", cat_id)
