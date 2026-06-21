# © Todos os direitos reservados – github.com/Wbad-02
import io
from models import agora as _agora_br
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
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


def _parse_data(valor: str | None):
    if not valor:
        return None
    try:
        from datetime import datetime as dt
        return dt.fromisoformat(valor)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data inválida: '{valor}'. Use formato AAAA-MM-DD.")


def _obter_materiais(db: Session, apenas_alertas: bool):
    mats = (
        db.query(models.Material)
        .options(
            joinedload(models.Material.grupo)
                .joinedload(models.GrupoMaterial.categoria),
            joinedload(models.Material.grupo)
                .joinedload(models.GrupoMaterial.materiais),
        )
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
            str(int(m.quantidade)),
            m.unidade,
            str(int(m.grupo.quantidade_minima)),
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
    q = (
        db.query(models.Movimentacao)
        .options(
            joinedload(models.Movimentacao.material)
                .joinedload(models.Material.grupo)
                .joinedload(models.GrupoMaterial.categoria),
            joinedload(models.Movimentacao.usuario),
        )
        .filter(models.Movimentacao.tipo == "saida")
    )
    if motivo:
        q = q.filter(models.Movimentacao.motivo == motivo)
    dt_inicio = _parse_data(data_inicio)
    if dt_inicio:
        q = q.filter(models.Movimentacao.criado_em >= dt_inicio)
    dt_fim = _parse_data(data_fim)
    if dt_fim:
        from datetime import datetime as dt
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
    q = (
        db.query(models.Movimentacao)
        .options(
            joinedload(models.Movimentacao.material)
                .joinedload(models.Material.grupo)
                .joinedload(models.GrupoMaterial.categoria),
            joinedload(models.Movimentacao.usuario),
        )
        .filter(models.Movimentacao.tipo == "saida")
    )
    if motivo:
        q = q.filter(models.Movimentacao.motivo == motivo)
    dt_inicio = _parse_data(data_inicio)
    if dt_inicio:
        q = q.filter(models.Movimentacao.criado_em >= dt_inicio)
    dt_fim = _parse_data(data_fim)
    if dt_fim:
        from datetime import datetime as dt
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
            str(int(r.quantidade)),
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


# ── Relatório de Ativos (hierárquico) ────────────────────────

def _dados_ativos_hierarquico(db: Session, status: str | None):
    q = (
        db.query(models.Ativo)
        .options(
            joinedload(models.Ativo.grupo).joinedload(models.AtivoGrupo.categoria),
            joinedload(models.Ativo.itens).joinedload(models.AtivoItem.material)
                .joinedload(models.Material.grupo).joinedload(models.GrupoMaterial.categoria),
            joinedload(models.Ativo.itens).joinedload(models.AtivoItem.unidade_patr),
        )
    )
    if status == "ativo":
        q = q.filter(models.Ativo.ativo == True)
    elif status == "inativo":
        q = q.filter(models.Ativo.ativo == False)
    ativos = q.order_by(models.Ativo.nome).all()

    tree: dict = {}
    for a in ativos:
        cat_nome = a.grupo.categoria.nome if a.grupo and a.grupo.categoria else "Sem categoria"
        grp_nome = a.grupo.nome if a.grupo else "Sem grupo"
        itens_ativos = [i for i in a.itens if i.devolvido_em is None]

        materiais = []
        for i in itens_ativos:
            mat = i.material
            mat_cat = mat.grupo.categoria.nome if mat and mat.grupo and mat.grupo.categoria else "—"
            mat_grp = mat.grupo.nome if mat and mat.grupo else "—"
            materiais.append({
                "nome": mat.nome if mat else "—",
                "categoria_grupo": f"{mat_cat} / {mat_grp}",
                "codigo_patrimonio": i.unidade_patr.codigo if i.unidade_patr else "—",
                "data_atribuicao": i.atribuido_em.strftime("%d/%m/%Y") if i.atribuido_em else "—",
                "observacao": i.observacao or "—",
            })

        ativo_data = {
            "id": a.id,
            "nome": a.nome,
            "descricao": a.descricao or "",
            "status": "Ativo" if a.ativo else "Inativo",
            "materiais": materiais,
        }

        tree.setdefault(cat_nome, {})
        tree[cat_nome].setdefault(grp_nome, [])
        tree[cat_nome][grp_nome].append(ativo_data)

    return tree


def _flat_rows_ativos(tree: dict):
    rows = []
    for cat_nome, grupos in sorted(tree.items()):
        for grp_nome, ativos_list in sorted(grupos.items()):
            for a in ativos_list:
                if a["materiais"]:
                    for m in a["materiais"]:
                        rows.append((
                            cat_nome, grp_nome, a["nome"], a["status"],
                            m["nome"], m["categoria_grupo"],
                            m["codigo_patrimonio"], m["data_atribuicao"],
                            m["observacao"],
                        ))
                else:
                    rows.append((
                        cat_nome, grp_nome, a["nome"], a["status"],
                        "— sem materiais —", "—", "—", "—", "—",
                    ))
    return rows


@router.get("/ativos")
def relatorio_ativos_json(
    status: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    return _dados_ativos_hierarquico(db, status)


@router.get("/ativos/excel")
def exportar_ativos_excel(
    status: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    tree = _dados_ativos_hierarquico(db, status)
    rows = _flat_rows_ativos(tree)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ativos"
    header_fill = PatternFill("solid", fgColor="1E3A34")
    header_font = Font(bold=True, color="FFFFFF")
    cat_fill = PatternFill("solid", fgColor="E8F0ED")
    cat_font = Font(bold=True, color="1E3A34", size=11)

    headers = [
        "Categoria Ativo", "Grupo Ativo", "Ativo", "Status",
        "Material", "Categoria / Grupo Material", "Patrimônio",
        "Data Atribuição", "Observação",
    ]
    col_widths = [18, 16, 22, 10, 28, 22, 14, 16, 24]
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = w

    prev_cat = prev_grp = prev_ativo = None
    ri = 2
    for row in rows:
        cat, grp, ativo_nome = row[0], row[1], row[2]

        if prev_ativo is not None and ativo_nome != prev_ativo:
            ri += 1

        display = list(row)
        if cat == prev_cat:
            display[0] = ""
        if cat == prev_cat and grp == prev_grp:
            display[1] = ""
        if cat == prev_cat and grp == prev_grp and ativo_nome == prev_ativo:
            display[2] = ""
            display[3] = ""
        prev_cat, prev_grp, prev_ativo = cat, grp, ativo_nome

        for ci, val in enumerate(display, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.alignment = Alignment(horizontal="center" if ci in (3,4,7,8) else "left")
        ri += 1

    ws.freeze_panes = "A2"
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
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
    from reportlab.lib.pagesizes import landscape
    tree = _dados_ativos_hierarquico(db, status)
    rows = _flat_rows_ativos(tree)

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=1*cm, rightMargin=1*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=14, textColor=colors.HexColor("#1E3A34"))
    sub_style = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    cell_style = ParagraphStyle("c", parent=styles["Normal"], fontSize=8)

    elements = []
    titulo = "Relatório de Ativos"
    if status == "ativo":
        titulo += " — Somente Ativos"
    elif status == "inativo":
        titulo += " — Somente Inativos"
    elements.append(Paragraph(titulo, title_style))
    elements.append(Paragraph(f"Gerado em {_agora_br().strftime('%d/%m/%Y às %H:%M')}", sub_style))
    elements.append(Spacer(1, 0.4 * cm))

    table_headers = ["Cat. Ativo", "Grupo", "Ativo", "Material", "Cat./Grupo Mat.", "Patrimônio", "Data", "Obs."]
    table_data = [table_headers]
    prev_cat = prev_grp = prev_ativo = None
    for row in rows:
        cat, grp, ativo_nome = row[0], row[1], row[2]
        d_cat = cat if cat != prev_cat else ""
        d_grp = grp if not (cat == prev_cat and grp == prev_grp) else ""
        d_ativo = ativo_nome if not (cat == prev_cat and grp == prev_grp and ativo_nome == prev_ativo) else ""
        prev_cat, prev_grp, prev_ativo = cat, grp, ativo_nome
        table_data.append([
            d_cat, d_grp, d_ativo,
            Paragraph(row[4], cell_style), row[5], row[6], row[7],
            Paragraph(row[8], cell_style),
        ])

    cw = [2.5*cm, 2.5*cm, 3.5*cm, 4.5*cm, 3.5*cm, 2.5*cm, 2.2*cm, 4*cm]
    table = Table(table_data, colWidths=cw, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A34")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.3 * cm))
    total_ativos = sum(len(al) for gs in tree.values() for al in gs.values())
    elements.append(Paragraph(
        f"Total: {total_ativos} ativo(s) · © Todos os direitos reservados – github.com/Wbad-02",
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
    from datetime import date
    inicio = date(ano, mes, 1)
    fim = date(ano, mes + 1, 1) if mes < 12 else date(ano + 1, 1, 1)
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
            models.Movimentacao.criado_em >= inicio,
            models.Movimentacao.criado_em < fim,
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


def _dados_relatorio_geral(db: Session):
    from sqlalchemy import func as _f
    atribuidos_map = {
        r.material_id: float(r.total or 0)
        for r in db.query(
            models.AtivoItem.material_id,
            _f.sum(models.AtivoItem.quantidade).label("total"),
        )
        .filter(models.AtivoItem.devolvido_em.is_(None))
        .group_by(models.AtivoItem.material_id)
        .all()
    }
    mats = _obter_materiais(db, apenas_alertas=False)
    resultado = []
    for m in mats:
        estoque = float(m.quantidade)
        atribuidos = atribuidos_map.get(m.id, 0.0)
        resultado.append({
            "material_id":    m.id,
            "material_nome":  m.nome,
            "categoria_nome": m.grupo.categoria.nome if m.grupo and m.grupo.categoria else "",
            "grupo_nome":     m.grupo.nome if m.grupo else "",
            "unidade":        m.unidade,
            "estoque":        estoque,
            "atribuidos":     atribuidos,
            "total":          estoque + atribuidos,
        })
    return resultado


# ── Endpoints JSON ────────────────────────────────────────────

@router.get("/geral")
def relatorio_geral(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    return _dados_relatorio_geral(db)


@router.get("/geral/excel")
def exportar_geral_excel(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_relatorio_geral(db)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Visao Geral"

    header_fill = PatternFill("solid", fgColor="1E3A34")
    header_font = Font(bold=True, color="FFFFFF")
    atrib_fill  = PatternFill("solid", fgColor="DBEAFE")

    headers    = ["Material", "Categoria", "Grupo", "Em Estoque", "Atribuídos", "Total", "Unidade"]
    col_widths = [30, 18, 18, 12, 12, 10, 10]
    for col_idx, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = w

    for row_idx, r in enumerate(dados, 2):
        row_data = [
            r["material_nome"], r["categoria_nome"], r["grupo_nome"],
            r["estoque"], r["atribuidos"], r["total"], r["unidade"],
        ]
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(horizontal="center" if col_idx != 1 else "left")
            if r["atribuidos"] > 0:
                cell.fill = atrib_fill

    tot_row = len(dados) + 2
    ws.cell(row=tot_row, column=1, value="TOTAL").font = Font(bold=True)
    ws.cell(row=tot_row, column=4, value=sum(r["estoque"] for r in dados)).font = Font(bold=True)
    ws.cell(row=tot_row, column=5, value=sum(r["atribuidos"] for r in dados)).font = Font(bold=True)
    ws.cell(row=tot_row, column=6, value=sum(r["total"] for r in dados)).font = Font(bold=True)
    for c in range(1, 8):
        ws.cell(row=tot_row, column=c).alignment = Alignment(horizontal="center" if c != 1 else "left")

    ws.freeze_panes = "A2"
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"visao_geral_{_agora_br().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/geral/pdf")
def exportar_geral_pdf(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_relatorio_geral(db)
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title_geral", parent=styles["Title"],
        fontSize=16, textColor=colors.HexColor("#1E3A34"),
    )
    sub_style = ParagraphStyle(
        "sub_geral", parent=styles["Normal"],
        fontSize=9, textColor=colors.grey,
    )

    elements = []
    elements.append(Paragraph("Relatório Geral — Estoque + Atribuídos", title_style))
    elements.append(Paragraph(
        f"Gerado em {_agora_br().strftime('%d/%m/%Y às %H:%M')}",
        sub_style,
    ))
    elements.append(Spacer(1, 0.5*cm))

    table_data = [["Material", "Categoria", "Grupo", "Estoque", "Atrib.", "Total", "Un."]]
    for r in dados:
        table_data.append([
            r["material_nome"], r["categoria_nome"], r["grupo_nome"],
            str(int(r["estoque"])), str(int(r["atribuidos"])),
            str(int(r["total"])), r["unidade"],
        ])
    table_data.append([
        "TOTAL", "", "",
        str(int(sum(r["estoque"] for r in dados))),
        str(int(sum(r["atribuidos"] for r in dados))),
        str(int(sum(r["total"] for r in dados))),
        "",
    ])

    col_widths_pdf = [5*cm, 3*cm, 3*cm, 2*cm, 2*cm, 1.8*cm, 1.5*cm]
    table = Table(table_data, colWidths=col_widths_pdf, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A34")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F5F5F5")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8E8E8")),
        ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    for row_idx, r in enumerate(dados, 1):
        if r["atribuidos"] > 0:
            table.setStyle(TableStyle([
                ("BACKGROUND", (4, row_idx), (4, row_idx), colors.HexColor("#DBEAFE")),
                ("TEXTCOLOR",  (4, row_idx), (4, row_idx), colors.HexColor("#1565C0")),
            ]))

    elements.append(table)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        f"Total: {len(dados)} material(is) · © Todos os direitos reservados – github.com/Wbad-02",
        sub_style,
    ))

    doc.build(elements)
    output.seek(0)
    filename = f"visao_geral_{_agora_br().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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
            str(int(r["quantidade"])), r["unidade"],
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


# ── Relatório: Valor Imobilizado (detalhado) ─────────────────

from sqlalchemy import func, case
from utils_export import criar_excel, criar_pdf


def _dados_valor_imobilizado(db: Session, categoria_id: int | None, grupo_id: int | None):
    q = (
        db.query(models.AtivoItem)
        .options(
            joinedload(models.AtivoItem.ativo_obj)
                .joinedload(models.Ativo.grupo).joinedload(models.AtivoGrupo.categoria),
            joinedload(models.AtivoItem.material)
                .joinedload(models.Material.grupo).joinedload(models.GrupoMaterial.categoria),
            joinedload(models.AtivoItem.unidade_patr),
        )
        .filter(models.AtivoItem.devolvido_em == None)
    )
    if categoria_id:
        q = (
            q.join(models.Ativo, models.AtivoItem.ativo_id == models.Ativo.id)
            .join(models.AtivoGrupo, models.Ativo.grupo_id == models.AtivoGrupo.id)
            .filter(models.AtivoGrupo.categoria_id == categoria_id)
        )
    if grupo_id:
        if not categoria_id:
            q = (
                q.join(models.Ativo, models.AtivoItem.ativo_id == models.Ativo.id)
                .join(models.AtivoGrupo, models.Ativo.grupo_id == models.AtivoGrupo.id)
            )
        q = q.filter(models.AtivoGrupo.id == grupo_id)

    itens = q.all()

    resultado = []
    total_geral = 0.0
    for i in itens:
        mat = i.material
        ativo = i.ativo_obj
        if i.unidade_patr and i.unidade_patr.valor_unitario:
            valor = i.unidade_patr.valor_unitario
        elif mat and mat.valor_unitario:
            valor = mat.valor_unitario * i.quantidade
        else:
            valor = 0.0
        total_geral += valor

        resultado.append({
            "ativo_nome": ativo.nome if ativo else "—",
            "ativo_categoria": ativo.grupo.categoria.nome if ativo and ativo.grupo and ativo.grupo.categoria else "—",
            "ativo_grupo": ativo.grupo.nome if ativo and ativo.grupo else "—",
            "material_nome": mat.nome if mat else "—",
            "material_categoria_grupo": f"{mat.grupo.categoria.nome} / {mat.grupo.nome}" if mat and mat.grupo and mat.grupo.categoria else "—",
            "codigo_patrimonio": i.unidade_patr.codigo if i.unidade_patr else "—",
            "quantidade": i.quantidade,
            "valor_unitario": round(valor / i.quantidade, 2) if i.quantidade else 0.0,
            "valor_total": round(valor, 2),
            "data_atribuicao": i.atribuido_em.strftime("%d/%m/%Y") if i.atribuido_em else "—",
        })

    resultado.sort(key=lambda r: (r["ativo_categoria"], r["ativo_grupo"], r["ativo_nome"]))
    return resultado, round(total_geral, 2)


@router.get("/valor-imobilizado")
def relatorio_valor_imobilizado_json(
    categoria_id: int | None = Query(None),
    grupo_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados, total = _dados_valor_imobilizado(db, categoria_id, grupo_id)
    return {"itens": dados, "total": total}


@router.get("/valor-imobilizado/excel")
def relatorio_valor_imobilizado_excel(
    categoria_id: int | None = Query(None),
    grupo_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados, total = _dados_valor_imobilizado(db, categoria_id, grupo_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Valor Imobilizado"
    header_fill = PatternFill("solid", fgColor="1E3A34")
    header_font = Font(bold=True, color="FFFFFF")
    money_fmt = '#,##0.00'

    headers = [
        "Ativo", "Cat. Ativo", "Grupo Ativo", "Material",
        "Cat./Grupo Material", "Patrimônio", "Qtd",
        "Valor Unit.", "Valor Total", "Dt Atribuição",
    ]
    col_widths = [22, 16, 16, 28, 20, 14, 8, 14, 14, 14]
    for ci, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = w

    for ri, d in enumerate(dados, 2):
        row_data = [
            d["ativo_nome"], d["ativo_categoria"], d["ativo_grupo"],
            d["material_nome"], d["material_categoria_grupo"],
            d["codigo_patrimonio"], d["quantidade"],
            d["valor_unitario"], d["valor_total"], d["data_atribuicao"],
        ]
        for ci, val in enumerate(row_data, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            if ci in (8, 9):
                cell.number_format = money_fmt
            cell.alignment = Alignment(horizontal="center" if ci in (6, 7, 10) else ("right" if ci in (8, 9) else "left"))

    total_row = len(dados) + 2
    ws.cell(row=total_row, column=8, value="TOTAL").font = Font(bold=True)
    tc = ws.cell(row=total_row, column=9, value=total)
    tc.font = Font(bold=True)
    tc.number_format = money_fmt

    ws.freeze_panes = "A2"
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"valor_imobilizado_{_agora_br().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/valor-imobilizado/pdf")
def relatorio_valor_imobilizado_pdf(
    categoria_id: int | None = Query(None),
    grupo_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    from reportlab.lib.pagesizes import landscape
    dados, total = _dados_valor_imobilizado(db, categoria_id, grupo_id)

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=1*cm, rightMargin=1*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontSize=14, textColor=colors.HexColor("#1E3A34"))
    sub_style = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    cell_style = ParagraphStyle("c", parent=styles["Normal"], fontSize=8)

    elements = [
        Paragraph("Relatório de Valor Imobilizado", title_style),
        Paragraph(f"Gerado em {_agora_br().strftime('%d/%m/%Y às %H:%M')}", sub_style),
        Spacer(1, 0.4*cm),
    ]

    table_data = [["Ativo", "Cat.", "Grupo", "Material", "Patrimônio", "Qtd", "V.Unit.", "V.Total", "Data"]]
    for d in dados:
        table_data.append([
            Paragraph(d["ativo_nome"], cell_style),
            d["ativo_categoria"], d["ativo_grupo"],
            Paragraph(d["material_nome"], cell_style),
            d["codigo_patrimonio"], str(int(d["quantidade"])),
            f"R$ {d['valor_unitario']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"R$ {d['valor_total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            d["data_atribuicao"],
        ])
    table_data.append(["", "", "", "", "", "", "TOTAL",
                       f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), ""])

    cw = [3.5*cm, 2.2*cm, 2.2*cm, 4.5*cm, 2.5*cm, 1.2*cm, 2.5*cm, 2.8*cm, 2.2*cm]
    t = Table(table_data, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A34")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F5F5F5")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8F0ED")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        f"{len(dados)} item(ns) · © Todos os direitos reservados – github.com/Wbad-02",
        sub_style,
    ))
    doc.build(elements)
    output.seek(0)
    filename = f"valor_imobilizado_{_agora_br().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        output, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Relatório: Entradas Gerais (manual + NF-e) ────────────────

def _dados_entradas_gerais(db: Session, data_inicio: str | None, data_fim: str | None):
    from datetime import datetime as dt
    q = (
        db.query(models.Movimentacao)
        .options(
            joinedload(models.Movimentacao.material)
                .joinedload(models.Material.grupo)
                .joinedload(models.GrupoMaterial.categoria),
            joinedload(models.Movimentacao.usuario),
        )
        .filter(models.Movimentacao.tipo == "entrada")
    )
    dt_inicio = _parse_data(data_inicio)
    if dt_inicio:
        q = q.filter(models.Movimentacao.criado_em >= dt_inicio)
    dt_fim = _parse_data(data_fim)
    if dt_fim:
        q = q.filter(models.Movimentacao.criado_em <= dt.fromisoformat(data_fim + "T23:59:59"))
    movs = q.order_by(models.Movimentacao.criado_em.desc()).all()

    resultado = []
    for m in movs:
        mat = m.material
        grp = mat.grupo if mat else None
        cat = grp.categoria if grp else None
        usr = m.usuario
        qtd = m.quantidade or 0.0
        vunit = m.valor_unitario or 0.0
        resultado.append({
            "data": m.criado_em.strftime("%d/%m/%Y %H:%M") if m.criado_em else "—",
            "material": mat.nome if mat else "—",
            "categoria": cat.nome if cat else "—",
            "grupo": grp.nome if grp else "—",
            "quantidade": qtd,
            "unidade": mat.unidade if mat else "—",
            "valor_unitario": vunit,
            "subtotal": round(qtd * vunit, 2),
            "origem": "NF-e" if m.nf_numero else "Manual",
            "nf_numero": m.nf_numero or "—",
            "usuario": usr.nome if usr else "Sistema",
        })
    return resultado


@router.get("/entradas")
def relatorio_entradas_json(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    return _dados_entradas_gerais(db, data_inicio, data_fim)


@router.get("/entradas/excel")
def exportar_entradas_excel(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_entradas_gerais(db, data_inicio, data_fim)
    headers = ["Data", "Material", "Categoria", "Grupo", "Qtd.", "Unidade", "Valor Unit.", "Subtotal", "Origem", "NF-e", "Usuário"]
    col_widths = [18, 28, 18, 18, 8, 8, 14, 14, 10, 14, 18]
    rows = [
        [d["data"], d["material"], d["categoria"], d["grupo"],
         d["quantidade"], d["unidade"], d["valor_unitario"], d["subtotal"],
         d["origem"], d["nf_numero"], d["usuario"]]
        for d in dados
    ]
    total_subtotal = round(sum(d["subtotal"] for d in dados), 2)
    footer = ["", "", "", "", "", "", "TOTAL", total_subtotal, "", "", ""]
    return criar_excel(
        titulo_aba="Entradas",
        headers=headers,
        col_widths=col_widths,
        rows=rows,
        filename_prefix="entradas",
        footer_row=footer,
    )


@router.get("/entradas/pdf")
def exportar_entradas_pdf(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_entradas_gerais(db, data_inicio, data_fim)
    headers = ["Data", "Material", "Categoria", "Qtd.", "Un.", "V.Unit.", "Subtotal", "Origem", "NF-e", "Usuário"]
    col_widths_cm = [2.5, 3.8, 2.5, 1.3, 1.0, 1.8, 2.0, 1.5, 2.2, 2.5]
    rows = [
        [d["data"][:10], d["material"], d["categoria"],
         str(int(d["quantidade"])), d["unidade"],
         f'R$ {d["valor_unitario"]:.2f}' if d["valor_unitario"] else "—",
         f'R$ {d["subtotal"]:.2f}' if d["subtotal"] else "—",
         d["origem"], d["nf_numero"], d["usuario"]]
        for d in dados
    ]
    total_subtotal = round(sum(d["subtotal"] for d in dados), 2)
    footer_text = f"Total: {len(dados)} entrada(s) · Valor total: R$ {total_subtotal:,.2f} · © Todos os direitos reservados – github.com/Wbad-02"
    return criar_pdf(
        titulo="Relatório de Entradas (Manual + NF-e)",
        headers=headers,
        col_widths_cm=col_widths_cm,
        rows=rows,
        filename_prefix="entradas",
        footer_text=footer_text,
        orientacao="landscape",
    )


# ── Relatório: Requerimentos Consolidado ───────────────────────

def _dados_requerimentos(db: Session, data_inicio: str | None, data_fim: str | None):
    from datetime import datetime as dt
    q = (
        db.query(models.Requerimento)
        .options(
            joinedload(models.Requerimento.itens),
            joinedload(models.Requerimento.criador),
            joinedload(models.Requerimento.aprovador),
        )
    )
    dt_inicio = _parse_data(data_inicio)
    if dt_inicio:
        q = q.filter(models.Requerimento.criado_em >= dt_inicio)
    dt_fim = _parse_data(data_fim)
    if dt_fim:
        q = q.filter(models.Requerimento.criado_em <= dt.fromisoformat(data_fim + "T23:59:59"))
    reqs = q.order_by(models.Requerimento.criado_em.desc()).all()

    status_label = {
        models.StatusRequerimento.aguardando: "Aguardando",
        models.StatusRequerimento.aprovado: "Aprovado",
        models.StatusRequerimento.rejeitado: "Rejeitado",
    }

    lista = []
    total_aprovados = 0
    total_rejeitados = 0
    total_aguardando = 0
    valor_total_aprovado = 0.0

    for r in reqs:
        qtd_itens = len(r.itens)
        valor_total = round(sum(i.quantidade * i.valor for i in r.itens), 2)
        status_str = status_label.get(r.status, str(r.status))

        if r.status == models.StatusRequerimento.aprovado:
            total_aprovados += 1
            valor_total_aprovado += valor_total
        elif r.status == models.StatusRequerimento.rejeitado:
            total_rejeitados += 1
        else:
            total_aguardando += 1

        lista.append({
            "titulo": r.titulo,
            "status": status_str,
            "criado_por": r.criador.nome if r.criador else "—",
            "aprovado_por": r.aprovador.nome if r.aprovador else "—",
            "qtd_itens": qtd_itens,
            "valor_total": valor_total,
            "criado_em": r.criado_em.strftime("%d/%m/%Y %H:%M") if r.criado_em else "—",
            "atualizado_em": r.atualizado_em.strftime("%d/%m/%Y %H:%M") if r.atualizado_em else "—",
        })

    totais = {
        "total_requerimentos": len(reqs),
        "total_aprovados": total_aprovados,
        "total_rejeitados": total_rejeitados,
        "total_aguardando": total_aguardando,
        "valor_total_aprovado": round(valor_total_aprovado, 2),
    }
    return lista, totais


@router.get("/requerimentos")
def relatorio_requerimentos_json(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    lista, totais = _dados_requerimentos(db, data_inicio, data_fim)
    return {"requerimentos": lista, **totais}


@router.get("/requerimentos/excel")
def exportar_requerimentos_excel(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    lista, totais = _dados_requerimentos(db, data_inicio, data_fim)
    headers = ["Título", "Status", "Criado por", "Aprovado por", "Qtd. Itens", "Valor Total (R$)", "Criado em", "Atualizado em"]
    col_widths = [30, 14, 18, 18, 12, 18, 18, 18]
    rows = [
        [d["titulo"], d["status"], d["criado_por"], d["aprovado_por"],
         d["qtd_itens"], d["valor_total"], d["criado_em"], d["atualizado_em"]]
        for d in lista
    ]
    footer = [
        f"Total: {totais['total_requerimentos']}",
        f"Aprov: {totais['total_aprovados']}  Rej: {totais['total_rejeitados']}  Ag: {totais['total_aguardando']}",
        "", "", "", totais["valor_total_aprovado"], "", "",
    ]
    return criar_excel(
        titulo_aba="Requerimentos",
        headers=headers,
        col_widths=col_widths,
        rows=rows,
        filename_prefix="requerimentos",
        footer_row=footer,
    )


@router.get("/requerimentos/pdf")
def exportar_requerimentos_pdf(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    lista, totais = _dados_requerimentos(db, data_inicio, data_fim)
    headers = ["Título", "Status", "Criado por", "Aprovado por", "Itens", "Valor (R$)", "Criado em"]
    col_widths_cm = [4.5, 2.2, 3.0, 3.0, 1.5, 2.5, 2.8]
    rows = [
        [d["titulo"], d["status"], d["criado_por"], d["aprovado_por"],
         str(d["qtd_itens"]),
         f'R$ {d["valor_total"]:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."),
         d["criado_em"][:10]]
        for d in lista
    ]
    footer_text = (
        f"Total: {totais['total_requerimentos']} requerimento(s) · "
        f"Aprovados: {totais['total_aprovados']} · Rejeitados: {totais['total_rejeitados']} · "
        f"Aguardando: {totais['total_aguardando']} · "
        f"Valor aprovado: R$ {totais['valor_total_aprovado']:,.2f} · "
        f"© Todos os direitos reservados – github.com/Wbad-02"
    )
    return criar_pdf(
        titulo="Relatório de Requerimentos",
        headers=headers,
        col_widths_cm=col_widths_cm,
        rows=rows,
        filename_prefix="requerimentos",
        footer_text=footer_text,
    )


# ── Relatório: NF-e por Fornecedor ────────────────────────────

def _dados_nfe_fornecedores(db: Session):
    from sqlalchemy import func as _f
    rows = (
        db.query(
            models.NfeImportada.emitente,
            _f.count(models.NfeImportada.chave).label("qtd"),
            _f.max(models.NfeImportada.importado_em).label("ultima_importacao"),
        )
        .group_by(models.NfeImportada.emitente)
        .order_by(_f.count(models.NfeImportada.chave).desc())
        .all()
    )
    resultado = []
    for r in rows:
        resultado.append({
            "fornecedor": r.emitente or "Sem nome",
            "qtd_nfe": int(r.qtd),
            "ultima_importacao": r.ultima_importacao.strftime("%d/%m/%Y %H:%M") if r.ultima_importacao else "—",
        })
    return resultado


@router.get("/nfe-fornecedores")
def relatorio_nfe_fornecedores_json(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    return _dados_nfe_fornecedores(db)


@router.get("/nfe-fornecedores/excel")
def exportar_nfe_fornecedores_excel(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_nfe_fornecedores(db)
    headers = ["Fornecedor", "Qtd. NF-e", "Última Importação"]
    col_widths = [40, 14, 22]
    rows = [
        [d["fornecedor"], d["qtd_nfe"], d["ultima_importacao"]]
        for d in dados
    ]
    footer = [f"Total: {len(dados)} fornecedor(es)", sum(d["qtd_nfe"] for d in dados), ""]
    return criar_excel(
        titulo_aba="NF-e Fornecedores",
        headers=headers,
        col_widths=col_widths,
        rows=rows,
        filename_prefix="nfe_fornecedores",
        footer_row=footer,
    )


@router.get("/nfe-fornecedores/pdf")
def exportar_nfe_fornecedores_pdf(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    dados = _dados_nfe_fornecedores(db)
    headers = ["Fornecedor", "Qtd. NF-e", "Última Importação"]
    col_widths_cm = [9.0, 3.0, 4.5]
    rows = [
        [d["fornecedor"], str(d["qtd_nfe"]), d["ultima_importacao"]]
        for d in dados
    ]
    total_nfe = sum(d["qtd_nfe"] for d in dados)
    footer_text = f"Total: {len(dados)} fornecedor(es) · {total_nfe} NF-e(s) · © Todos os direitos reservados – github.com/Wbad-02"
    return criar_pdf(
        titulo="NF-e por Fornecedor",
        headers=headers,
        col_widths_cm=col_widths_cm,
        rows=rows,
        filename_prefix="nfe_fornecedores",
        footer_text=footer_text,
    )


# ── Relatório: Classificação ABC / Pareto ────────────────────

def _dados_abc(db: Session):
    from datetime import datetime, timedelta
    corte = _agora_br() - timedelta(days=365)
    saidas = (
        db.query(models.Movimentacao)
        .options(
            joinedload(models.Movimentacao.material)
                .joinedload(models.Material.grupo)
                .joinedload(models.GrupoMaterial.categoria),
        )
        .filter(
            models.Movimentacao.tipo == "saida",
            models.Movimentacao.criado_em >= corte,
        )
        .all()
    )

    # Agrupar por material_id
    agrupado: dict = {}
    for s in saidas:
        mid = s.material_id
        if mid not in agrupado:
            mat = s.material
            grp = mat.grupo if mat else None
            cat = grp.categoria if grp else None
            agrupado[mid] = {
                "material_nome": mat.nome if mat else "—",
                "categoria": cat.nome if cat else "—",
                "grupo": grp.nome if grp else "—",
                "qtd_saidas": 0.0,
                "valor_consumido": 0.0,
            }
        agrupado[mid]["qtd_saidas"] += s.quantidade or 0.0
        agrupado[mid]["valor_consumido"] += (s.quantidade or 0.0) * (s.valor_unitario or 0.0)

    # Ordenar por valor consumido desc
    lista = sorted(agrupado.values(), key=lambda x: x["valor_consumido"], reverse=True)

    # Calcular total e percentuais
    total_valor = sum(r["valor_consumido"] for r in lista)
    acumulado = 0.0
    for r in lista:
        r["valor_consumido"] = round(r["valor_consumido"], 2)
        r["qtd_saidas"] = round(r["qtd_saidas"], 2)
        pct = round((r["valor_consumido"] / total_valor) * 100, 2) if total_valor > 0 else 0.0
        acumulado += pct
        r["percentual"] = pct
        r["percentual_acumulado"] = round(acumulado, 2)
        if acumulado <= 80:
            r["classe"] = "A"
        elif acumulado <= 95:
            r["classe"] = "B"
        else:
            r["classe"] = "C"

    totais = {
        "total_itens": len(lista),
        "total_valor_consumido": round(total_valor, 2),
        "total_qtd_saidas": round(sum(r["qtd_saidas"] for r in lista), 2),
        "itens_classe_a": sum(1 for r in lista if r["classe"] == "A"),
        "itens_classe_b": sum(1 for r in lista if r["classe"] == "B"),
        "itens_classe_c": sum(1 for r in lista if r["classe"] == "C"),
    }
    return lista, totais


@router.get("/abc")
def relatorio_abc_json(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    lista, totais = _dados_abc(db)
    return {"itens": lista, **totais}


@router.get("/abc/excel")
def relatorio_abc_excel(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    lista, totais = _dados_abc(db)
    headers = ["Material", "Categoria", "Grupo", "Qtd. Saídas", "Valor Consumido (R$)", "% do Total", "% Acumulado", "Classe"]
    col_widths = [30, 18, 18, 14, 20, 12, 14, 10]
    rows = [
        [r["material_nome"], r["categoria"], r["grupo"],
         r["qtd_saidas"], r["valor_consumido"],
         r["percentual"], r["percentual_acumulado"], r["classe"]]
        for r in lista
    ]
    footer = [
        f"Total: {totais['total_itens']} material(is)",
        "", "",
        totais["total_qtd_saidas"],
        totais["total_valor_consumido"],
        "100%", "",
        f"A:{totais['itens_classe_a']} B:{totais['itens_classe_b']} C:{totais['itens_classe_c']}",
    ]

    def _abc_style(idx, row):
        classe = row[7] if len(row) > 7 else ""
        fills = {
            "A": PatternFill("solid", fgColor="C8E6C9"),
            "B": PatternFill("solid", fgColor="FFF9C4"),
            "C": PatternFill("solid", fgColor="FFCDD2"),
        }
        return {"fill": fills.get(classe), "fmt_5": '#,##0.00', "fmt_6": '0.00"%"', "fmt_7": '0.00"%"'}

    return criar_excel(
        titulo_aba="ABC Pareto",
        headers=headers,
        col_widths=col_widths,
        rows=rows,
        filename_prefix="abc_pareto",
        row_style_fn=_abc_style,
        footer_row=footer,
    )


@router.get("/abc/pdf")
def relatorio_abc_pdf(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    lista, totais = _dados_abc(db)
    headers = ["Material", "Categoria", "Grupo", "Qtd.", "Valor (R$)", "%", "% Acum.", "Classe"]
    col_widths_cm = [4.0, 2.5, 2.5, 1.5, 2.5, 1.5, 1.8, 1.5]
    rows = [
        [r["material_nome"], r["categoria"], r["grupo"],
         str(r["qtd_saidas"]),
         f'R$ {r["valor_consumido"]:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."),
         f'{r["percentual"]:.1f}%',
         f'{r["percentual_acumulado"]:.1f}%',
         r["classe"]]
        for r in lista
    ]

    def _abc_pdf_style(idx, row):
        classe = row[7] if len(row) > 7 else ""
        bgs = {"A": "#C8E6C9", "B": "#FFF9C4", "C": "#FFCDD2"}
        return {"pdf_bg": bgs.get(classe)}

    footer_text = (
        f"Total: {totais['total_itens']} material(is) · "
        f"Valor consumido: R$ {totais['total_valor_consumido']:,.2f} · "
        f"A:{totais['itens_classe_a']} B:{totais['itens_classe_b']} C:{totais['itens_classe_c']} · "
        f"© Todos os direitos reservados – github.com/Wbad-02"
    )
    return criar_pdf(
        titulo="Classificação ABC / Pareto — Últimos 12 meses",
        headers=headers,
        col_widths_cm=col_widths_cm,
        rows=rows,
        filename_prefix="abc_pareto",
        row_style_fn=_abc_pdf_style,
        footer_text=footer_text,
        orientacao="landscape",
    )


# ── Relatório: Atividade por Usuário ─────────────────────────

def _dados_atividade_usuarios(db: Session, meses: int):
    from datetime import datetime, timedelta
    from collections import Counter
    if not (1 <= meses <= 24):
        meses = 3
    corte = _agora_br() - timedelta(days=30 * meses)

    # Consultar logs de auditoria
    logs = (
        db.query(models.LogAuditoria)
        .options(joinedload(models.LogAuditoria.usuario))
        .filter(models.LogAuditoria.criado_em >= corte)
        .all()
    )

    # Agrupar por usuario_id
    por_usuario: dict = {}
    for log in logs:
        uid = log.usuario_id or 0
        if uid not in por_usuario:
            usr = log.usuario
            por_usuario[uid] = {
                "usuario_nome": usr.nome if usr else "Sistema",
                "total_acoes": 0,
                "acoes_por_tipo": Counter(),
                "ultima_acao": None,
            }
        por_usuario[uid]["total_acoes"] += 1
        por_usuario[uid]["acoes_por_tipo"][log.acao] += 1
        if log.criado_em:
            atual = por_usuario[uid]["ultima_acao"]
            if atual is None or log.criado_em > atual:
                por_usuario[uid]["ultima_acao"] = log.criado_em

    # Consultar movimentações do período
    movs = (
        db.query(models.Movimentacao)
        .options(joinedload(models.Movimentacao.usuario))
        .filter(models.Movimentacao.criado_em >= corte)
        .all()
    )
    mov_por_usuario: dict = {}
    for m in movs:
        uid = m.usuario_id or 0
        if uid not in mov_por_usuario:
            mov_por_usuario[uid] = {"entradas": 0, "saidas": 0}
        if m.tipo == "entrada":
            mov_por_usuario[uid]["entradas"] += 1
        elif m.tipo == "saida":
            mov_por_usuario[uid]["saidas"] += 1
        # Garantir que o usuário apareça na lista mesmo sem logs
        if uid not in por_usuario:
            usr = m.usuario
            por_usuario[uid] = {
                "usuario_nome": usr.nome if usr else "Sistema",
                "total_acoes": 0,
                "acoes_por_tipo": Counter(),
                "ultima_acao": None,
            }

    lista = []
    for uid, dados in por_usuario.items():
        mov_data = mov_por_usuario.get(uid, {"entradas": 0, "saidas": 0})
        lista.append({
            "usuario_nome": dados["usuario_nome"],
            "total_acoes": dados["total_acoes"],
            "acoes_por_tipo": dict(dados["acoes_por_tipo"]),
            "entradas": mov_data["entradas"],
            "saidas": mov_data["saidas"],
            "ultima_acao": dados["ultima_acao"].strftime("%d/%m/%Y %H:%M") if dados["ultima_acao"] else "—",
        })

    lista.sort(key=lambda x: x["total_acoes"], reverse=True)
    totais = {
        "total_acoes": sum(r["total_acoes"] for r in lista),
        "total_usuarios_ativos": len(lista),
    }
    return lista, totais


@router.get("/atividade-usuarios")
def relatorio_atividade_usuarios_json(
    meses: int = 3,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    lista, totais = _dados_atividade_usuarios(db, meses)
    return {"usuarios": lista, **totais}


@router.get("/atividade-usuarios/excel")
def relatorio_atividade_usuarios_excel(
    meses: int = 3,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    lista, totais = _dados_atividade_usuarios(db, meses)
    headers = ["Usuário", "Total Ações", "Entradas", "Saídas", "Tipos de Ação", "Última Ação"]
    col_widths = [22, 14, 12, 12, 40, 20]
    rows = [
        [r["usuario_nome"], r["total_acoes"], r["entradas"], r["saidas"],
         ", ".join(f'{k}: {v}' for k, v in r["acoes_por_tipo"].items()) if r["acoes_por_tipo"] else "—",
         r["ultima_acao"]]
        for r in lista
    ]
    footer = [
        f"Total: {totais['total_usuarios_ativos']} usuário(s)",
        totais["total_acoes"],
        sum(r["entradas"] for r in lista),
        sum(r["saidas"] for r in lista),
        "", "",
    ]
    return criar_excel(
        titulo_aba="Atividade Usuarios",
        headers=headers,
        col_widths=col_widths,
        rows=rows,
        filename_prefix="atividade_usuarios",
        footer_row=footer,
    )


@router.get("/atividade-usuarios/pdf")
def relatorio_atividade_usuarios_pdf(
    meses: int = 3,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    lista, totais = _dados_atividade_usuarios(db, meses)
    headers = ["Usuário", "Total Ações", "Entradas", "Saídas", "Tipos de Ação", "Última Ação"]
    col_widths_cm = [3.5, 2.0, 2.0, 2.0, 6.5, 3.0]
    rows = [
        [r["usuario_nome"], str(r["total_acoes"]), str(r["entradas"]), str(r["saidas"]),
         ", ".join(f'{k}: {v}' for k, v in r["acoes_por_tipo"].items()) if r["acoes_por_tipo"] else "—",
         r["ultima_acao"]]
        for r in lista
    ]
    footer_text = (
        f"Total: {totais['total_usuarios_ativos']} usuário(s) · "
        f"{totais['total_acoes']} ação(ões) · "
        f"© Todos os direitos reservados – github.com/Wbad-02"
    )
    return criar_pdf(
        titulo=f"Atividade por Usuário — Últimos {meses} mês(es)",
        headers=headers,
        col_widths_cm=col_widths_cm,
        rows=rows,
        filename_prefix="atividade_usuarios",
        footer_text=footer_text,
        orientacao="landscape",
    )


# ── Relatório: Patrimônio / Inventário ───────────────────────

def _dados_patrimonio(db: Session, status: str):
    q = (
        db.query(models.UnidadePatrimonio)
        .options(
            joinedload(models.UnidadePatrimonio.material)
                .joinedload(models.Material.grupo)
                .joinedload(models.GrupoMaterial.categoria),
        )
    )
    if status == "ativo":
        q = q.filter(models.UnidadePatrimonio.status == models.StatusUnidade.ativo)
    elif status == "retirado":
        q = q.filter(models.UnidadePatrimonio.status == models.StatusUnidade.retirado)

    unidades = q.order_by(models.UnidadePatrimonio.criado_em.asc()).all()

    unidade_ids = [u.id for u in unidades]
    atribuicoes_map = {}
    if unidade_ids:
        atribuicoes = (
            db.query(models.AtivoItem)
            .options(joinedload(models.AtivoItem.ativo_obj))
            .filter(
                models.AtivoItem.unidade_id.in_(unidade_ids),
                models.AtivoItem.devolvido_em == None,
            )
            .all()
        )
        for ai in atribuicoes:
            atribuicoes_map[ai.unidade_id] = ai.ativo_obj.nome if ai.ativo_obj else "—"

    lista = []
    total_ativo = 0
    total_retirado = 0
    total_atribuido = 0
    valor_total_ativo = 0.0

    for u in unidades:
        mat = u.material
        grp = mat.grupo if mat else None
        cat = grp.categoria if grp else None
        is_ativo = u.status == models.StatusUnidade.ativo
        atribuido_a = atribuicoes_map.get(u.id, "—")
        tag_atribuido = (u.tag or "").lower() == "atribuido"

        if atribuido_a != "—" or tag_atribuido:
            total_atribuido += 1
            exibir_status = "atribuído"
        elif is_ativo:
            total_ativo += 1
            valor_total_ativo += u.valor_unitario or 0.0
            exibir_status = "disponível"
        else:
            total_retirado += 1
            exibir_status = "retirado"

        lista.append({
            "codigo": u.codigo or "—",
            "material_nome": mat.nome if mat else "—",
            "categoria": cat.nome if cat else "—",
            "grupo": grp.nome if grp else "—",
            "status": exibir_status,
            "atribuido_a": atribuido_a,
            "origem": u.origem or "—",
            "nf_numero": u.nf_numero or "—",
            "valor_unitario": round(u.valor_unitario, 2) if u.valor_unitario else 0.0,
            "tag": u.tag or "—",
            "criado_em": u.criado_em.strftime("%d/%m/%Y %H:%M") if u.criado_em else "—",
            "retirado_em": u.retirado_em.strftime("%d/%m/%Y %H:%M") if u.retirado_em else "—",
        })

    totais = {
        "total_unidades": len(lista),
        "total_disponivel": total_ativo,
        "total_atribuido": total_atribuido,
        "total_retirado": total_retirado,
        "valor_total_disponivel": round(valor_total_ativo, 2),
    }
    return lista, totais


@router.get("/patrimonio")
def relatorio_patrimonio_json(
    status: str = "ativo",
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    lista, totais = _dados_patrimonio(db, status)
    return {"unidades": lista, **totais}


@router.get("/patrimonio/excel")
def relatorio_patrimonio_excel(
    status: str = "ativo",
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    lista, totais = _dados_patrimonio(db, status)
    headers = ["Código", "Material", "Categoria", "Grupo", "Status", "Atribuído a", "Origem", "NF-e", "Valor Unit. (R$)", "Tag", "Criado em", "Retirado em"]
    col_widths = [14, 26, 16, 16, 12, 20, 10, 14, 16, 10, 16, 16]
    rows = [
        [d["codigo"], d["material_nome"], d["categoria"], d["grupo"],
         d["status"], d["atribuido_a"], d["origem"], d["nf_numero"], d["valor_unitario"],
         d["tag"], d["criado_em"], d["retirado_em"]]
        for d in lista
    ]
    footer = [
        f"Total: {totais['total_unidades']} unidade(s)",
        "", "", "",
        f"Disp: {totais['total_disponivel']}  Atrib: {totais['total_atribuido']}  Ret: {totais['total_retirado']}",
        "", "", "", totais["valor_total_disponivel"],
        "", "", "",
    ]

    def _patrimonio_style(idx, row):
        st = row[4] if len(row) > 4 else ""
        if st == "atribuído":
            return {"fill": PatternFill("solid", fgColor="E3F2FD"), "fmt_9": '#,##0.00'}
        if st == "retirado":
            return {"fill": PatternFill("solid", fgColor="FFCDD2"), "fmt_9": '#,##0.00'}
        return {"fmt_9": '#,##0.00'}

    return criar_excel(
        titulo_aba="Patrimonio",
        headers=headers,
        col_widths=col_widths,
        rows=rows,
        filename_prefix="patrimonio",
        row_style_fn=_patrimonio_style,
        footer_row=footer,
    )


@router.get("/patrimonio/pdf")
def relatorio_patrimonio_pdf(
    status: str = "ativo",
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    lista, totais = _dados_patrimonio(db, status)
    headers = ["Código", "Material", "Cat.", "Grupo", "Status", "Atribuído a", "Origem", "NF-e", "Valor (R$)", "Tag", "Criado", "Retirado"]
    col_widths_cm = [2.0, 3.2, 1.8, 1.8, 1.5, 2.8, 1.3, 1.8, 1.8, 1.2, 2.0, 2.0]
    rows = [
        [d["codigo"], d["material_nome"], d["categoria"], d["grupo"],
         d["status"], d["atribuido_a"], d["origem"], d["nf_numero"],
         f'R$ {d["valor_unitario"]:,.2f}'.replace(",", "X").replace(".", ",").replace("X", ".") if d["valor_unitario"] else "—",
         d["tag"], d["criado_em"][:10] if d["criado_em"] != "—" else "—",
         d["retirado_em"][:10] if d["retirado_em"] != "—" else "—"]
        for d in lista
    ]

    def _patrimonio_pdf_style(idx, row):
        st = row[4] if len(row) > 4 else ""
        if st == "atribuído":
            return {"pdf_bg": "#E3F2FD"}
        if st == "retirado":
            return {"pdf_bg": "#FFCDD2"}
        return {}

    status_label = {"ativo": "Ativos", "retirado": "Retirados", "todos": "Todos"}
    footer_text = (
        f"Total: {totais['total_unidades']} un. · "
        f"Disponível: {totais['total_disponivel']} · Atribuído: {totais['total_atribuido']} · Retirado: {totais['total_retirado']} · "
        f"Valor disponível: R$ {totais['valor_total_disponivel']:,.2f} · "
        f"© Todos os direitos reservados – github.com/Wbad-02"
    )
    return criar_pdf(
        titulo=f"Relatório de Patrimônio — {status_label.get(status, status.title())}",
        headers=headers,
        col_widths_cm=col_widths_cm,
        rows=rows,
        filename_prefix="patrimonio",
        row_style_fn=_patrimonio_pdf_style,
        footer_text=footer_text,
        orientacao="landscape",
    )