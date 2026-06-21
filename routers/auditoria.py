# © Todos os direitos reservados – github.com/Wbad-02
from datetime import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

import models
from auth import requer_admin
from database import get_db
from utils_export import criar_excel, criar_pdf

router = APIRouter(prefix="/api/auditoria", tags=["auditoria"])

_ACOES_VALIDAS    = {"criar","editar","remover","aprovar","rejeitar","reativar","inativar",
                     "atribuir","devolver","entrar","retirar","importar","cancelar"}
_ENTIDADES_VALIDAS = {"material","ativo","ativo_item","solicitacao","requerimento",
                      "usuario","categoria","grupo","unidade","movimentacao","notificacao"}


def _parse_data(valor: str | None) -> dt | None:
    if not valor:
        return None
    try:
        return dt.fromisoformat(valor)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data inválida: '{valor}'. Use formato AAAA-MM-DD.")


def _filtrar_auditoria(db: Session, usuario_id, acao, entidade, data_inicio, data_fim):
    q = (
        db.query(models.LogAuditoria)
        .options(joinedload(models.LogAuditoria.usuario))
    )
    if usuario_id:
        q = q.filter(models.LogAuditoria.usuario_id == usuario_id)
    if acao:
        q = q.filter(models.LogAuditoria.acao == acao)
    if entidade:
        q = q.filter(models.LogAuditoria.entidade == entidade)
    dt_inicio = _parse_data(data_inicio)
    if dt_inicio:
        q = q.filter(models.LogAuditoria.criado_em >= dt_inicio)
    dt_fim = _parse_data(data_fim)
    if dt_fim:
        q = q.filter(models.LogAuditoria.criado_em <= dt.fromisoformat(data_fim + "T23:59:59"))
    return q


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
    q = _filtrar_auditoria(db, usuario_id, acao, entidade, data_inicio, data_fim)
    total = q.count()
    logs = q.order_by(models.LogAuditoria.criado_em.desc()).offset(offset).limit(limit).all()

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


@router.get("/excel")
def exportar_auditoria_excel(
    usuario_id:  int | None = Query(None),
    acao:        str | None = Query(None),
    entidade:    str | None = Query(None),
    data_inicio: str | None = Query(None),
    data_fim:    str | None = Query(None),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    q = _filtrar_auditoria(db, usuario_id, acao, entidade, data_inicio, data_fim)
    logs = q.order_by(models.LogAuditoria.criado_em.desc()).all()

    headers = ["Data/Hora", "Usuário", "Ação", "Entidade", "ID Registro", "Detalhe"]
    col_widths = [18, 20, 14, 14, 12, 40]
    rows = [
        [
            l.criado_em.strftime("%d/%m/%Y %H:%M"),
            l.usuario.nome if l.usuario else "Sistema",
            l.acao, l.entidade,
            l.entidade_id or "—",
            l.detalhe or "—",
        ]
        for l in logs
    ]

    def style_fn(i, row):
        return {"align": "center", "align_2": "left", "align_6": "left"}

    return criar_excel("Auditoria", headers, col_widths, rows, "auditoria", style_fn)


@router.get("/pdf")
def exportar_auditoria_pdf(
    usuario_id:  int | None = Query(None),
    acao:        str | None = Query(None),
    entidade:    str | None = Query(None),
    data_inicio: str | None = Query(None),
    data_fim:    str | None = Query(None),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    q = _filtrar_auditoria(db, usuario_id, acao, entidade, data_inicio, data_fim)
    logs = q.order_by(models.LogAuditoria.criado_em.desc()).all()

    headers = ["Data/Hora", "Usuário", "Ação", "Entidade", "ID", "Detalhe"]
    col_widths_cm = [3.2, 3.5, 2.2, 2.5, 1.5, 6]
    rows = [
        [
            l.criado_em.strftime("%d/%m %H:%M"),
            l.usuario.nome if l.usuario else "Sistema",
            l.acao, l.entidade,
            str(l.entidade_id or "—"),
            l.detalhe or "—",
        ]
        for l in logs
    ]
    return criar_pdf(
        "Relatório de Auditoria", headers, col_widths_cm, rows,
        "auditoria", orientacao="landscape",
    )


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
