# © Todos os direitos reservados – github.com/Wbad-02
from datetime import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import models
from auth import requer_admin
from database import get_db

router = APIRouter(prefix="/api/auditoria", tags=["auditoria"])

_ACOES_VALIDAS    = {"criar","editar","remover","aprovar","rejeitar","reativar","inativar",
                     "atribuir","devolver","entrar","retirar","importar","cancelar"}
_ENTIDADES_VALIDAS = {"material","ativo","ativo_item","solicitacao","requerimento",
                      "usuario","categoria","grupo","unidade","movimentacao","notificacao"}


@router.get("/")
def listar_logs(
    usuario_id:  int | None = Query(None),
    acao:        str | None = Query(None),
    entidade:    str | None = Query(None),
    data_inicio: str | None = Query(None),
    data_fim:    str | None = Query(None),
    limit:  int = Query(100, ge=1, le=500),
    offset: int = Query(0,   ge=0),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    q = db.query(models.LogAuditoria)

    if usuario_id:
        q = q.filter(models.LogAuditoria.usuario_id == usuario_id)
    if acao:
        q = q.filter(models.LogAuditoria.acao == acao)
    if entidade:
        q = q.filter(models.LogAuditoria.entidade == entidade)
    if data_inicio:
        q = q.filter(models.LogAuditoria.criado_em >= dt.fromisoformat(data_inicio))
    if data_fim:
        q = q.filter(models.LogAuditoria.criado_em <= dt.fromisoformat(data_fim + "T23:59:59"))

    total = q.count()
    logs  = q.order_by(models.LogAuditoria.criado_em.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "id":          l.id,
                "usuario_nome": l.usuario.nome if l.usuario else "Sistema",
                "acao":        l.acao,
                "entidade":    l.entidade,
                "entidade_id": l.entidade_id,
                "detalhe":     l.detalhe,
                "criado_em":   l.criado_em.isoformat(),
            }
            for l in logs
        ],
    }


@router.get("/opcoes")
def opcoes_filtro(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    """Retorna acoes e entidades distintas presentes no log, para popular os filtros."""
    from sqlalchemy import distinct, func
    acoes    = [r[0] for r in db.query(distinct(models.LogAuditoria.acao)).all() if r[0]]
    entidades = [r[0] for r in db.query(distinct(models.LogAuditoria.entidade)).all() if r[0]]
    usuarios = [
        {"id": u.id, "nome": u.nome}
        for u in db.query(models.Usuario).filter(models.Usuario.ativo == True).order_by(models.Usuario.nome).all()
    ]
    return {"acoes": sorted(acoes), "entidades": sorted(entidades), "usuarios": usuarios}
