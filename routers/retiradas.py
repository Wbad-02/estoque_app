# © Todos os direitos reservados – github.com/Wbad-02
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, selectinload
from database import get_db
from auth import get_usuario_atual
import models, schemas

router = APIRouter(prefix="/api/retiradas", tags=["retiradas"])


@router.get("/", response_model=list[schemas.MovimentacaoOut])
def listar_retiradas(
    material_id: int | None = Query(None),
    motivo:      str | None = Query(None),
    skip:        int        = Query(0, ge=0),
    limit:       int        = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    q = (
        db.query(models.Movimentacao)
        .options(
            selectinload(models.Movimentacao.material)
            .selectinload(models.Material.grupo)
            .selectinload(models.GrupoMaterial.categoria),
            selectinload(models.Movimentacao.usuario),
        )
        .filter(models.Movimentacao.tipo == "saida")
        .order_by(models.Movimentacao.criado_em.desc())
    )
    if material_id:
        q = q.filter(models.Movimentacao.material_id == material_id)
    if motivo:
        q = q.filter(models.Movimentacao.motivo == motivo)

    rows = q.offset(skip).limit(limit).all()
    resultado = []
    for r in rows:
        out = schemas.MovimentacaoOut.model_validate(r)
        out.nome_material  = r.material.nome if r.material else ""
        out.nome_usuario   = r.usuario.nome  if r.usuario  else "Sistema"
        out.grupo_nome     = r.material.grupo.nome           if r.material and r.material.grupo else ""
        out.categoria_nome = r.material.grupo.categoria.nome if r.material and r.material.grupo and r.material.grupo.categoria else ""
        resultado.append(out)
    return resultado
