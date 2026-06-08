# © Todos os direitos reservados – github.com/Wbad-02
"""
Router de onboarding: template Excel, preview e importacao em massa de materiais.

Rotas:
  GET  /api/onboarding/template-excel   — baixa planilha modelo (.xlsx)
  POST /api/onboarding/preview-excel    — valida planilha sem gravar
  POST /api/onboarding/importar-excel   — importa materiais da planilha
"""
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

import models
from auth import registrar_log, requer_admin, requer_editor_ou_admin
from database import get_db

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

_MAX_XLSX_BYTES: int = 5 * 1024 * 1024  # 5 MB

_UNIDADES_VALIDAS: list[str] = ["un", "cx", "pc", "m", "l", "kg", "par", "rolo"]


# ── Helpers internos ───────────────────────────────────────────────────────────

def _cell_str(value: object) -> str:
    """Converte valor de celula para string limpa; retorna '' se None."""
    if value is None:
        return ""
    return str(value).strip()


def _parse_float(value: object, default: float = 0.0) -> float:
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"Nao e um numero valido: {value!r}")


def _parse_int(value: object, default: int = 0) -> int:
    f = _parse_float(value, float(default))
    return int(f)


# ── Tarefa 2/3 — parser compartilhado ─────────────────────────────────────────

def _parse_excel(file_bytes: bytes, db: Session) -> dict:
    """
    Le a aba 'Materiais' a partir da linha 3 (linha 1 = cabecalho, linha 2 = exemplo).
    Para ao encontrar a primeira linha completamente vazia nas colunas A-D.

    Retorna:
        {
            "total_linhas": int,
            "linhas_validas": [...],
            "erros": [...],
            "resumo": {...}
        }
    """
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(422, f"Arquivo Excel invalido ou corrompido: {exc}")

    if "Materiais" not in wb.sheetnames:
        raise HTTPException(422, "Aba 'Materiais' nao encontrada na planilha")

    ws = wb["Materiais"]

    linhas_validas: list[dict] = []
    erros: list[dict] = []

    # Caches para evitar queries repetidas por nome
    _cat_cache: dict[str, Optional[models.Categoria]] = {}
    _grp_cache: dict[tuple[str, int], Optional[models.GrupoMaterial]] = {}

    # Contadores de resumo
    cats_novas: set[str] = set()
    grps_novos: set[tuple[str, str]] = set()
    mats_novos: int = 0
    mats_dup: int = 0

    # Indice de linha real na planilha (linha 1 = cabecalho, linha 2 = exemplo)
    # iter_rows min_row=3 => row_idx começa em 3
    for row in ws.iter_rows(min_row=3):
        # Extrair valores das 9 colunas esperadas (A..I)
        vals = [row[i].value if i < len(row) else None for i in range(9)]

        col_a = _cell_str(vals[0])  # categoria
        col_b = _cell_str(vals[1])  # grupo
        col_c = vals[2]             # quantidade_minima_grupo (numerico)
        col_d = _cell_str(vals[3])  # material
        col_e = _cell_str(vals[4])  # descricao
        col_f = vals[5]             # quantidade
        col_g = _cell_str(vals[6])  # unidade
        col_h = vals[7]             # valor_unitario
        col_i = vals[8]             # fator_embalagem

        # Parar na primeira linha totalmente vazia (A-D)
        if not col_a and not col_b and not _cell_str(vals[3]) and col_d == "":
            # Verificacao mais segura: A, B, D todos vazios
            if not col_a and not col_b and not col_d:
                break

        # Numero da linha para reportar ao usuario (planilha: linha 1-based)
        # row[0].row e o numero de linha na planilha
        linha_num: int = row[0].row if row else 0

        campo_erros: list[dict] = []

        # ── Validacoes de campos obrigatorios ──
        if not col_a:
            campo_erros.append({"linha": linha_num, "campo": "categoria", "mensagem": "Campo obrigatorio vazio"})
        if not col_b:
            campo_erros.append({"linha": linha_num, "campo": "grupo", "mensagem": "Campo obrigatorio vazio"})
        if not col_d:
            campo_erros.append({"linha": linha_num, "campo": "material", "mensagem": "Campo obrigatorio vazio"})

        # ── quantidade ──
        try:
            quantidade = _parse_int(col_f, 0)
            if quantidade < 0:
                campo_erros.append({
                    "linha": linha_num,
                    "campo": "quantidade",
                    "mensagem": f"Valor negativo ({quantidade})",
                })
        except ValueError:
            quantidade = 0
            campo_erros.append({
                "linha": linha_num,
                "campo": "quantidade",
                "mensagem": f"Nao e um numero inteiro valido: {col_f!r}",
            })

        # ── quantidade_minima_grupo ──
        try:
            qtd_min_grupo = _parse_int(col_c, 0)
            if qtd_min_grupo < 0:
                qtd_min_grupo = 0
        except ValueError:
            qtd_min_grupo = 0

        # ── valor_unitario ──
        try:
            valor_unitario: Optional[float] = _parse_float(col_h, 0.0) if col_h is not None else None
        except ValueError:
            valor_unitario = None
            campo_erros.append({
                "linha": linha_num,
                "campo": "valor_unitario",
                "mensagem": f"Nao e um numero valido: {col_h!r}",
            })

        # ── fator_embalagem ──
        try:
            fator_embalagem = max(1, _parse_int(col_i, 1))
        except ValueError:
            fator_embalagem = 1

        # ── unidade ──
        unidade = col_g.lower() if col_g else "un"
        if unidade not in _UNIDADES_VALIDAS:
            unidade = "un"

        # Se ha erros obrigatorios, registrar e pular
        if campo_erros:
            erros.extend(campo_erros)
            continue

        # ── Consultas ao banco ──
        cat_nome = col_a
        grp_nome = col_b
        mat_nome = col_d

        # Categoria
        if cat_nome not in _cat_cache:
            _cat_cache[cat_nome] = (
                db.query(models.Categoria)
                .filter(models.Categoria.nome.ilike(cat_nome))
                .first()
            )
        cat_obj = _cat_cache[cat_nome]
        cat_nova = cat_obj is None

        # Para determinar grupo, precisamos de um categoria_id candidato
        # Se cat nova, id ainda nao existe — representamos como None para lookup
        cat_id_lookup: Optional[int] = cat_obj.id if cat_obj else None

        grp_key = (grp_nome.lower(), cat_id_lookup if cat_id_lookup is not None else -1)
        if grp_key not in _grp_cache:
            if cat_id_lookup is not None:
                _grp_cache[grp_key] = (
                    db.query(models.GrupoMaterial)
                    .filter(
                        models.GrupoMaterial.categoria_id == cat_id_lookup,
                        models.GrupoMaterial.nome.ilike(grp_nome),
                    )
                    .first()
                )
            else:
                # Categoria nova => grupo tambem novo
                _grp_cache[grp_key] = None
        grp_obj = _grp_cache[grp_key]
        grp_novo = grp_obj is None

        # Material
        status_mat: str
        if grp_obj is not None:
            mat_existente = (
                db.query(models.Material)
                .filter(
                    models.Material.grupo_id == grp_obj.id,
                    models.Material.nome.ilike(mat_nome),
                    models.Material.ativo == True,
                )
                .first()
            )
            status_mat = "duplicado" if mat_existente else "novo"
        else:
            # Grupo nao existe => material necessariamente novo
            status_mat = "novo"

        # Acumular resumo
        if cat_nova:
            cats_novas.add(cat_nome.lower())
        if grp_novo:
            grps_novos.add((cat_nome.lower(), grp_nome.lower()))
        if status_mat == "novo":
            mats_novos += 1
        else:
            mats_dup += 1

        linhas_validas.append({
            "linha":                 linha_num,
            "categoria":             cat_nome,
            "grupo":                 grp_nome,
            "quantidade_minima_grupo": qtd_min_grupo,
            "material":              mat_nome,
            "descricao":             col_e,
            "quantidade":            quantidade,
            "unidade":               unidade,
            "valor_unitario":        valor_unitario,
            "fator_embalagem":       fator_embalagem,
            "status":                status_mat,
        })

    wb.close()

    return {
        "total_linhas": len(linhas_validas) + len(erros),
        "linhas_validas": linhas_validas,
        "erros": erros,
        "resumo": {
            "categorias_novas":    len(cats_novas),
            "grupos_novos":        len(grps_novos),
            "materiais_novos":     mats_novos,
            "materiais_duplicados": mats_dup,
        },
    }


# ── Tarefa 1 — GET /template-excel ────────────────────────────────────────────

@router.get("/template-excel")
def baixar_template_excel(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
) -> StreamingResponse:
    """Gera e retorna planilha modelo para importacao de materiais em massa."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()

    # ── Aba 1: Materiais ───────────────────────────────────────────────────────
    ws_mat = wb.active
    ws_mat.title = "Materiais"

    fill_header  = PatternFill("solid", fgColor="1B3A2D")
    fill_exemplo = PatternFill("solid", fgColor="E8E8E8")
    font_header  = Font(bold=True, color="FFFFFF", size=11)
    font_exemplo = Font(size=10, italic=True, color="666666")
    al_center    = Alignment(horizontal="center", vertical="center", wrap_text=True)
    al_left      = Alignment(horizontal="left",   vertical="center")

    cabecalhos = [
        "categoria",
        "grupo",
        "quantidade_minima_grupo",
        "material",
        "descricao",
        "quantidade",
        "unidade",
        "valor_unitario",
        "fator_embalagem",
    ]
    for col_idx, titulo in enumerate(cabecalhos, start=1):
        cell = ws_mat.cell(row=1, column=col_idx, value=titulo)
        cell.font      = font_header
        cell.fill      = fill_header
        cell.alignment = al_center
    ws_mat.row_dimensions[1].height = 20

    # Linha 2: exemplo em cinza claro
    exemplos = [
        "Informatica",
        "Perifericos",
        0,
        "Mouse USB",
        "Mouse optico USB sem fio",
        10,
        "un",
        45.90,
        1,
    ]
    for col_idx, valor in enumerate(exemplos, start=1):
        cell = ws_mat.cell(row=2, column=col_idx, value=valor)
        cell.font      = font_exemplo
        cell.fill      = fill_exemplo
        cell.alignment = al_left

    # Linhas 3-502: area vazia (500 linhas)
    # Nao e necessario preencher — o freeze e as validacoes cobrem o range

    # Data validation: coluna G (unidade) — dropdown
    dv_unidade = DataValidation(
        type="list",
        formula1='"un,cx,pc,m,l,kg,par,rolo"',
        allow_blank=True,
        showDropDown=False,
        showErrorMessage=True,
        errorTitle="Unidade invalida",
        error="Selecione uma unidade da lista: un, cx, pc, m, l, kg, par, rolo",
    )
    dv_unidade.sqref = "G3:G502"
    ws_mat.add_data_validation(dv_unidade)

    # Data validation: coluna F (quantidade) — inteiro >= 0
    dv_qtd = DataValidation(
        type="whole",
        operator="greaterThanOrEqual",
        formula1="0",
        allow_blank=True,
        showErrorMessage=True,
        errorTitle="Quantidade invalida",
        error="Informe um numero inteiro maior ou igual a 0",
    )
    dv_qtd.sqref = "F3:F502"
    ws_mat.add_data_validation(dv_qtd)

    # Congelar linha 1 (cabecalho visivel ao rolar)
    ws_mat.freeze_panes = "A3"

    # Larguras de colunas
    larguras = {
        "A": 20,  # categoria
        "B": 20,  # grupo
        "C": 24,  # quantidade_minima_grupo
        "D": 28,  # material
        "E": 32,  # descricao
        "F": 14,  # quantidade
        "G": 12,  # unidade
        "H": 18,  # valor_unitario
        "I": 16,  # fator_embalagem
    }
    for col_letra, largura in larguras.items():
        ws_mat.column_dimensions[col_letra].width = largura

    # ── Aba 2: Instrucoes ──────────────────────────────────────────────────────
    ws_inst = wb.create_sheet("Instrucoes")
    ws_inst.protection.sheet = True

    font_titulo  = Font(bold=True, size=13, color="1B3A2D")
    font_subtit  = Font(bold=True, size=11)
    font_normal_inst = Font(size=10)
    al_left_inst = Alignment(horizontal="left", vertical="center", wrap_text=True)

    instrucoes: list[tuple[Optional[str], str]] = [
        ("INSTRUCOES DE PREENCHIMENTO", ""),
        (None, "Preencha a aba 'Materiais' a partir da linha 3. A linha 2 e apenas um exemplo e sera ignorada."),
        (None, ""),
        ("CAMPOS OBRIGATORIOS", ""),
        ("categoria", "Nome da categoria do material (ex: Informatica, Limpeza). Sera criada se nao existir."),
        ("grupo", "Nome do grupo dentro da categoria (ex: Perifericos, Cabos). Sera criado se nao existir."),
        ("material", "Nome do material. Se ja existir no mesmo grupo, sera tratado como duplicata."),
        (None, ""),
        ("CAMPOS OPCIONAIS", ""),
        ("quantidade_minima_grupo", "Quantidade minima de alerta para o grupo. Use 0 para desativar. Padrao: 0."),
        ("descricao", "Descricao livre do material."),
        ("quantidade", "Quantidade inicial em estoque. Use 0 para cadastrar sem estoque. Deve ser inteiro >= 0."),
        ("unidade", "Unidade de medida. Valores aceitos: un, cx, pc, m, l, kg, par, rolo. Padrao: un."),
        ("valor_unitario", "Valor unitario em reais (ex: 45.90). Deixe vazio se nao souber."),
        ("fator_embalagem", "Fator de conversao de embalagem para unidades. Padrao: 1."),
        (None, ""),
        ("REGRAS DE PREENCHIMENTO", ""),
        (None, "1. Nao altere o cabecalho da linha 1."),
        (None, "2. Nao insira dados na linha 2 (e um exemplo)."),
        (None, "3. Linhas em branco interrompem a leitura — nao deixe linhas vazias entre registros."),
        (None, "4. Texto em maiusculas ou minusculas sao tratados da mesma forma."),
        (None, "5. Categorias e grupos novos serao criados automaticamente durante a importacao."),
        (None, "6. Materiais com mesmo nome no mesmo grupo sao considerados duplicatas."),
        (None, "7. Maximo de 500 linhas de dados por arquivo."),
    ]

    for i, (chave, valor) in enumerate(instrucoes, start=1):
        if chave and not valor:
            # Titulo de secao
            cell = ws_inst.cell(row=i, column=1, value=chave)
            cell.font = font_titulo
        elif chave:
            # Nome do campo
            cell_k = ws_inst.cell(row=i, column=1, value=chave)
            cell_k.font = font_subtit
            cell_k.alignment = al_left_inst
            cell_v = ws_inst.cell(row=i, column=2, value=valor)
            cell_v.font = font_normal_inst
            cell_v.alignment = al_left_inst
        else:
            # Linha descritiva sem chave
            cell = ws_inst.cell(row=i, column=1, value=valor)
            cell.font = font_normal_inst
            cell.alignment = al_left_inst

        ws_inst.row_dimensions[i].height = 16

    ws_inst.column_dimensions["A"].width = 28
    ws_inst.column_dimensions["B"].width = 70

    # ── Aba 3: Categorias_e_Grupos ─────────────────────────────────────────────
    ws_cat = wb.create_sheet("Categorias_e_Grupos")

    categorias = db.query(models.Categoria).order_by(models.Categoria.nome).all()

    if not categorias:
        ws_cat.cell(row=1, column=1, value="Nenhuma categoria cadastrada ainda.")
    else:
        fill_cab_cat = PatternFill("solid", fgColor="1B3A2D")
        font_cab_cat = Font(bold=True, color="FFFFFF", size=11)
        cab_cat = ["Categoria", "Grupo", "Qtd Minima"]
        for col_idx, titulo in enumerate(cab_cat, start=1):
            cell = ws_cat.cell(row=1, column=col_idx, value=titulo)
            cell.font      = font_cab_cat
            cell.fill      = fill_cab_cat
            cell.alignment = Alignment(horizontal="center", vertical="center")

        linha_cat = 2
        for cat in categorias:
            grupos = (
                db.query(models.GrupoMaterial)
                .filter(models.GrupoMaterial.categoria_id == cat.id)
                .order_by(models.GrupoMaterial.nome)
                .all()
            )
            if not grupos:
                ws_cat.cell(row=linha_cat, column=1, value=cat.nome)
                ws_cat.cell(row=linha_cat, column=2, value="(sem grupos)")
                ws_cat.cell(row=linha_cat, column=3, value=0)
                linha_cat += 1
            else:
                for grp in grupos:
                    ws_cat.cell(row=linha_cat, column=1, value=cat.nome)
                    ws_cat.cell(row=linha_cat, column=2, value=grp.nome)
                    ws_cat.cell(row=linha_cat, column=3, value=int(grp.quantidade_minima or 0))
                    linha_cat += 1

        ws_cat.column_dimensions["A"].width = 24
        ws_cat.column_dimensions["B"].width = 24
        ws_cat.column_dimensions["C"].width = 14

    # ── Serializar e retornar ──────────────────────────────────────────────────
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=modelo_importacao_estoque.xlsx"},
    )


# ── Tarefa 2 — POST /preview-excel ────────────────────────────────────────────

@router.post("/preview-excel")
async def preview_excel(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
) -> dict:
    """Valida a planilha e retorna preview sem gravar nada no banco."""
    contents = await arquivo.read()
    if len(contents) > _MAX_XLSX_BYTES:
        raise HTTPException(413, "Arquivo muito grande (maximo 5 MB)")

    resultado = _parse_excel(contents, db)
    return resultado


# ── Tarefa 3 — POST /importar-excel ───────────────────────────────────────────

@router.post("/importar-excel")
async def importar_excel(
    arquivo:        UploadFile = File(...),
    modo_duplicata: str        = Form("ignorar"),
    db:             Session    = Depends(get_db),
    atual:          models.Usuario = Depends(requer_admin),
) -> JSONResponse:
    """
    Importa materiais da planilha para o banco.

    modo_duplicata:
      "ignorar"   — pula material ja existente no grupo
      "atualizar" — soma quantidade ao existente, preenche campos vazios
    """
    if modo_duplicata not in ("ignorar", "atualizar"):
        raise HTTPException(400, "modo_duplicata deve ser 'ignorar' ou 'atualizar'")

    contents = await arquivo.read()
    if len(contents) > _MAX_XLSX_BYTES:
        raise HTTPException(413, "Arquivo muito grande (maximo 5 MB)")

    parse_result = _parse_excel(contents, db)

    if not parse_result["linhas_validas"] and parse_result["erros"]:
        raise HTTPException(422, "Planilha sem linhas validas para importar")

    linhas = parse_result["linhas_validas"]

    # Contadores de resultado
    cats_criadas: int = 0
    grps_criados: int = 0
    mats_criados: int = 0
    ignorados: list[dict] = []
    erros_import: list[dict] = []

    # ── Passo 1: criar categorias novas ───────────────────────────────────────
    # Mapeia nome_lower -> objeto Categoria (existente ou recem-criado)
    cat_map: dict[str, models.Categoria] = {}

    for linha in linhas:
        cat_nome: str = linha["categoria"]
        cat_key = cat_nome.lower()
        if cat_key in cat_map:
            continue
        existente = (
            db.query(models.Categoria)
            .filter(models.Categoria.nome.ilike(cat_nome))
            .first()
        )
        if existente:
            cat_map[cat_key] = existente
        else:
            nova_cat = models.Categoria(nome=cat_nome)
            db.add(nova_cat)
            try:
                db.flush()
                cat_map[cat_key] = nova_cat
                cats_criadas += 1
            except Exception as exc:
                db.rollback()
                erros_import.append({
                    "linha": linha["linha"],
                    "campo": "categoria",
                    "mensagem": f"Erro ao criar categoria '{cat_nome}': {exc}",
                })
                continue

    # ── Passo 2: criar grupos novos ────────────────────────────────────────────
    # Mapeia (cat_key, grp_key) -> objeto GrupoMaterial
    grp_map: dict[tuple[str, str], models.GrupoMaterial] = {}

    for linha in linhas:
        cat_key = linha["categoria"].lower()
        grp_nome: str = linha["grupo"]
        grp_key = grp_nome.lower()
        mapa_key = (cat_key, grp_key)

        if mapa_key in grp_map:
            continue

        if cat_key not in cat_map:
            # Categoria nao foi criada (erro anterior) — pular grupo
            continue

        cat_obj = cat_map[cat_key]
        existente_grp = (
            db.query(models.GrupoMaterial)
            .filter(
                models.GrupoMaterial.categoria_id == cat_obj.id,
                models.GrupoMaterial.nome.ilike(grp_nome),
            )
            .first()
        )
        if existente_grp:
            grp_map[mapa_key] = existente_grp
        else:
            qtd_min = linha["quantidade_minima_grupo"]
            novo_grp = models.GrupoMaterial(
                nome=grp_nome,
                categoria_id=cat_obj.id,
                quantidade_minima=float(qtd_min),
            )
            db.add(novo_grp)
            try:
                db.flush()
                grp_map[mapa_key] = novo_grp
                grps_criados += 1
            except Exception as exc:
                db.rollback()
                erros_import.append({
                    "linha": linha["linha"],
                    "campo": "grupo",
                    "mensagem": f"Erro ao criar grupo '{grp_nome}': {exc}",
                })
                continue

    # ── Passo 3: criar/atualizar materiais ────────────────────────────────────
    for linha in linhas:
        cat_key = linha["categoria"].lower()
        grp_key_inner = linha["grupo"].lower()
        mapa_key = (cat_key, grp_key_inner)
        mat_nome: str = linha["material"]
        linha_num: int = linha["linha"]

        if mapa_key not in grp_map:
            erros_import.append({
                "linha": linha_num,
                "campo": "grupo",
                "mensagem": f"Grupo '{linha['grupo']}' nao disponivel (erro em etapa anterior)",
            })
            continue

        grp_obj = grp_map[mapa_key]

        try:
            existente_mat = (
                db.query(models.Material)
                .filter(
                    models.Material.grupo_id == grp_obj.id,
                    models.Material.nome.ilike(mat_nome),
                    models.Material.ativo == True,
                )
                .first()
            )

            if existente_mat:
                if modo_duplicata == "ignorar":
                    ignorados.append({
                        "linha":   linha_num,
                        "material": mat_nome,
                        "motivo":  "Material ja existe no grupo",
                    })
                    continue
                else:
                    # Modo "atualizar": soma quantidade, preenche campos vazios
                    qtd_adicionada: int = linha["quantidade"]
                    if qtd_adicionada > 0:
                        existente_mat.quantidade = (existente_mat.quantidade or 0.0) + qtd_adicionada
                    if not existente_mat.descricao and linha["descricao"]:
                        existente_mat.descricao = linha["descricao"]
                    if not existente_mat.valor_unitario and linha["valor_unitario"]:
                        existente_mat.valor_unitario = linha["valor_unitario"]
                    db.flush()

                    if qtd_adicionada > 0:
                        mov = models.Movimentacao(
                            material_id=existente_mat.id,
                            usuario_id=atual.id,
                            tipo="entrada",
                            quantidade=float(qtd_adicionada),
                            valor_unitario=linha["valor_unitario"],
                            observacao="Importacao inicial via planilha",
                        )
                        db.add(mov)
                        db.flush()
            else:
                # Material novo
                novo_mat = models.Material(
                    nome=mat_nome,
                    descricao=linha["descricao"] or None,
                    quantidade=float(linha["quantidade"]),
                    unidade=linha["unidade"],
                    grupo_id=grp_obj.id,
                    valor_unitario=linha["valor_unitario"],
                    fator_embalagem=float(linha["fator_embalagem"]),
                    ativo=True,
                )
                db.add(novo_mat)
                db.flush()
                mats_criados += 1

                if linha["quantidade"] > 0:
                    mov = models.Movimentacao(
                        material_id=novo_mat.id,
                        usuario_id=atual.id,
                        tipo="entrada",
                        quantidade=float(linha["quantidade"]),
                        valor_unitario=linha["valor_unitario"],
                        observacao="Importacao inicial via planilha",
                    )
                    db.add(mov)
                    db.flush()

        except Exception as exc:
            db.rollback()
            erros_import.append({
                "linha":     linha_num,
                "campo":     "material",
                "mensagem":  f"Erro inesperado ao processar '{mat_nome}': {exc}",
            })
            continue

    db.commit()

    detalhe_log = (
        f"categorias={cats_criadas} grupos={grps_criados} "
        f"materiais={mats_criados} ignorados={len(ignorados)} "
        f"erros={len(erros_import)} modo={modo_duplicata}"
    )
    registrar_log(
        db,
        atual.id,
        "importacao_excel",
        "onboarding",
        None,
        detalhe_log,
    )

    payload = {
        "sucesso":   True,
        "criados":   {
            "categorias": cats_criadas,
            "grupos":     grps_criados,
            "materiais":  mats_criados,
        },
        "ignorados": ignorados,
        "erros":     erros_import,
    }

    status_code = 207 if erros_import else 200
    return JSONResponse(content=payload, status_code=status_code)
