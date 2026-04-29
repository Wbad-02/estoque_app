# © Todos os direitos reservados – github.com/Wbad-02
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_editor_ou_admin, get_usuario_atual
import models, schemas

router = APIRouter(prefix="/api/ativos-categorias", tags=["ativos-categorias"])


# ── Categorias ────────────────────────────────────────

@router.get("/", response_model=list[schemas.AtivoCategoriaOut])
def listar(db: Session = Depends(get_db), _=Depends(get_usuario_atual)):
    return db.query(models.AtivoCategoria).order_by(models.AtivoCategoria.nome).all()


@router.post("/", response_model=schemas.AtivoCategoriaOut, status_code=201)
def criar(payload: schemas.AtivoCategoriaCreate, db: Session = Depends(get_db),
          _=Depends(requer_editor_ou_admin)):
    if db.query(models.AtivoCategoria).filter(
        models.AtivoCategoria.nome == payload.nome
    ).first():
        raise HTTPException(400, "Já existe uma categoria com este nome")
    obj = models.AtivoCategoria(**payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


@router.put("/{cat_id}", response_model=schemas.AtivoCategoriaOut)
def atualizar(cat_id: int, payload: schemas.AtivoCategoriaUpdate,
              db: Session = Depends(get_db), _=Depends(requer_editor_ou_admin)):
    obj = db.query(models.AtivoCategoria).filter(models.AtivoCategoria.id == cat_id).first()
    if not obj: raise HTTPException(404, "Categoria não encontrada")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj


@router.delete("/{cat_id}", status_code=204)
def remover(cat_id: int, db: Session = Depends(get_db), _=Depends(requer_editor_ou_admin)):
    obj = db.query(models.AtivoCategoria).filter(models.AtivoCategoria.id == cat_id).first()
    if not obj: raise HTTPException(404, "Categoria não encontrada")
    db.delete(obj); db.commit()


# ── Grupos ────────────────────────────────────────────

@router.get("/grupos/", response_model=list[schemas.AtivoGrupoOut])
def listar_grupos(categoria_id: int | None = Query(None),
                  db: Session = Depends(get_db), _=Depends(get_usuario_atual)):
    q = db.query(models.AtivoGrupo)
    if categoria_id:
        q = q.filter(models.AtivoGrupo.categoria_id == categoria_id)
    return q.order_by(models.AtivoGrupo.nome).all()


@router.post("/grupos/", response_model=schemas.AtivoGrupoOut, status_code=201)
def criar_grupo(payload: schemas.AtivoGrupoCreate, db: Session = Depends(get_db),
                _=Depends(requer_editor_ou_admin)):
    cat = db.query(models.AtivoCategoria).filter(
        models.AtivoCategoria.id == payload.categoria_id
    ).first()
    if not cat: raise HTTPException(404, "Categoria não encontrada")
    obj = models.AtivoGrupo(**payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return obj


@router.put("/grupos/{grp_id}", response_model=schemas.AtivoGrupoOut)
def atualizar_grupo(grp_id: int, payload: schemas.AtivoGrupoUpdate,
                    db: Session = Depends(get_db), _=Depends(requer_editor_ou_admin)):
    obj = db.query(models.AtivoGrupo).filter(models.AtivoGrupo.id == grp_id).first()
    if not obj: raise HTTPException(404, "Grupo não encontrado")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return obj


@router.delete("/grupos/{grp_id}", status_code=204)
def remover_grupo(grp_id: int, db: Session = Depends(get_db),
                  _=Depends(requer_editor_ou_admin)):
    obj = db.query(models.AtivoGrupo).filter(models.AtivoGrupo.id == grp_id).first()
    if not obj: raise HTTPException(404, "Grupo não encontrado")
    db.delete(obj); db.commit()
