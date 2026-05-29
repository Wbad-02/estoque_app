# © Todos os direitos reservados – github.com/Wbad-02
import io
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from auth import get_usuario_atual, requer_editor_ou_admin, registrar_log
from database import get_db
from email_service import disparar_notificacao, _html_email, _linha_info
from utils import get_app_url

router = APIRouter(prefix="/api/requerimentos", tags=["requerimentos"])


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
    total = sum((i.quantidade or 1.0) * i.valor for i in req.itens)
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
            schemas.ItemRequerimentoOut(id=i.id, nome=i.nome, quantidade=i.quantidade or 1.0, valor=i.valor, url=i.url)
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
            quantidade=item.quantidade,
            valor=item.valor,
            url=item.url or None,
        ))

    db.commit()
    db.refresh(req)

    req = _load(req.id, db)
    total = sum((i.quantidade or 1.0) * i.valor for i in req.itens)

    registrar_log(db, atual.id, "criar", "requerimento", req.id, payload.titulo)

    disparar_notificacao(db, "requerimento", {
        "titulo":       req.titulo,
        "total":        f"R$ {total:,.2f}",
        "itens_count":  str(len(req.itens)),
        "criador":      atual.nome,
        "link":         f"{get_app_url()}/#requerimentos",
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


# ── GET /modelo-excel — template em branco ────────────────────────────────────
# IMPORTANTE: deve ficar ANTES de GET /{req_id} para evitar conflito de rota
@router.get("/modelo-excel")
def baixar_modelo_excel(
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    # Colunas: A=Nome | B=Link | C=Qtd | D=Valor Unit. | E=Subtotal
    wb = Workbook()
    ws = wb.active
    ws.title = "Requerimento"

    fill_verde   = PatternFill("solid", fgColor="1B3A2D")
    fill_dourado = PatternFill("solid", fgColor="C9A84C")
    font_branco  = Font(bold=True, color="FFFFFF", size=13)
    font_header  = Font(bold=True, size=11)
    font_normal  = Font(size=11)
    font_link    = Font(size=11, color="0563C1", underline="single")
    al_center    = Alignment(horizontal="center", vertical="center")
    al_right     = Alignment(horizontal="right",  vertical="center")
    al_left      = Alignment(horizontal="left",   vertical="center")

    # Linha 1 — título (A1:E1)
    ws.merge_cells("A1:E1")
    ws["A1"] = "Requerimento de Compra"
    ws["A1"].font = font_branco; ws["A1"].fill = fill_verde; ws["A1"].alignment = al_center
    ws.row_dimensions[1].height = 24

    # Linha 2 — cabeçalhos
    cabecalhos = [
        ("A2", "Nome"),
        ("B2", "Link (URL do produto)"),
        ("C2", "Qtd"),
        ("D2", "Valor Unitário (R$)"),
        ("E2", "Subtotal (R$)"),
    ]
    for cel, texto in cabecalhos:
        ws[cel] = texto
        ws[cel].font = font_header; ws[cel].fill = fill_dourado; ws[cel].alignment = al_center
    ws.row_dimensions[2].height = 18

    # Linhas de exemplo
    exemplos = [
        ("Mouse sem fio Logitech M170", "https://produto.mercadolivre.com.br/MLB-123456", 2, 89.90),
        ("Teclado USB padrão ABNT2",    "https://produto.mercadolivre.com.br/MLB-789012", 1, 69.90),
        ("Monitor 21.5\" Full HD",      "",                                               1, 649.00),
    ]
    for linha, (nome, url, qtd, val) in enumerate(exemplos, start=3):
        # Coluna A — Nome
        c_nome = ws.cell(row=linha, column=1, value=nome)
        c_nome.font = font_normal; c_nome.alignment = al_left

        # Coluna B — Link (texto puro; clicável como hyperlink se preenchido)
        c_url = ws.cell(row=linha, column=2, value=url or "")
        if url:
            c_url.hyperlink = url
            c_url.font = font_link
        else:
            c_url.font = font_normal
        c_url.alignment = al_left

        # Coluna C — Qtd
        c_qtd = ws.cell(row=linha, column=3, value=qtd)
        c_qtd.number_format = "#,##0.##"; c_qtd.alignment = al_right; c_qtd.font = font_normal

        # Coluna D — Valor Unit.
        c_val = ws.cell(row=linha, column=4, value=val)
        c_val.number_format = "#,##0.00"; c_val.alignment = al_right; c_val.font = font_normal

        # Coluna E — Subtotal (fórmula =C*D)
        c_sub = ws.cell(row=linha, column=5, value=f"=C{linha}*D{linha}")
        c_sub.number_format = "#,##0.00"; c_sub.alignment = al_right; c_sub.font = font_normal

    # Larguras
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 42
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 20
    ws.column_dimensions["E"].width = 18

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="modelo_requerimento.xlsx"'},
    )


# ── POST /parse-excel — lê planilha e devolve itens como JSON (sem salvar) ───
# IMPORTANTE: deve ficar ANTES de GET /{req_id} para evitar conflito de rota
@router.post("/parse-excel")
def parse_excel(
    arquivo: UploadFile = File(...),
    _: models.Usuario = Depends(get_usuario_atual),
):
    """Lê a planilha e retorna os itens como JSON — não cria nada no banco."""
    from openpyxl import load_workbook

    if not arquivo.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(422, "Envie um arquivo .xlsx")

    try:
        conteudo = arquivo.file.read()
        wb = load_workbook(io.BytesIO(conteudo), data_only=False)
        ws = wb.active
    except Exception:
        raise HTTPException(422, "Arquivo Excel inválido ou corrompido")

    _SKIP_NOMES = {"TOTAL", "NOME", "NOME DO ITEM", "REQUERIMENTO DE COMPRA"}
    itens = []

    for row_cells in ws.iter_rows(min_row=2):
        if len(row_cells) < 4:
            continue
        raw_nome = row_cells[0].value
        nome = str(raw_nome).strip() if raw_nome not in (None, "") else ""
        if not nome or nome.upper() in _SKIP_NOMES:
            continue

        c_url = row_cells[1]
        raw_url = c_url.value
        url: str | None = str(raw_url).strip() if raw_url not in (None, "") else None
        if not url and c_url.hyperlink:
            url = c_url.hyperlink.target if hasattr(c_url.hyperlink, "target") else str(c_url.hyperlink)

        try:
            qtd = float(row_cells[2].value) if row_cells[2].value not in (None, "") else 1.0
            val = float(row_cells[3].value) if row_cells[3].value not in (None, "") else 0.0
        except (TypeError, ValueError):
            continue

        if qtd <= 0 or val <= 0:
            continue

        itens.append({"nome": nome, "url": url or None, "quantidade": qtd, "valor": val})

    if not itens:
        raise HTTPException(422, "Nenhum item válido encontrado na planilha (verifique o modelo)")

    return itens


# ── POST /importar-excel — cria requerimento a partir de planilha ─────────────
# IMPORTANTE: deve ficar ANTES de GET /{req_id} para evitar conflito de rota
@router.post("/importar-excel", response_model=schemas.RequerimentoOut, status_code=201)
def importar_excel(
    titulo: str,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(_requer_criador_req),
):
    from openpyxl import load_workbook

    if not arquivo.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(422, "Envie um arquivo .xlsx")

    try:
        conteudo = arquivo.file.read()
        # data_only=False preserva acesso a hyperlinks nas células
        wb = load_workbook(io.BytesIO(conteudo), data_only=False)
        ws = wb.active
    except Exception:
        raise HTTPException(422, "Arquivo Excel inválido ou corrompido")

    # Layout esperado: A=Nome | B=Link (URL) | C=Qtd | D=Valor Unit. | E=Subtotal (ignorado)
    _SKIP_NOMES = {"TOTAL", "NOME", "NOME DO ITEM", "REQUERIMENTO DE COMPRA"}

    itens_raw = []
    for row_cells in ws.iter_rows(min_row=2):   # min_row=2 pula o título (linha 1)
        if len(row_cells) < 4:
            continue

        # Coluna A — Nome
        raw_nome = row_cells[0].value
        nome = str(raw_nome).strip() if raw_nome not in (None, "") else ""
        if not nome or nome.upper() in _SKIP_NOMES:
            continue

        # Coluna B — Link/URL (texto puro ou hyperlink na célula)
        c_url = row_cells[1]
        raw_url = c_url.value
        url: str | None = None
        if raw_url not in (None, ""):
            url = str(raw_url).strip() or None
        # Fallback: hyperlink embutido na célula B
        if not url and c_url.hyperlink:
            url = c_url.hyperlink.target if hasattr(c_url.hyperlink, "target") else str(c_url.hyperlink)

        # Coluna C — Qtd
        # Coluna D — Valor Unit.
        try:
            raw_qtd = row_cells[2].value
            raw_val = row_cells[3].value
            qtd = float(raw_qtd) if raw_qtd not in (None, "") else 1.0
            val = float(raw_val) if raw_val not in (None, "") else 0.0
        except (TypeError, ValueError):
            continue

        if qtd <= 0 or val <= 0:
            continue

        itens_raw.append({"nome": nome, "quantidade": qtd, "valor": val, "url": url or None})

    if not itens_raw:
        raise HTTPException(422, "Nenhum item válido encontrado na planilha (verifique o modelo)")

    titulo = titulo.strip()
    if not titulo:
        raise HTTPException(422, "Informe o título do requerimento")

    req = models.Requerimento(
        titulo=titulo,
        status=models.StatusRequerimento.aguardando,
        criado_por=atual.id,
    )
    db.add(req)
    db.flush()

    for item in itens_raw:
        db.add(models.ItemRequerimento(
            requerimento_id=req.id,
            nome=item["nome"],
            quantidade=item["quantidade"],
            valor=item["valor"],
            url=item.get("url"),
        ))

    db.commit()
    db.refresh(req)
    req = _load(req.id, db)
    total = sum((i.quantidade or 1.0) * i.valor for i in req.itens)

    registrar_log(db, atual.id, "criar", "requerimento", req.id, titulo)

    disparar_notificacao(db, "requerimento", {
        "titulo":      req.titulo,
        "total":       f"R$ {total:,.2f}",
        "itens_count": str(len(req.itens)),
        "criador":     atual.nome,
        "link":        f"{get_app_url()}/#requerimentos",
    })

    return _build_out(req)


# ── GET /{id} — detalhe ────────────────────────────────────────────────────────
@router.get("/{req_id}", response_model=schemas.RequerimentoOut)
def obter_requerimento(
    req_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    return _build_out(_load(req_id, db))


def _email_decisao_html(titulo: str, status: str, aprovador: str, obs: str,
                        itens_aprovados: list[str], itens_reprovados: list[str]) -> str:
    cor_status = "#1B7A4B" if status == "aprovado" else "#C0392B"
    badge_html = (
        f'<span style="display:inline-block;padding:3px 12px;border-radius:12px;'
        f'font-size:12px;font-weight:600;background:{cor_status};color:#fff">'
        f'{status.upper()}</span>'
    )

    def _lista_itens(itens: list[str], cor: str, icone: str) -> str:
        if not itens:
            return ""
        linhas = "".join(
            f'<tr><td style="padding:4px 8px;font-size:13px;color:{cor}">{icone}</td>'
            f'<td style="padding:4px 8px;font-size:13px;color:#333">{item}</td></tr>'
            for item in itens
        )
        return f'<table style="width:100%;border-collapse:collapse;margin-bottom:6px">{linhas}</table>'

    secao_itens = ""
    if itens_aprovados or itens_reprovados:
        secao_itens = '<hr style="border:none;border-top:1px solid #eee;margin:16px 0">'
        if itens_aprovados:
            secao_itens += (
                '<p style="margin:0 0 6px;font-size:13px;font-weight:600;color:#1B7A4B">✔ Itens aprovados para compra</p>'
                + _lista_itens(itens_aprovados, "#1B7A4B", "✔")
            )
        if itens_reprovados:
            secao_itens += (
                '<p style="margin:12px 0 6px;font-size:13px;font-weight:600;color:#C0392B">✘ Itens não aprovados</p>'
                + _lista_itens(itens_reprovados, "#C0392B", "✘")
            )

    corpo = f"""
<p style="margin:0 0 16px;font-size:15px;color:#444">
  O requerimento de compra abaixo teve uma decisão registrada.
</p>
<table style="width:100%;border-collapse:collapse">
  {_linha_info("Requerimento", titulo, destaque=True)}
  {_linha_info("Status", badge_html)}
  {_linha_info("Decisão por", aprovador)}
  {_linha_info("Observação", obs)}
</table>
{secao_itens}
<div style="margin-top:24px;padding-top:16px;border-top:1px solid #eee">
  <a href="{get_app_url()}/#requerimentos"
     style="display:inline-block;padding:10px 24px;background:#1B3A2D;color:#fff;
            text-decoration:none;border-radius:6px;font-size:14px;font-weight:600">
    Ver requerimento
  </a>
</div>
"""
    return _html_email(f"Requerimento '{titulo}' — {status}", corpo)


# ── POST /{id}/aprovar ─────────────────────────────────────────────────────────
@router.post("/{req_id}/aprovar", response_model=schemas.RequerimentoOut)
def aprovar_requerimento(
    req_id: int,
    body: schemas.AprovarRequerimentoBody,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(_requer_aprovador_req),
):
    req = _load(req_id, db)
    if req.status != models.StatusRequerimento.aguardando:
        raise HTTPException(409, f"Requerimento ja esta '{req.status.value}'")

    req.status       = models.StatusRequerimento.aprovado
    req.aprovado_por = atual.id
    req.observacao   = body.observacao
    db.commit()
    db.refresh(req)

    req = _load(req_id, db)
    registrar_log(db, atual.id, "aprovar", "requerimento", req_id)

    criador_email = req.criador.email if req.criador else None
    corpo_html = _email_decisao_html(
        req.titulo, "aprovado", atual.nome, body.observacao,
        body.itens_aprovados, body.itens_reprovados,
    )
    disparar_notificacao(db, "requerimento_decisao", {
        "titulo":     req.titulo,
        "status":     "aprovado",
        "observacao": body.observacao,
        "aprovador":  atual.nome,
    }, extras=[criador_email] if criador_email else None, corpo_html=corpo_html)

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

    req.status       = models.StatusRequerimento.rejeitado
    req.aprovado_por = atual.id
    req.observacao   = body.observacao
    db.commit()
    db.refresh(req)

    req = _load(req_id, db)
    registrar_log(db, atual.id, "rejeitar", "requerimento", req_id, body.observacao)

    criador_email = req.criador.email if req.criador else None
    corpo_html = _email_decisao_html(
        req.titulo, "rejeitado", atual.nome, body.observacao,
        body.itens_aprovados, body.itens_reprovados,
    )
    disparar_notificacao(db, "requerimento_decisao", {
        "titulo":     req.titulo,
        "status":     "rejeitado",
        "observacao": body.observacao,
        "aprovador":  atual.nome,
    }, extras=[criador_email] if criador_email else None, corpo_html=corpo_html)

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
    font_link    = Font(size=11, color="0563C1", underline="single")

    # ── Linha 1: titulo (A1:E1 merged) ────────────────────────────────────────
    ws.merge_cells("A1:E1")
    ws["A1"] = req.titulo
    ws["A1"].font      = font_titulo
    ws["A1"].fill      = fill_verde
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 22

    # ── Linha 2: cabecalho (5 colunas) ────────────────────────────────────────
    # A=Nome | B=Link | C=Qtd | D=Valor Unit. | E=Subtotal
    cabecalhos = [
        (1, "Nome"),
        (2, "Link (URL do produto)"),
        (3, "Qtd"),
        (4, "Valor Unit. (R$)"),
        (5, "Subtotal (R$)"),
    ]
    for col, texto in cabecalhos:
        c = ws.cell(row=2, column=col, value=texto)
        c.font = font_header; c.fill = fill_dourado
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    # ── Linhas dos itens ───────────────────────────────────────────────────────
    for linha, item in enumerate(req.itens, start=3):
        qtd      = item.quantidade or 1.0
        subtotal = round(qtd * item.valor, 2)

        # Coluna A — Nome
        c_nome = ws.cell(row=linha, column=1, value=item.nome)
        c_nome.font = font_normal
        c_nome.alignment = Alignment(horizontal="left")

        # Coluna B — Link
        c_url = ws.cell(row=linha, column=2, value=item.url or "")
        if item.url:
            c_url.hyperlink = item.url
            c_url.font = font_link
        else:
            c_url.font = font_normal
        c_url.alignment = Alignment(horizontal="left")

        # Coluna C — Qtd
        c_qtd = ws.cell(row=linha, column=3, value=qtd)
        c_qtd.font = font_normal; c_qtd.number_format = "#,##0.##"
        c_qtd.alignment = Alignment(horizontal="right")

        # Coluna D — Valor Unit.
        c_val = ws.cell(row=linha, column=4, value=item.valor)
        c_val.font = font_normal; c_val.number_format = "#,##0.00"
        c_val.alignment = Alignment(horizontal="right")

        # Coluna E — Subtotal
        c_sub = ws.cell(row=linha, column=5, value=subtotal)
        c_sub.font = font_normal; c_sub.number_format = "#,##0.00"
        c_sub.alignment = Alignment(horizontal="right")

    # ── Linha de total ─────────────────────────────────────────────────────────
    linha_total = 3 + len(req.itens)
    total = sum((i.quantidade or 1.0) * i.valor for i in req.itens)

    ws.merge_cells(f"A{linha_total}:D{linha_total}")
    cel_label = ws.cell(row=linha_total, column=1, value="TOTAL")
    cel_label.font = font_total; cel_label.fill = fill_total
    cel_label.alignment = Alignment(horizontal="right")

    cel_total = ws.cell(row=linha_total, column=5, value=round(total, 2))
    cel_total.font = font_total; cel_total.fill = fill_total
    cel_total.number_format = "#,##0.00"; cel_total.alignment = Alignment(horizontal="right")

    # Larguras das colunas
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 42
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 18

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

