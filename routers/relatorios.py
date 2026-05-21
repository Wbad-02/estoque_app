# © Todos os direitos reservados – github.com/Wbad-02
import io
from models import agora as _agora_br
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database import get_db
from auth import get_usuario_atual, requer_admin, requer_editor_ou_admin
import models

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

router = APIRouter(prefix="/api/relatorios", tags=["relatorios"])


def _obter_materiais(db: Session, apenas_alertas: bool):
    mats = (
        db.query(models.Material)
        .filter(models.Material.ativo == True)
        .join(models.GrupoMaterial)
        .order_by(models.GrupoMaterial.nome, models.Material.nome)
        .all()
    )
    if apenas_alertas:
        mats = [m for m in mats if m.alerta_minimo]
    return mats


@router.get("/excel")
def exportar_excel(
    apenas_alertas: bool = False,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    materiais = _obter_materiais(db, apenas_alertas)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Estoque"

    header_fill = PatternFill("solid", fgColor="1E3A34")
    alert_fill  = PatternFill("solid", fgColor="FFF3CD")
    header_font = Font(bold=True, color="FFFFFF")

    headers    = ["ID", "Material", "Categoria", "Grupo", "Qtd.", "Unidade", "Mín. Grupo", "Status"]
    col_widths = [6, 28, 18, 18, 8, 8, 12, 12]

    for col_idx, (header, width) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font      = header_font
        cell.fill      = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = width

    for row_idx, m in enumerate(materiais, 2):
        alerta = m.alerta_minimo
        status = "⚠ ALERTA" if alerta else "OK"
        row_data = [
            m.id, m.nome,
            m.categoria.nome if m.categoria else "—",
            m.grupo.nome,
            m.quantidade, m.unidade,
            m.grupo.quantidade_minima,
            status,
        ]
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(horizontal="center" if col_idx != 2 else "left")
            if alerta:
                cell.fill = alert_fill

    ws.freeze_panes = "A2"

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"estoque_{_agora_br().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/pdf")
def exportar_pdf(
    apenas_alertas: bool = False,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    materiais = _obter_materiais(db, apenas_alertas)

    output = io.BytesIO()
    doc    = SimpleDocTemplate(output, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title", parent=styles["Title"],
        fontSize=16, textColor=colors.HexColor("#1E3A34"),
    )
    sub_style = ParagraphStyle(
        "sub", parent=styles["Normal"],
        fontSize=9, textColor=colors.grey,
    )

    elements = []
    titulo = "Relatório de Estoque" + (" – Itens em Alerta" if apenas_alertas else "")
    elements.append(Paragraph(titulo, title_style))
    elements.append(Paragraph(
        f"Gerado em {_agora_br().strftime('%d/%m/%Y às %H:%M')}",
        sub_style,
    ))
    elements.append(Spacer(1, 0.5*cm))

    table_data = [["Material", "Categoria", "Grupo", "Qtd.", "Un.", "Mín.", "Status"]]
    for m in materiais:
        alerta = m.alerta_minimo
        table_data.append([
            m.nome,
            m.categoria.nome if m.categoria else "—",
            m.grupo.nome,
            str(m.quantidade),
            m.unidade,
            str(m.grupo.quantidade_minima),
            "ALERTA" if alerta else "OK",
        ])

    col_widths_pdf = [5.5*cm, 3.5*cm, 3.5*cm, 1.8*cm, 1.5*cm, 1.5*cm, 2*cm]
    table = Table(table_data, colWidths=col_widths_pdf, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A34")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    for row_idx, m in enumerate(materiais, 1):
        if m.alerta_minimo:
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#FFF3CD")),
                ("TEXTCOLOR",  (-1, row_idx), (-1, row_idx), colors.HexColor("#856404")),
            ]))

    elements.append(table)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        f"Total: {len(materiais)} item(ns) · © Todos os direitos reservados – github.com/Wbad-02",
        sub_style,
    ))

    doc.build(elements)
    output.seek(0)

    filename = f"estoque_{_agora_br().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/saidas/excel")
def exportar_saidas_excel(
    motivo:       str | None = None,
    data_inicio:  str | None = None,
    data_fim:     str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    from datetime import datetime as dt
    q = db.query(models.Movimentacao).filter(models.Movimentacao.tipo == "saida")
    if motivo:
        q = q.filter(models.Movimentacao.motivo == motivo)
    if data_inicio:
        q = q.filter(models.Movimentacao.criado_em >= dt.fromisoformat(data_inicio))
    if data_fim:
        q = q.filter(models.Movimentacao.criado_em <= dt.fromisoformat(data_fim + "T23:59:59"))
    rows = q.order_by(models.Movimentacao.criado_em.desc()).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Saídas"

    header_fill = PatternFill("solid", fgColor="1E3A34")
    header_font = Font(bold=True, color="FFFFFF")
    colab_fill  = PatternFill("solid", fgColor="E3F2FD")
    defeito_fill = PatternFill("solid", fgColor="FCE4EC")

    headers    = ["Data/Hora", "Material", "Categoria", "Grupo", "Qtd.", "Unidade", "Motivo", "Observação", "Usuário"]
    col_widths = [18, 28, 18, 18, 8, 8, 18, 30, 18]

    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font; cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = w

    motivo_label = {"colaborador": "Atribuído a colaborador", "defeito": "Defeito / Ruim"}

    for ri, r in enumerate(rows, 2):
        mat  = r.material
        grp  = mat.grupo       if mat  else None
        cat  = grp.categoria   if grp  else None
        usr  = r.usuario
        motivo_str = r.motivo if r.motivo else ""
        row_data = [
            r.criado_em.strftime("%d/%m/%Y %H:%M"),
            mat.nome           if mat  else "—",
            cat.nome           if cat  else "—",
            grp.nome           if grp  else "—",
            r.quantidade,
            mat.unidade        if mat  else "—",
            motivo_label.get(motivo_str, motivo_str or "—"),
            r.observacao or "—",
            usr.nome           if usr  else "Sistema",
        ]
        fill = colab_fill if motivo_str == "colaborador" else defeito_fill
        for ci, val in enumerate(row_data, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.alignment = Alignment(horizontal="center" if ci not in (2,8) else "left")
            cell.fill = fill

    ws.freeze_panes = "A2"

    # Totais no rodapé
    ws.cell(row=len(rows)+3, column=1, value="Total de registros:")
    ws.cell(row=len(rows)+3, column=2, value=len(rows)).font = Font(bold=True)
    ws.cell(row=len(rows)+4, column=1, value="© Todos os direitos reservados – github.com/Wbad-02")

    output = io.BytesIO(); wb.save(output); output.seek(0)
    filename = f"saidas_{_agora_br().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/saidas/pdf")
def exportar_saidas_pdf(
    motivo:      str | None = None,
    data_inicio: str | None = None,
    data_fim:    str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    from datetime import datetime as dt
    q = db.query(models.Movimentacao).filter(models.Movimentacao.tipo == "saida")
    if motivo:
        q = q.filter(models.Movimentacao.motivo == motivo)
    if data_inicio:
        q = q.filter(models.Movimentacao.criado_em >= dt.fromisoformat(data_inicio))
    if data_fim:
        q = q.filter(models.Movimentacao.criado_em <= dt.fromisoformat(data_fim + "T23:59:59"))
    rows = q.order_by(models.Movimentacao.criado_em.desc()).all()

    output = io.BytesIO()
    doc    = SimpleDocTemplate(output, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=14, textColor=colors.HexColor("#1E3A34"))
    sub_style   = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.grey)

    elements = []
    titulo = "Relatório de Saídas de Estoque"
    if motivo:
        _motivo_label = {'colaborador': 'Colaborador', 'defeito': 'Defeito'}
        titulo += f" — {_motivo_label.get(motivo, motivo)}"
    elements.append(Paragraph(titulo, title_style))
    elements.append(Paragraph(f"Gerado em {_agora_br().strftime('%d/%m/%Y às %H:%M')}", sub_style))
    elements.append(Spacer(1, 0.4*cm))

    motivo_label = {"colaborador": "Colaborador", "defeito": "Defeito"}
    table_data = [["Data/Hora", "Material", "Grupo", "Qtd.", "Motivo", "Observação", "Usuário"]]
    for r in rows:
        mat = r.material; grp = mat.grupo if mat else None; usr = r.usuario
        motivo_str = r.motivo if r.motivo else ""
        table_data.append([
            r.criado_em.strftime("%d/%m %H:%M"),
            mat.nome        if mat else "—",
            grp.nome        if grp else "—",
            str(r.quantidade),
            motivo_label.get(motivo_str, motivo_str or "—"),
            (r.observacao or "—")[:30],
            usr.nome        if usr else "Sistema",
        ])

    cw = [3*cm, 5*cm, 3*cm, 1.5*cm, 2.5*cm, 3.5*cm, 3*cm]
    table = Table(table_data, colWidths=cw, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1E3A34")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",       (0,0), (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        f"Total: {len(rows)} registro(s) · © Todos os direitos reservados – github.com/Wbad-02",
        sub_style,
    ))
    doc.build(elements)
    output.seek(0)

    filename = f"saidas_{_agora_br().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        output, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Relatório de Ativos ───────────────────────────────────────

@router.get("/ativos/excel")
def exportar_ativos_excel(
    status: str | None = None,   # "ativo" | "inativo" | None = todos
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    q = db.query(models.Ativo)
    if status == "ativo":
        q = q.filter(models.Ativo.ativo == True)
    elif status == "inativo":
        q = q.filter(models.Ativo.ativo == False)
    ativos = q.order_by(models.Ativo.nome).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ativos"
    header_fill = PatternFill("solid", fgColor="1E3A34")
    header_font = Font(bold=True, color="FFFFFF")
    inativo_fill = PatternFill("solid", fgColor="ECEFF1")

    headers    = ["ID", "Nome", "Descrição", "Categoria", "Grupo", "Status", "Materiais em uso", "Cadastrado em"]
    col_widths = [6, 28, 22, 18, 18, 10, 16, 18]
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font; cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = w

    for ri, a in enumerate(ativos, 2):
        itens_ativos = sum(1 for i in a.itens if i.devolvido_em is None)
        row_data = [
            a.id, a.nome, a.descricao or "—",
            a.grupo.categoria.nome if a.grupo and a.grupo.categoria else "—",
            a.grupo.nome if a.grupo else "—",
            "Ativo" if a.ativo else "Inativo",
            itens_ativos,
            a.criado_em.strftime("%d/%m/%Y"),
        ]
        fill = inativo_fill if not a.ativo else None
        for ci, val in enumerate(row_data, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.alignment = Alignment(horizontal="center" if ci != 2 else "left")
            if fill:
                cell.fill = fill

    ws.freeze_panes = "A2"
    output = io.BytesIO(); wb.save(output); output.seek(0)
    filename = f"ativos_{_agora_br().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/ativos/pdf")
def exportar_ativos_pdf(
    status: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    q = db.query(models.Ativo)
    if status == "ativo":
        q = q.filter(models.Ativo.ativo == True)
    elif status == "inativo":
        q = q.filter(models.Ativo.ativo == False)
    ativos = q.order_by(models.Ativo.nome).all()

    output = io.BytesIO()
    doc    = SimpleDocTemplate(output, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=14, textColor=colors.HexColor("#1E3A34"))
    sub_style   = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.grey)

    elements = []
    titulo = "Relatório de Ativos"
    if status == "ativo":   titulo += " — Somente Ativos"
    elif status == "inativo": titulo += " — Somente Inativos"
    elements.append(Paragraph(titulo, title_style))
    elements.append(Paragraph(f"Gerado em {_agora_br().strftime('%d/%m/%Y às %H:%M')}", sub_style))
    elements.append(Spacer(1, 0.4*cm))

    table_data = [["Nome", "Categoria", "Grupo", "Status", "Materiais em uso"]]
    for a in ativos:
        itens_ativos = sum(1 for i in a.itens if i.devolvido_em is None)
        table_data.append([
            a.nome,
            a.grupo.categoria.nome if a.grupo and a.grupo.categoria else "—",
            a.grupo.nome if a.grupo else "—",
            "Ativo" if a.ativo else "Inativo",
            str(itens_ativos),
        ])

    cw = [5.5*cm, 3.5*cm, 3.5*cm, 2*cm, 3*cm]
    table = Table(table_data, colWidths=cw, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1E3A34")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",       (0,0), (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        f"Total: {len(ativos)} registro(s) · © Todos os direitos reservados – github.com/Wbad-02",
        sub_style,
    ))
    doc.build(elements)
    output.seek(0)

    filename = f"ativos_{_agora_br().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        output, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Relatório de Notificações ─────────────────────────────────

@router.get("/notificacoes/excel")
def exportar_notificacoes_excel(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    emails = db.query(models.NotificacaoEmail).filter(
        models.NotificacaoEmail.ativo == True
    ).order_by(models.NotificacaoEmail.tipo, models.NotificacaoEmail.email).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notificacoes"
    header_fill = PatternFill("solid", fgColor="1E3A34")
    header_font = Font(bold=True, color="FFFFFF")
    tipo_fills = {
        "retirada": PatternFill("solid", fgColor="E3F2FD"),
        "entrada":  PatternFill("solid", fgColor="E8F5E9"),
        "alerta":   PatternFill("solid", fgColor="FFF3E0"),
    }

    headers    = ["Tipo", "E-mail", "Intervalo (dias)", "Cadastrado em"]
    col_widths = [14, 36, 18, 18]
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font; cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = w

    tipo_label = {"retirada": "Retirada", "entrada": "Entrada", "alerta": "Alerta"}
    for ri, e in enumerate(emails, 2):
        row_data = [
            tipo_label.get(e.tipo, e.tipo),
            e.email,
            e.intervalo_dias if e.intervalo_dias else "—",
            e.criado_em.strftime("%d/%m/%Y"),
        ]
        fill = tipo_fills.get(e.tipo)
        for ci, val in enumerate(row_data, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.alignment = Alignment(horizontal="center" if ci != 2 else "left")
            if fill:
                cell.fill = fill

    ws.freeze_panes = "A2"
    output = io.BytesIO(); wb.save(output); output.seek(0)
    filename = f"notificacoes_{_agora_br().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── helpers de dados ─────────────────────────────────────────

def _dados_entradas_nfe(db, mes: int, ano: int):
    from sqlalchemy.orm import joinedload
    from sqlalchemy import func as _f
    movs = (
        db.query(models.Movimentacao)
        .options(
            joinedload(models.Movimentacao.material)
            .joinedload(models.Material.grupo)
            .joinedload(models.GrupoMaterial.categoria),
        )
        .filter(
            models.Movimentacao.tipo == "entrada",
            models.Movimentacao.nf_numero.isnot(None),
            _f.strftime("%m", models.Movimentacao.criado_em) == f"{mes:02d}",
            _f.strftime("%Y", models.Movimentacao.criado_em) == str(ano),
        )
        .order_by(models.Movimentacao.criado_em.asc())
        .all()
    )
    resultado = []
    for m in movs:
        mat       = m.material
        grupo     = mat.grupo if mat else None
        categoria = grupo.categoria if grupo else None
        qtd       = m.quantidade or 0.0
        vunit     = m.valor_unitario or 0.0
        resultado.append({
            "nf_numero":      m.nf_numero,
            "material_nome":  mat.nome if mat else "",
            "categoria_nome": categoria.nome if categoria else "",
            "grupo_nome":     grupo.nome if grupo else "",
            "quantidade":     qtd,
            "unidade":        mat.unidade if mat else "",
            "valor_unitario": vunit,
            "subtotal":       round(qtd * vunit, 2),
            "criado_em":      m.criado_em.isoformat(),
        })
    return resultado


def _dados_consumo_medio(db, meses: int):
    from datetime import timedelta
    from sqlalchemy import func as _f
    if not (1 <= meses <= 24):
        meses = 3
    corte = _agora_br() - timedelta(days=30 * meses)
    saidas_map = {
        r.material_id: float(r.total_saida or 0)
        for r in db.query(
            models.Movimentacao.material_id,
            _f.sum(models.Movimentacao.quantidade).label("total_saida"),
        )
        .filter(models.Movimentacao.tipo == "saida", models.Movimentacao.criado_em >= corte)
        .group_by(models.Movimentacao.material_id)
        .all()
    }
    mats = (
        db.query(models.Material)
        .filter(models.Material.ativo == True)
        .join(models.GrupoMaterial)
        .order_by(models.GrupoMaterial.nome, models.Material.nome)
        .all()
    )
    resultado = []
    for m in mats:
        total        = saidas_map.get(m.id, 0.0)
        media_mensal = round(total / meses, 2)
        dias         = round((float(m.quantidade) / media_mensal) * 30) if media_mensal > 0 else None
        resultado.append({
            "material_id":           m.id,
            "material_nome":         m.nome,
            "categoria_nome":        m.grupo.categoria.nome if m.grupo and m.grupo.categoria else "",
            "grupo_nome":            m.grupo.nome if m.grupo else "",
            "estoque_atual":         float(m.quantidade),
            "unidade":               m.unidade,
            "consumo_total_periodo": total,
            "media_mensal":          media_mensal,
            "dias_cobertura":        dias,
        })
    resultado.sort(key=lambda x: (x["dias_cobertura"] is None, x["dias_cobertura"] or 0))
    return resultado


def _dados_solicitacoes_material(db):
    from sqlalchemy import func as _f, case
    rows = (
        db.query(
            models.SolicitacaoEstoque.material_id,
            _f.count(models.SolicitacaoEstoque.id).label("total"),
            _f.sum(case((models.SolicitacaoEstoque.status == models.StatusSolicitacao.aprovado,  1), else_=0)).label("aprovados"),
            _f.sum(case((models.SolicitacaoEstoque.status == models.StatusSolicitacao.rejeitado, 1), else_=0)).label("rejeitados"),
            _f.sum(case((models.SolicitacaoEstoque.status == models.StatusSolicitacao.aguardando,1), else_=0)).label("aguardando"),
        )
        .group_by(models.SolicitacaoEstoque.material_id)
        .order_by(_f.count(models.SolicitacaoEstoque.id).desc())
        .all()
    )
    mat_ids = [r.material_id for r in rows]
    mats = {
        m.id: m
        for m in db.query(models.Material).filter(models.Material.id.in_(mat_ids)).all()
    } if mat_ids else {}
    resultado = []
    for r in rows:
        mat      = mats.get(r.material_id)
        total    = int(r.total or 0)
        aprovados = int(r.aprovados or 0)
        taxa     = round((aprovados / total) * 100, 1) if total > 0 else 0.0
        resultado.append({
            "material_id":    r.material_id,
            "material_nome":  mat.nome if mat else "—",
            "categoria_nome": mat.grupo.categoria.nome if mat and mat.grupo and mat.grupo.categoria else "",
            "grupo_nome":     mat.grupo.nome if mat and mat.grupo else "",
            "total":          total,
            "aprovados":      aprovados,
            "rejeitados":     int(r.rejeitados or 0),
            "aguardando":     int(r.aguardando or 0),
            "taxa_aprovacao": taxa,
        })
    return resultado


# ── Endpoints JSON ────────────────────────────────────────────

@router.get("/entradas-nfe")
def relatorio_entradas_nfe(
    mes: int, ano: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    return _dados_entradas_nfe(db, mes, ano)


@router.get("/consumo-medio")
def consumo_medio(
    meses: int = 3,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    return _dados_consumo_medio(db, meses)


@router.get("/solicitacoes-por-material")
def solicitacoes_por_material(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    return _dados_solicitacoes_material(db)


# ── Exports: NF-e ────────────────────────────────────────────

def _nfe_excel(dados, mes, ano):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "NF-e"
    hfill = PatternFill("solid", fgColor="1E3A34")
    hfont = Font(bold=True, color="FFFFFF")
    headers    = ["NF-e", "Material", "Categoria", "Grupo", "Qtd.", "Unidade", "Valor Unit.", "Subtotal", "Data"]
    col_widths = [14, 28, 18, 18, 8, 8, 14, 14, 20]
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font = hfont; c.fill = hfill; c.alignment = Alignment(horizontal="center")
        ws.column_dimensions[c.column_letter].width = w
    total_geral = 0.0
    for ri, r in enumerate(dados, 2):
        row = [r["nf_numero"] or "—", r["material_nome"], r["categoria_nome"], r["grupo_nome"],
               r["quantidade"], r["unidade"], r["valor_unitario"] or None, r["subtotal"] or None,
               r["criado_em"][:16].replace("T", " ")]
        for ci, v in enumerate(row, 1):
            c = ws.cell(row=ri, column=ci, value=v)
            c.alignment = Alignment(horizontal="left" if ci in (2,3,4,9) else "center")
        total_geral += r["subtotal"] or 0
    # totalizador
    tr = len(dados) + 2
    ws.cell(row=tr, column=7, value="TOTAL").font = Font(bold=True)
    ws.cell(row=tr, column=8, value=round(total_geral, 2)).font = Font(bold=True)
    ws.freeze_panes = "A2"
    out = io.BytesIO(); wb.save(out); out.seek(0)
    return out


def _nfe_pdf(dados, mes, ano):
    MESES = ["","Janeiro","Fevereiro","Março","Abril","Maio","Junho",
             "Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"]
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=14, textColor=colors.HexColor("#1E3A34"))
    sub_style   = ParagraphStyle("s", parent=styles["Normal"], fontSize=9,  textColor=colors.grey)
    elements = [
        Paragraph(f"Entradas por NF-e — {MESES[mes]}/{ano}", title_style),
        Paragraph(f"Gerado em {_agora_br().strftime('%d/%m/%Y às %H:%M')}", sub_style),
        Spacer(1, 0.4*cm),
    ]
    tdata = [["NF-e", "Material", "Categoria", "Qtd.", "Un.", "Subtotal", "Data"]]
    total_geral = 0.0
    for r in dados:
        tdata.append([
            r["nf_numero"] or "—", r["material_nome"], r["categoria_nome"],
            str(r["quantidade"]), r["unidade"],
            f'R$ {r["subtotal"]:.2f}' if r["subtotal"] else "—",
            r["criado_em"][:10],
        ])
        total_geral += r["subtotal"] or 0
    tdata.append(["", "", "", "", "TOTAL", f"R$ {total_geral:.2f}", ""])
    cw = [2.5*cm, 4.5*cm, 3*cm, 1.5*cm, 1.2*cm, 2.5*cm, 2.5*cm]
    t  = Table(tdata, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),  (-1,0),  colors.HexColor("#1E3A34")),
        ("TEXTCOLOR",     (0,0),  (-1,0),  colors.white),
        ("FONTNAME",      (0,0),  (-1,0),  "Helvetica-Bold"),
        ("FONTNAME",      (0,-1), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0),  (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),  (-1,-2), [colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",          (0,0),  (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0),  (-1,-1), 4),
        ("RIGHTPADDING",  (0,0),  (-1,-1), 4),
    ]))
    elements += [t, Spacer(1,0.3*cm),
                 Paragraph(f"Total: {len(dados)} item(ns) · © Todos os direitos reservados – github.com/Wbad-02", sub_style)]
    doc.build(elements); out.seek(0)
    return out


@router.get("/entradas-nfe/excel")
def exportar_nfe_excel(
    mes: int, ano: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    dados = _dados_entradas_nfe(db, mes, ano)
    filename = f"nfe_{mes:02d}{ano}_{_agora_br().strftime('%H%M')}.xlsx"
    return StreamingResponse(
        _nfe_excel(dados, mes, ano),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/entradas-nfe/pdf")
def exportar_nfe_pdf(
    mes: int, ano: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    dados = _dados_entradas_nfe(db, mes, ano)
    filename = f"nfe_{mes:02d}{ano}_{_agora_br().strftime('%H%M')}.pdf"
    return StreamingResponse(
        _nfe_pdf(dados, mes, ano),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Exports: Consumo médio ────────────────────────────────────

def _cobertura_label(d):
    if d is None:       return "Sem consumo"
    if d <= 7:          return f"{d} dias (CRITICO)"
    if d <= 30:         return f"{d} dias (ATENCAO)"
    if d <= 60:         return f"{d} dias (MODERADO)"
    return              f"{d} dias (OK)"

def _cobertura_fill(d):
    if d is None:       return None
    if d <= 7:          return PatternFill("solid", fgColor="FCE4EC")
    if d <= 30:         return PatternFill("solid", fgColor="FFF3E0")
    if d <= 60:         return PatternFill("solid", fgColor="FFFDE7")
    return                     PatternFill("solid", fgColor="E8F5E9")

def _cobertura_color_pdf(d):
    if d is None:       return colors.grey
    if d <= 7:          return colors.HexColor("#c62828")
    if d <= 30:         return colors.HexColor("#e65100")
    if d <= 60:         return colors.HexColor("#f9a825")
    return                     colors.HexColor("#2e7d32")


@router.get("/consumo-medio/excel")
def exportar_consumo_excel(
    meses: int = 3,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_consumo_medio(db, meses)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Consumo Médio"
    hfill = PatternFill("solid", fgColor="1E3A34")
    hfont = Font(bold=True, color="FFFFFF")
    headers    = ["Material", "Categoria", "Grupo", "Estoque Atual", "Unidade", "Consumo Médio/mês", "Dias de Cobertura", "Status"]
    col_widths = [28, 18, 18, 14, 8, 18, 18, 16]
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font = hfont; c.fill = hfill; c.alignment = Alignment(horizontal="center")
        ws.column_dimensions[c.column_letter].width = w
    for ri, r in enumerate(dados, 2):
        row = [r["material_nome"], r["categoria_nome"], r["grupo_nome"],
               r["estoque_atual"], r["unidade"], r["media_mensal"] if r["media_mensal"] > 0 else None,
               r["dias_cobertura"], _cobertura_label(r["dias_cobertura"])]
        fill = _cobertura_fill(r["dias_cobertura"])
        for ci, v in enumerate(row, 1):
            c = ws.cell(row=ri, column=ci, value=v)
            c.alignment = Alignment(horizontal="left" if ci in (1,2,3,5) else "center")
            if fill: c.fill = fill
    ws.freeze_panes = "A2"
    out = io.BytesIO(); wb.save(out); out.seek(0)
    filename = f"consumo_medio_{_agora_br().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/consumo-medio/pdf")
def exportar_consumo_pdf(
    meses: int = 3,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_consumo_medio(db, meses)
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=14, textColor=colors.HexColor("#1E3A34"))
    sub_style   = ParagraphStyle("s", parent=styles["Normal"], fontSize=9,  textColor=colors.grey)
    elements = [
        Paragraph(f"Consumo Médio & Previsão de Ruptura — últimos {meses} mês(es)", title_style),
        Paragraph(f"Gerado em {_agora_br().strftime('%d/%m/%Y às %H:%M')}", sub_style),
        Spacer(1, 0.4*cm),
    ]
    tdata = [["Material", "Categoria", "Estoque", "Un.", "Cons./mês", "Cobertura"]]
    for r in dados:
        cob = f"{r['dias_cobertura']} dias" if r["dias_cobertura"] is not None else "—"
        tdata.append([
            r["material_nome"], r["categoria_nome"], str(r["estoque_atual"]),
            r["unidade"], str(r["media_mensal"]) if r["media_mensal"] > 0 else "—", cob,
        ])
    cw = [5*cm, 3.5*cm, 2.2*cm, 1.5*cm, 2.5*cm, 2.5*cm]
    t  = Table(tdata, colWidths=cw, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1E3A34")),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",         (0,0), (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ]
    for ri, r in enumerate(dados, 1):
        c = _cobertura_color_pdf(r["dias_cobertura"])
        style_cmds.append(("TEXTCOLOR", (5, ri), (5, ri), c))
        style_cmds.append(("FONTNAME",  (5, ri), (5, ri), "Helvetica-Bold"))
    t.setStyle(TableStyle(style_cmds))
    elements += [t, Spacer(1,0.3*cm),
                 Paragraph(f"Total: {len(dados)} material(is) · © Todos os direitos reservados – github.com/Wbad-02", sub_style)]
    doc.build(elements); out.seek(0)
    filename = f"consumo_medio_{_agora_br().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(out, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})


# ── Exports: Solicitações por material ───────────────────────

@router.get("/solicitacoes-por-material/excel")
def exportar_solicitacoes_excel(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_solicitacoes_material(db)
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Solicitacoes"
    hfill = PatternFill("solid", fgColor="1E3A34")
    hfont = Font(bold=True, color="FFFFFF")
    headers    = ["#", "Material", "Categoria", "Grupo", "Total", "Aprovados", "Rejeitados", "Aguardando", "Taxa Aprv. (%)"]
    col_widths = [5,   28,        18,           18,     8,       12,          12,            12,           16]
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font = hfont; c.fill = hfill; c.alignment = Alignment(horizontal="center")
        ws.column_dimensions[c.column_letter].width = w
    for ri, r in enumerate(dados, 2):
        row = [ri-1, r["material_nome"], r["categoria_nome"], r["grupo_nome"],
               r["total"], r["aprovados"], r["rejeitados"], r["aguardando"], r["taxa_aprovacao"]]
        for ci, v in enumerate(row, 1):
            c = ws.cell(row=ri, column=ci, value=v)
            c.alignment = Alignment(horizontal="left" if ci == 2 else "center")
    ws.freeze_panes = "A2"
    out = io.BytesIO(); wb.save(out); out.seek(0)
    filename = f"solicitacoes_{_agora_br().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/solicitacoes-por-material/pdf")
def exportar_solicitacoes_pdf(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_solicitacoes_material(db)
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=14, textColor=colors.HexColor("#1E3A34"))
    sub_style   = ParagraphStyle("s", parent=styles["Normal"], fontSize=9,  textColor=colors.grey)
    elements = [
        Paragraph("Volume de Solicitações por Material", title_style),
        Paragraph(f"Gerado em {_agora_br().strftime('%d/%m/%Y às %H:%M')}", sub_style),
        Spacer(1, 0.4*cm),
    ]
    tdata = [["#", "Material", "Categoria", "Total", "Aprovados", "Rejeitados", "Aguardando", "Taxa %"]]
    for i, r in enumerate(dados, 1):
        tdata.append([str(i), r["material_nome"], r["categoria_nome"],
                      str(r["total"]), str(r["aprovados"]), str(r["rejeitados"]),
                      str(r["aguardando"]), f'{r["taxa_aprovacao"]:.1f}%'])
    cw = [0.8*cm, 4.5*cm, 3*cm, 1.5*cm, 2*cm, 2*cm, 2*cm, 1.7*cm]
    t  = Table(tdata, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1E3A34")),
        ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
        ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID",         (0,0), (-1,-1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ]))
    elements += [t, Spacer(1,0.3*cm),
                 Paragraph(f"Total: {len(dados)} material(is) · © Todos os direitos reservados – github.com/Wbad-02", sub_style)]
    doc.build(elements); out.seek(0)
    filename = f"solicitacoes_{_agora_br().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(out, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})
