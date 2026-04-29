# © Todos os direitos reservados – github.com/Wbad-02
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_editor_ou_admin, get_usuario_atual, registrar_log
import models, schemas

router = APIRouter(prefix="/api/motivos", tags=["motivos"])

_MOTIVOS_PADRAO = [
    {"id": 0, "nome": "colaborador", "label": "Atribuído a colaborador"},
    {"id": 0, "nome": "defeito",     "label": "Defeito / Ruim"},
]


@router.get("/")
def listar_motivos(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    """Retorna motivos padrão + customizados ativos."""
    customizados = db.query(models.MotivoPersonalizado).filter(
        models.MotivoPersonalizado.ativo == True
    ).order_by(models.MotivoPersonalizado.nome).all()

    return {
        "padrao": _MOTIVOS_PADRAO,
        "customizados": [{"id": m.id, "nome": m.nome} for m in customizados],
    }


@router.post("/", response_model=schemas.MotivoPersonalizadoOut, status_code=201)
def criar_motivo(
    payload: schemas.MotivoPersonalizadoCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    existente = db.query(models.MotivoPersonalizado).filter(
        models.MotivoPersonalizado.nome == payload.nome,
        models.MotivoPersonalizado.ativo == True,
    ).first()
    if existente:
        raise HTTPException(409, "Motivo já cadastrado")

    motivo = models.MotivoPersonalizado(nome=payload.nome)
    db.add(motivo)
    db.commit()
    db.refresh(motivo)
    registrar_log(db, atual.id, "criar", "motivo_personalizado", motivo.id, payload.nome)
    return motivo


@router.delete("/{motivo_id}", status_code=204)
def remover_motivo(
    motivo_id: int,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    motivo = db.query(models.MotivoPersonalizado).filter(
        models.MotivoPersonalizado.id == motivo_id,
        models.MotivoPersonalizado.ativo == True,
    ).first()
    if not motivo:
        raise HTTPException(404, "Motivo não encontrado")
    motivo.ativo = False
    db.commit()
    registrar_log(db, atual.id, "remover", "motivo_personalizado", motivo_id)
