# © Todos os direitos reservados – github.com/Wbad-02
import io
import os
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from auth import get_usuario_atual, requer_editor_ou_admin, registrar_log
from database import get_db
from email_service import disparar_notificacao

router = APIRouter(prefix="/api/requerimentos", tags=["requerimentos"])

_origins = os.environ.get("CORS_ORIGINS", "http://localhost:8000")
_URL_BASE = _origins.split(",")[0].strip().rstrip("/")


def _requer_criador_req(
    db:    Session        = Depends(get_db),
    atual: models.Usuario = Depends(get_usuario_atual),
) -> models.Usuario:
    """Admin+ passa sempre. Editor só passa se o seu e-mail está cadastrado em 'requerimento'."""
    if atual.grupo in (models.GrupoPermissao.admin, models.GrupoPermissao.mestre):
        return atual
    if atual.grupo == models.GrupoPermissao.editor:
        existe = db.query(models.NotificacaoEmail).filter(
            models.NotificacaoEmail.tipo  == "requerimento",
            models.NotificacaoEmail.ativo == True,
            models.NotificacaoEmail.email == atual.email,
        ).first()
        if existe:
            return atual
    raise HTTPException(403, "Acesso restrito: seu e-mail não está autorizado a criar requerimentos")


def _requer_aprovador_req(
    db:    Session        = Depends(get_db),
    atual: models.Usuario = Depends(get_usuario_atual),
) -> models.Usuario:
    """Admin+ passa sempre. Editor só passa se o seu e-mail está em 'requerimento_decisao'."""
    if atual.grupo in (models.GrupoPermissao.admin, models.GrupoPermissao.mestre):
        return atual
    if atual.grupo == models.GrupoPermissao.editor:
        existe = db.query(models.NotificacaoEmail).filter(
            models.NotificacaoEmail.tipo  == "requerimento_decisao",
            models.NotificacaoEmail.ativo == True,
            models.NotificacaoEmail.email == atual.email,
        ).first()
        if existe:
            return atual
    raise HTTPException(403, "Acesso restrito: seu e-mail não está autorizado a aprovar/rejeitar requerimentos")


def _slugify(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^\w\s-]", "", texto).strip().lower()
    texto = re.sub(r"[\s_-]+", "_", texto)
    return texto[:60]


def _build_out(req: models.Requerimento) -> schemas.RequerimentoOut:
    total = sum(i.valor for i in req.itens)
    return schemas.RequerimentoOut(
        id=req.id,
        titulo=req.titulo,
        status=req.status.value if req.status else "aguardando",
        criado_em=req.criado_em,
        atualizado_em=req.atualizado_em,
        observacao=req.observacao,
        criador_nome=req.criador.nome if req.criador else "",
        aprovador_nome=req.aprovador.nome if req.aprovador else "",
        total=total,
        itens=[
            schemas.ItemRequerimentoOut(id=i.id, nome=i.nome, valor=i.valor)
            for i in req.itens
        ],
    )


def _load(req_id: int, db: Session) -> models.Requerimento:
    req = (
        db.query(models.Requerimento)
        .options(
            joinedload(models.Requerimento.criador),
            joinedload(models.Requerimento.aprovador),
            joinedload(models.Requerimento.itens),
        )
        .filter(models.Requerimento.id == req_id)
        .first()
    )
    if not req:
        raise HTTPException(404, "Requerimento nao encontrado")
    return req


# ── POST / — criar ─────────────────────────────────────────────────────────────
@router.post("/", response_model=schemas.RequerimentoOut, status_code=201)
def criar_requerimento(
    payload: schemas.RequerimentoCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(_requer_criador_req),
):
    if not payload.itens:
        raise HTTPException(422, "O requerimento deve ter ao menos um item")

    req = models.Requerimento(
        titulo=payload.titulo.strip(),
        status=models.StatusRequerimento.aguardando,
        criado_por=atual.id,
    )
    db.add(req)
    db.flush()

    for item in payload.itens:
        db.add(models.ItemRequerimento(
            requerimento_id=req.id,
            nome=item.nome.strip(),
            valor=item.valor,
        ))

    db.commit()
    db.refresh(req)

    req = _load(req.id, db)
    total = sum(i.valor for i in req.itens)

    registrar_log(db, atual.id, "criar", "requerimento", req.id, payload.titulo)

    disparar_notificacao(db, "requerimento", {
        "titulo":       req.titulo,
        "total":        f"R$ {total:,.2f}",
        "itens_count":  str(len(req.itens)),
        "criador":      atual.nome,
        "link":         f"{_URL_BASE}/#requerimentos",
    })

    return _build_out(req)


# ── GET / — listar ─────────────────────────────────────────────────────────────
@router.get("/", response_model=list[schemas.RequerimentoOut])
def listar_requerimentos(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    reqs = (
        db.query(models.Requerimento)
        .options(
            joinedload(models.Requerimento.criador),
            joinedload(models.Requerimento.aprovador),
            joinedload(models.Requerimento.itens),
        )
        .order_by(models.Requerimento.criado_em.desc())
        .all()
    )
    return [_build_out(r) for r in reqs]


# ── GET /{id} — detalhe ────────────────────────────────────────────────────────
@router.get("/{req_id}", response_model=schemas.RequerimentoOut)
def obter_requerimento(
    req_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    return _build_out(_load(req_id, db))


# ── POST /{id}/aprovar ─────────────────────────────────────────────────────────
@router.post("/{req_id}/aprovar", response_model=schemas.RequerimentoOut)
def aprovar_requerimento(
    req_id: int,
    body: schemas.AprovarRequerimentoBody = schemas.AprovarRequerimentoBody(),
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(_requer_aprovador_req),
):
    req = _load(req_id, db)
    if req.status != models.StatusRequerimento.aguardando:
        raise HTTPException(409, f"Requerimento ja esta '{req.status.value}'")

    req.status      = models.StatusRequerimento.aprovado
    req.aprovado_por = atual.id
    req.observacao   = body.observacao
    db.commit()
    db.refresh(req)

    req = _load(req_id, db)
    registrar_log(db, atual.id, "aprovar", "requerimento", req_id)

    disparar_notificacao(db, "requerimento_decisao", {
        "titulo":     req.titulo,
        "status":     "aprovado",
        "observacao": body.observacao or "—",
        "aprovador":  atual.nome,
    })

    return _build_out(req)


# ── POST /{id}/rejeitar ────────────────────────────────────────────────────────
@router.post("/{req_id}/rejeitar", response_model=schemas.RequerimentoOut)
def rejeitar_requerimento(
    req_id: int,
    body: schemas.RejeitarRequerimentoBody,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(_requer_aprovador_req),
):
    req = _load(req_id, db)
    if req.status != models.StatusRequerimento.aguardando:
        raise HTTPException(409, f"Requerimento ja esta '{req.status.value}'")

    req.status      = models.StatusRequerimento.rejeitado
    req.aprovado_por = atual.id
    req.observacao   = body.observacao
    db.commit()
    db.refresh(req)

    req = _load(req_id, db)
    registrar_log(db, atual.id, "rejeitar", "requerimento", req_id, body.observacao)

    disparar_notificacao(db, "requerimento_decisao", {
        "titulo":     req.titulo,
        "status":     "rejeitado",
        "observacao": body.observacao,
        "aprovador":  atual.nome,
    })

    return _build_out(req)


# ── GET /{id}/excel ────────────────────────────────────────────────────────────
@router.get("/{req_id}/excel")
def exportar_excel(
    req_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    req = _load(req_id, db)

    wb = Workbook()
    ws = wb.active
    ws.title = "Requerimento"

    # Paleta de cores
    COR_VERDE   = "1B3A2D"   # titulo
    COR_DOURADO = "C9A84C"   # cabecalho
    COR_BRANCO  = "FFFFFF"
    COR_TOTAL   = "F2F2F2"

    fill_verde   = PatternFill("solid", fgColor=COR_VERDE)
    fill_dourado = PatternFill("solid", fgColor=COR_DOURADO)
    fill_total   = PatternFill("solid", fgColor=COR_TOTAL)

    font_titulo  = Font(bold=True, color=COR_BRANCO, size=13)
    font_header  = Font(bold=True, color="000000", size=11)
    font_total   = Font(bold=True, size=11)
    font_normal  = Font(size=11)

    # ── Linha 1: titulo (A1:B1 merged) ────────────────────────────────────────
    ws.merge_cells("A1:B1")
    ws["A1"] = req.titulo
    ws["A1"].font      = font_titulo
    ws["A1"].fill      = fill_verde
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 22

    # ── Linha 2: cabecalho ─────────────────────────────────────────────────────
    ws["A2"] = "Nome"
    ws["B2"] = "Valor (R$)"
    for col in ("A2", "B2"):
        ws[col].font      = font_header
        ws[col].fill      = fill_dourado
        ws[col].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    # ── Linhas dos itens ───────────────────────────────────────────────────────
    for linha, item in enumerate(req.itens, start=3):
        ws.cell(row=linha, column=1, value=item.nome).font = font_normal
        cel_valor = ws.cell(row=linha, column=2, value=item.valor)
        cel_valor.font       = font_normal
        cel_valor.number_format = "#,##0.00"
        cel_valor.alignment  = Alignment(horizontal="right")

    # ── Linha de total ─────────────────────────────────────────────────────────
    linha_total = 3 + len(req.itens)
    total = sum(i.valor for i in req.itens)

    cel_label = ws.cell(row=linha_total, column=1, value="TOTAL")
    cel_label.font      = font_total
    cel_label.fill      = fill_total
    cel_label.alignment = Alignment(horizontal="right")

    cel_total = ws.cell(row=linha_total, column=2, value=total)
    cel_total.font          = font_total
    cel_total.fill          = fill_total
    cel_total.number_format = "#,##0.00"
    cel_total.alignment     = Alignment(horizontal="right")

    # Larguras das colunas
    ws.column_dimensions[get_column_letter(1)].width = 50
    ws.column_dimensions[get_column_letter(2)].width = 18

    # Serializar em memoria
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    slug     = _slugify(req.titulo)
    filename = f"requerimento_{req_id}_{slug}.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
