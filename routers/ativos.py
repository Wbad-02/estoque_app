# © Todos os direitos reservados – github.com/Wbad-02
from models import agora
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_editor_ou_admin, get_usuario_atual, registrar_log
from utils import sync_qty
import models, schemas

router = APIRouter(prefix="/api/ativos", tags=["ativos"])


def _ativo_out(a: models.Ativo) -> schemas.AtivoOut:
    data = schemas.AtivoOut.model_validate(a)
    data.itens_ativos = sum(1 for i in a.itens if i.devolvido_em is None)
    return data


def _item_out(i: models.AtivoItem) -> schemas.AtivoItemOut:
    out = schemas.AtivoItemOut.model_validate(i)
    if i.material:
        out.nome_material  = i.material.nome
        out.unidade        = i.material.unidade
        out.categoria_nome = i.material.grupo.categoria.nome if i.material.grupo else ""
        out.grupo_nome     = i.material.grupo.nome if i.material.grupo else ""
    if i.unidade_patr:
        out.unidade_codigo = i.unidade_patr.codigo
    return out


# ── CRUD Ativos ───────────────────────────────────────

@router.get("/", response_model=list[schemas.AtivoOut])
def listar(grupo_id: int | None = Query(None), db: Session = Depends(get_db),
           _=Depends(get_usuario_atual)):
    q = db.query(models.Ativo).filter(models.Ativo.ativo == True)
    if grupo_id:
        q = q.filter(models.Ativo.grupo_id == grupo_id)
    return [_ativo_out(a) for a in q.order_by(models.Ativo.nome).all()]


@router.get("/inativos", response_model=list[schemas.AtivoOut])
def listar_inativos(grupo_id: int | None = Query(None), db: Session = Depends(get_db),
                    _=Depends(get_usuario_atual)):
    q = db.query(models.Ativo).filter(models.Ativo.ativo == False)
    if grupo_id:
        q = q.filter(models.Ativo.grupo_id == grupo_id)
    return [_ativo_out(a) for a in q.order_by(models.Ativo.nome).all()]


@router.post("/", response_model=schemas.AtivoOut, status_code=201)
def criar(payload: schemas.AtivoCreate, db: Session = Depends(get_db),
          atual=Depends(requer_editor_ou_admin)):
    grupo = db.query(models.AtivoGrupo).filter(
        models.AtivoGrupo.id == payload.grupo_id
    ).first()
    if not grupo: raise HTTPException(404, "Grupo não encontrado")
    obj = models.Ativo(**payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    registrar_log(db, atual.id, "criar", "ativo", obj.id, payload.nome)
    return _ativo_out(obj)


@router.put("/{ativo_id}", response_model=schemas.AtivoOut)
def atualizar(ativo_id: int, payload: schemas.AtivoUpdate,
              db: Session = Depends(get_db), atual=Depends(requer_editor_ou_admin)):
    obj = db.query(models.Ativo).filter(models.Ativo.id == ativo_id).first()
    if not obj: raise HTTPException(404, "Ativo não encontrado")
    for k, v in payload.model_dump(exclude_none=True).items(): setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return _ativo_out(obj)


@router.post("/{ativo_id}/reativar", response_model=schemas.AtivoOut)
def reativar(ativo_id: int, db: Session = Depends(get_db),
             atual=Depends(requer_editor_ou_admin)):
    obj = db.query(models.Ativo).filter(
        models.Ativo.id == ativo_id, models.Ativo.ativo == False
    ).first()
    if not obj: raise HTTPException(404, "Ativo inativo não encontrado")
    obj.ativo = True
    db.commit()
    db.refresh(obj)
    registrar_log(db, atual.id, "reativar", "ativo", ativo_id, obj.nome)
    return _ativo_out(obj)


@router.delete("/{ativo_id}", status_code=204)
def remover(ativo_id: int, db: Session = Depends(get_db),
            atual=Depends(requer_editor_ou_admin)):
    obj = db.query(models.Ativo).filter(
        models.Ativo.id == ativo_id, models.Ativo.ativo == True
    ).first()
    if not obj: raise HTTPException(404, "Ativo não encontrado")

    # Retornar ao estoque todos os materiais ainda atribuídos
    mats_afetados = set()
    for item in obj.itens:
        if item.devolvido_em is None:
            if item.unidade_id:
                unidade = db.query(models.UnidadePatrimonio).filter(
                    models.UnidadePatrimonio.id == item.unidade_id
                ).first()
                if unidade:
                    unidade.tag = "usado"
            item.devolvido_em = agora()
            mats_afetados.add(item.material_id)

    db.flush()
    for mat_id in mats_afetados:
        mat = db.query(models.Material).filter(models.Material.id == mat_id).first()
        if mat:
            sync_qty(mat, db)

    obj.ativo = False
    db.commit()
    registrar_log(db, atual.id, "inativar", "ativo", ativo_id, obj.nome)


# ── Itens do Ativo ────────────────────────────────────

@router.get("/{ativo_id}/itens", response_model=list[schemas.AtivoItemOut])
def listar_itens(ativo_id: int, db: Session = Depends(get_db),
                 _=Depends(get_usuario_atual)):
    ativo = db.query(models.Ativo).filter(models.Ativo.id == ativo_id).first()
    if not ativo: raise HTTPException(404, "Ativo não encontrado")
    return [_item_out(i) for i in ativo.itens if i.devolvido_em is None]


@router.post("/{ativo_id}/atribuir", response_model=schemas.AtivoItemOut)
def atribuir_material(ativo_id: int, payload: schemas.AtribuirMaterialCreate,
                      db: Session = Depends(get_db),
                      atual=Depends(requer_editor_ou_admin)):
    ativo = db.query(models.Ativo).filter(
        models.Ativo.id == ativo_id, models.Ativo.ativo == True
    ).first()
    if not ativo: raise HTTPException(404, "Ativo não encontrado")

    mat = db.query(models.Material).filter(
        models.Material.id == payload.material_id, models.Material.ativo == True
    ).first()
    if not mat: raise HTTPException(404, "Material não encontrado")

    unidade = db.query(models.UnidadePatrimonio).filter(
        models.UnidadePatrimonio.id == payload.unidade_id,
        models.UnidadePatrimonio.material_id == payload.material_id,
    ).first()
    if not unidade:
        raise HTTPException(404, "Unidade não encontrada")
    if unidade.tag == "atribuido":
        raise HTTPException(400, "Unidade já está atribuída a outro ativo")
    if unidade.status != models.StatusUnidade.ativo:
        raise HTTPException(400, "Unidade não está disponível (já retirada do estoque)")

    unidade.tag = "atribuido"
    db.flush()
    sync_qty(mat, db)

    item = models.AtivoItem(
        ativo_id=ativo_id,
        material_id=payload.material_id,
        unidade_id=payload.unidade_id,
        quantidade=1,
        observacao=payload.observacao,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    registrar_log(db, atual.id, "atribuir", "ativo_item", item.id,
                  f"{mat.nome} → {ativo.nome}")
    return _item_out(item)


@router.post("/{ativo_id}/devolver/{item_id}")
def devolver_material(ativo_id: int, item_id: int,
                      db: Session = Depends(get_db),
                      atual=Depends(requer_editor_ou_admin)):
    item = db.query(models.AtivoItem).filter(
        models.AtivoItem.id == item_id,
        models.AtivoItem.ativo_id == ativo_id,
        models.AtivoItem.devolvido_em == None,
    ).first()
    if not item: raise HTTPException(404, "Item não encontrado ou já devolvido")

    mat = db.query(models.Material).filter(
        models.Material.id == item.material_id
    ).first()
    if item.unidade_id:
        unidade = db.query(models.UnidadePatrimonio).filter(
            models.UnidadePatrimonio.id == item.unidade_id
        ).first()
        if unidade:
            unidade.tag = "usado"

    item.devolvido_em = agora()
    db.flush()
    if mat:
        sync_qty(mat, db)
    db.commit()
    registrar_log(db, atual.id, "devolver", "ativo_item", item_id,
                  mat.nome if mat else "")
    return {"ok": True, "quantidade": item.quantidade,
            "material": mat.nome if mat else ""}
