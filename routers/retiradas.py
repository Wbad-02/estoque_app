# © Todos os direitos reservados – github.com/Wbad-02
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_editor_ou_admin, get_usuario_atual, registrar_log
from email_service import disparar_notificacao
import models, schemas

router = APIRouter(prefix="/api/retiradas", tags=["retiradas"])


@router.get("/", response_model=list[schemas.MovimentacaoOut])
def listar_retiradas(
    material_id: int | None = Query(None),
    motivo:      str | None = Query(None),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    q = (
        db.query(models.Movimentacao)
        .filter(models.Movimentacao.tipo == "saida")
        .order_by(models.Movimentacao.criado_em.desc())
    )
    if material_id:
        q = q.filter(models.Movimentacao.material_id == material_id)
    if motivo:
        q = q.filter(models.Movimentacao.motivo == motivo)

    rows = q.all()
    resultado = []
    for r in rows:
        out = schemas.MovimentacaoOut.model_validate(r)
        out.nome_material  = r.material.nome if r.material else ""
        out.nome_usuario   = r.usuario.nome  if r.usuario  else "Sistema"
        out.grupo_nome     = r.material.grupo.nome              if r.material and r.material.grupo else ""
        out.categoria_nome = r.material.grupo.categoria.nome    if r.material and r.material.grupo and r.material.grupo.categoria else ""
        resultado.append(out)
    return resultado


@router.post("/", response_model=schemas.MovimentacaoOut, status_code=201)
def registrar_retirada(
    payload: schemas.RetiradaCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    material = db.query(models.Material).filter(
        models.Material.id   == payload.material_id,
        models.Material.ativo == True,
    ).first()
    if not material:
        raise HTTPException(404, "Material não encontrado")

    if payload.quantidade > material.quantidade:
        raise HTTPException(
            422,
            f"Quantidade insuficiente. Disponível: {material.quantidade} {material.unidade}"
        )

    # Baixar estoque
    material.quantidade -= payload.quantidade
    db.flush()

    # Registrar movimentação
    mov = models.Movimentacao(
        material_id = payload.material_id,
        usuario_id  = atual.id,
        tipo        = "saida",
        quantidade  = payload.quantidade,
        motivo      = payload.motivo,
        observacao  = payload.observacao,
    )
    db.add(mov)
    db.commit()
    db.refresh(mov)

    registrar_log(
        db, atual.id, "retirada", "material",
        payload.material_id,
        f"qtd={payload.quantidade} motivo={payload.motivo}",
    )

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    disparar_notificacao(db, "retirada", {
        "material":   material.nome,
        "quantidade": str(payload.quantidade),
        "unidade":    material.unidade,
        "motivo":     payload.motivo,
        "observacao": payload.observacao or "—",
        "usuario":    atual.nome,
        "data":       agora,
    })
    if material.alerta_minimo:
        disparar_notificacao(db, "alerta", {
            "material":   material.nome,
            "quantidade": str(material.quantidade),
            "unidade":    material.unidade,
            "minimo":     str(material.quantidade_minima),
            "grupo":      material.grupo.nome if material.grupo else "—",
            "data":       agora,
        })

    out = schemas.MovimentacaoOut.model_validate(mov)
    out.nome_material  = material.nome
    out.nome_usuario   = atual.nome
    out.grupo_nome     = material.grupo.nome             if material.grupo else ""
    out.categoria_nome = material.grupo.categoria.nome   if material.grupo and material.grupo.categoria else ""
    return out
