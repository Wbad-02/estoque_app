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
from utils import sync_qty

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


# ═══════════════════════════════════════════════════════════════════════════════
# ATIVOS — template, preview, importação e exportação
# ═══════════════════════════════════════════════════════════════════════════════

_COLUNAS_ATIVOS = [
    "categoria_ativo", "grupo_ativo", "nome_ativo", "descricao_ativo",
    "categoria_material", "grupo_material", "nome_material", "descricao_material",
    "quantidade", "unidade", "valor_unitario", "codigo_patrimonio", "observacao",
]

_LARGURAS_ATIVOS = {
    "A": 22, "B": 22, "C": 28, "D": 30,
    "E": 22, "F": 22, "G": 28, "H": 30,
    "I": 12, "J": 12, "K": 16, "L": 20, "M": 30,
}


# ── T1 — parser ────────────────────────────────────────────────────────────────

def _parse_excel_ativos(file_bytes: bytes, db: Session) -> dict:
    """
    Lê a aba 'Ativos' a partir da linha 3.
    Linha 1 = cabeçalho, linha 2 = exemplo.
    Para ao encontrar A+B+C todos vazios.
    Linhas com E+F+G todos vazios são silenciosamente ignoradas.
    """
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(422, f"Arquivo Excel inválido ou corrompido: {exc}")

    if "Ativos" not in wb.sheetnames:
        raise HTTPException(422, "Aba 'Ativos' não encontrada na planilha")

    ws = wb["Ativos"]

    linhas_validas: list[dict] = []
    erros: list[dict] = []

    # caches para evitar queries repetidas
    _acat_cache: dict[str, Optional[models.AtivoCategoria]] = {}
    _agrp_cache: dict[tuple, Optional[models.AtivoGrupo]] = {}
    _ativo_cache: dict[tuple, Optional[models.Ativo]] = {}
    _cat_cache: dict[str, Optional[models.Categoria]] = {}
    _grp_cache: dict[tuple, Optional[models.GrupoMaterial]] = {}
    _mat_cache: dict[tuple, Optional[models.Material]] = {}

    ativos_novos: set = set()
    ativos_existentes: set = set()
    materiais_novos: int = 0
    materiais_existentes: int = 0
    com_patrimonio: int = 0
    sem_patrimonio: int = 0

    for row in ws.iter_rows(min_row=3):
        vals = [row[i].value if i < len(row) else None for i in range(13)]
        col = [_cell_str(v) for v in vals]

        cat_ativo   = col[0]
        grp_ativo   = col[1]
        nome_ativo  = col[2]
        desc_ativo  = col[3]
        cat_mat     = col[4]
        grp_mat     = col[5]
        nome_mat    = col[6]
        desc_mat    = col[7]
        cod_patr    = col[11]
        obs         = col[12]

        # parar na primeira linha com A+B+C vazios
        if not cat_ativo and not grp_ativo and not nome_ativo:
            break

        linha_num: int = row[0].row if row else 0

        # linhas com E+F+G todos vazios → ignorar silenciosamente
        if not cat_mat and not grp_mat and not nome_mat:
            continue

        campo_erros: list[dict] = []

        # obrigatórios do ativo
        for campo, val in [("categoria_ativo", cat_ativo), ("grupo_ativo", grp_ativo), ("nome_ativo", nome_ativo)]:
            if not val:
                campo_erros.append({"linha": linha_num, "campo": campo, "mensagem": "Campo obrigatório vazio"})

        # obrigatórios do material
        for campo, val in [("categoria_material", cat_mat), ("grupo_material", grp_mat), ("nome_material", nome_mat)]:
            if not val:
                campo_erros.append({"linha": linha_num, "campo": campo, "mensagem": "Campo obrigatório vazio"})

        # quantidade
        try:
            quantidade = max(1, _parse_int(vals[8], 1))
        except ValueError:
            quantidade = 1

        # unidade
        unidade = col[9].lower() if col[9] else "un"
        if unidade not in _UNIDADES_VALIDAS:
            unidade = "un"

        # valor_unitario
        try:
            valor_unitario: Optional[float] = _parse_float(vals[10], 0.0) if vals[10] is not None else None
        except ValueError:
            valor_unitario = None

        if campo_erros:
            erros.extend(campo_erros)
            continue

        # ── lookups de ativo ──
        acat_key = cat_ativo.lower()
        if acat_key not in _acat_cache:
            _acat_cache[acat_key] = db.query(models.AtivoCategoria).filter(
                models.AtivoCategoria.nome.ilike(cat_ativo)
            ).first()
        acat_obj = _acat_cache[acat_key]

        agrp_key = (cat_ativo.lower(), grp_ativo.lower())
        if agrp_key not in _agrp_cache:
            if acat_obj:
                _agrp_cache[agrp_key] = db.query(models.AtivoGrupo).filter(
                    models.AtivoGrupo.categoria_id == acat_obj.id,
                    models.AtivoGrupo.nome.ilike(grp_ativo),
                ).first()
            else:
                _agrp_cache[agrp_key] = None
        agrp_obj = _agrp_cache[agrp_key]

        ativo_key = (cat_ativo.lower(), grp_ativo.lower(), nome_ativo.lower())
        if ativo_key not in _ativo_cache:
            if agrp_obj:
                _ativo_cache[ativo_key] = db.query(models.Ativo).filter(
                    models.Ativo.grupo_id == agrp_obj.id,
                    models.Ativo.nome.ilike(nome_ativo),
                    models.Ativo.ativo == True,
                ).first()
            else:
                _ativo_cache[ativo_key] = None
        ativo_obj = _ativo_cache[ativo_key]
        status_ativo = "existente" if ativo_obj else "novo"

        # ── lookups de material ──
        mcat_key = cat_mat.lower()
        if mcat_key not in _cat_cache:
            _cat_cache[mcat_key] = db.query(models.Categoria).filter(
                models.Categoria.nome.ilike(cat_mat)
            ).first()
        mcat_obj = _cat_cache[mcat_key]

        mgrp_key = (cat_mat.lower(), grp_mat.lower())
        if mgrp_key not in _grp_cache:
            if mcat_obj:
                _grp_cache[mgrp_key] = db.query(models.GrupoMaterial).filter(
                    models.GrupoMaterial.categoria_id == mcat_obj.id,
                    models.GrupoMaterial.nome.ilike(grp_mat),
                ).first()
            else:
                _grp_cache[mgrp_key] = None
        mgrp_obj = _grp_cache[mgrp_key]

        mat_key = (cat_mat.lower(), grp_mat.lower(), nome_mat.lower())
        if mat_key not in _mat_cache:
            if mgrp_obj:
                _mat_cache[mat_key] = db.query(models.Material).filter(
                    models.Material.grupo_id == mgrp_obj.id,
                    models.Material.nome.ilike(nome_mat),
                    models.Material.ativo == True,
                ).first()
            else:
                _mat_cache[mat_key] = None
        mat_obj = _mat_cache[mat_key]
        status_material = "existente" if mat_obj else "novo"

        # material com usa_patrimonio=True e sem código → erro
        if mat_obj and mat_obj.usa_patrimonio and not cod_patr:
            erros.append({
                "linha": linha_num,
                "campo": "codigo_patrimonio",
                "mensagem": f"Material '{nome_mat}' usa controle de patrimônio — informe codigo_patrimonio",
            })
            continue

        tem_patrimonio = bool(cod_patr)

        # contadores de resumo
        ativo_key_resumo = (cat_ativo.lower(), grp_ativo.lower(), nome_ativo.lower())
        if status_ativo == "novo":
            ativos_novos.add(ativo_key_resumo)
        else:
            ativos_existentes.add(ativo_key_resumo)
        if status_material == "novo":
            materiais_novos += 1
        else:
            materiais_existentes += 1
        if tem_patrimonio:
            com_patrimonio += 1
        else:
            sem_patrimonio += 1

        linhas_validas.append({
            "linha":               linha_num,
            "categoria_ativo":     cat_ativo,
            "grupo_ativo":         grp_ativo,
            "nome_ativo":          nome_ativo,
            "descricao_ativo":     desc_ativo,
            "categoria_material":  cat_mat,
            "grupo_material":      grp_mat,
            "nome_material":       nome_mat,
            "descricao_material":  desc_mat,
            "quantidade":          quantidade,
            "unidade":             unidade,
            "valor_unitario":      valor_unitario,
            "codigo_patrimonio":   cod_patr,
            "observacao":          obs,
            "status_ativo":        status_ativo,
            "status_material":     status_material,
            "tem_patrimonio":      tem_patrimonio,
        })

    wb.close()

    return {
        "total_linhas": len(linhas_validas) + len(erros),
        "linhas_validas": linhas_validas,
        "erros": erros,
        "resumo": {
            "ativos_novos":          len(ativos_novos),
            "ativos_existentes":     len(ativos_existentes),
            "materiais_novos":       materiais_novos,
            "materiais_existentes":  materiais_existentes,
            "com_patrimonio":        com_patrimonio,
            "sem_patrimonio":        sem_patrimonio,
        },
    }


# ── T2 — GET /api/onboarding/ativos/template-excel ────────────────────────────

@router.get("/ativos/template-excel")
def baixar_template_ativos(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
) -> StreamingResponse:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Ativos"

    fill_header  = PatternFill("solid", fgColor="1B3A2D")
    fill_exemplo = PatternFill("solid", fgColor="E8E8E8")
    font_header  = Font(bold=True, color="FFFFFF", size=11)
    font_exemplo = Font(size=10, italic=True, color="666666")
    al_center    = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, nome in enumerate(_COLUNAS_ATIVOS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=nome)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = al_center
    ws.row_dimensions[1].height = 20

    exemplos = [
        "Departamentos", "Contabil", "Ana Paula", "Analista Contábil",
        "Informatica", "Computadores", "Notebook Dell", "Core i5 8GB",
        1, "un", 3200.00, "TI-001", "",
    ]
    for col_idx, val in enumerate(exemplos, start=1):
        cell = ws.cell(row=2, column=col_idx, value=val)
        cell.font = font_exemplo
        cell.fill = fill_exemplo

    dv_unidade = DataValidation(
        type="list", formula1='"un,cx,pc,m,l,kg,par,rolo"',
        allow_blank=True, showDropDown=False, showErrorMessage=True,
        errorTitle="Unidade inválida", error="Use: un, cx, pc, m, l, kg, par ou rolo",
    )
    dv_unidade.sqref = "J3:J502"
    ws.add_data_validation(dv_unidade)

    dv_qtd = DataValidation(
        type="whole", operator="greaterThanOrEqual", formula1="1",
        allow_blank=True, showErrorMessage=True,
        errorTitle="Quantidade inválida", error="Informe um inteiro >= 1",
    )
    dv_qtd.sqref = "I3:I502"
    ws.add_data_validation(dv_qtd)

    ws.freeze_panes = "A3"
    for col_letra, larg in _LARGURAS_ATIVOS.items():
        ws.column_dimensions[col_letra].width = larg

    # aba instruções
    ws_inst = wb.create_sheet("Instrucoes")
    ws_inst.protection.sheet = True
    instrucoes = [
        ("INSTRUÇÕES DE PREENCHIMENTO — ATIVOS", True),
        ("", False),
        ("COLUNAS DO ATIVO (A–D)", True),
        ("A  categoria_ativo*   — Categoria do ativo (ex: Departamentos). Criada se não existir.", False),
        ("B  grupo_ativo*       — Grupo dentro da categoria (ex: Contabil). Criado se não existir.", False),
        ("C  nome_ativo*        — Nome do ativo/pessoa.", False),
        ("D  descricao_ativo    — Descrição opcional.", False),
        ("", False),
        ("COLUNAS DO MATERIAL (E–M)", True),
        ("E  categoria_material* — Categoria do material (ex: Informatica).", False),
        ("F  grupo_material*     — Grupo do material (ex: Computadores).", False),
        ("G  nome_material*      — Nome do material. Criado no estoque se não existir.", False),
        ("H  descricao_material  — Descrição (usada só se o material for criado).", False),
        ("I  quantidade          — Qtd a atribuir. Inteiro >= 1. Padrão: 1.", False),
        ("J  unidade             — Unidade: un, cx, pc, m, l, kg, par, rolo. Padrão: un.", False),
        ("K  valor_unitario      — Valor em reais. Opcional.", False),
        ("L  codigo_patrimonio   — Código de patrimônio. Obrigatório se material usa rastreio.", False),
        ("M  observacao          — Observação da atribuição.", False),
        ("", False),
        ("REGRAS", True),
        ("- Não altere o cabeçalho da linha 1.", False),
        ("- A linha 2 é apenas um exemplo — não será importada.", False),
        ("- Preencha os dados a partir da linha 3.", False),
        ("- Linhas com colunas E, F e G vazias são ignoradas na importação.", False),
        ("- Linhas em branco (A+B+C vazias) interrompem a leitura.", False),
        ("- O arquivo exportado dos ativos existentes já vem neste formato.", False),
    ]
    for row_idx, (texto, negrito) in enumerate(instrucoes, start=1):
        cell = ws_inst.cell(row=row_idx, column=1, value=texto)
        cell.font = Font(bold=negrito, size=11 if negrito else 10)
    ws_inst.column_dimensions["A"].width = 90

    # aba ativos_e_grupos
    ws_ag = wb.create_sheet("Ativos_e_Grupos")
    categorias_a = db.query(models.AtivoCategoria).order_by(models.AtivoCategoria.nome).all()
    if not categorias_a:
        ws_ag.cell(row=1, column=1, value="Nenhuma categoria de ativo cadastrada ainda.")
    else:
        fill_cab = PatternFill("solid", fgColor="1B3A2D")
        font_cab = Font(bold=True, color="FFFFFF", size=11)
        for col_idx, titulo in enumerate(["Categoria", "Grupo"], start=1):
            cell = ws_ag.cell(row=1, column=col_idx, value=titulo)
            cell.font = font_cab
            cell.fill = fill_cab
        linha_ag = 2
        for acat in categorias_a:
            grupos_a = db.query(models.AtivoGrupo).filter(
                models.AtivoGrupo.categoria_id == acat.id
            ).order_by(models.AtivoGrupo.nome).all()
            for agrp in grupos_a:
                ws_ag.cell(row=linha_ag, column=1, value=acat.nome)
                ws_ag.cell(row=linha_ag, column=2, value=agrp.nome)
                linha_ag += 1
    ws_ag.column_dimensions["A"].width = 28
    ws_ag.column_dimensions["B"].width = 28

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=modelo_ativos.xlsx"},
    )


# ── T3 — POST /api/onboarding/ativos/preview-excel ────────────────────────────

@router.post("/ativos/preview-excel")
async def preview_ativos_excel(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
) -> dict:
    contents = await arquivo.read()
    if len(contents) > _MAX_XLSX_BYTES:
        raise HTTPException(413, "Arquivo muito grande (máximo 5 MB)")
    return _parse_excel_ativos(contents, db)


# ── T4 — POST /api/onboarding/ativos/importar-excel ───────────────────────────

@router.post("/ativos/importar-excel")
async def importar_ativos_excel(
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
) -> JSONResponse:
    contents = await arquivo.read()
    if len(contents) > _MAX_XLSX_BYTES:
        raise HTTPException(413, "Arquivo muito grande (máximo 5 MB)")

    parse = _parse_excel_ativos(contents, db)
    linhas = parse["linhas_validas"]

    if not linhas and parse["erros"]:
        raise HTTPException(422, "Planilha sem linhas válidas para importar")

    # contadores
    n_acat = n_agrp = n_ativo = n_mat = n_item = 0
    avisos: list[dict] = []
    erros_imp: list[dict] = []

    # caches de criação
    acat_map: dict[str, models.AtivoCategoria] = {}
    agrp_map: dict[tuple, models.AtivoGrupo] = {}
    ativo_map: dict[tuple, models.Ativo] = {}
    cat_map: dict[str, models.Categoria] = {}
    grp_map: dict[tuple, models.GrupoMaterial] = {}
    mat_map: dict[tuple, models.Material] = {}
    cod_cache: set[str] = set()  # códigos de patrimônio do lote atual

    for linha in linhas:
        ln = linha["linha"]
        try:
            # ── ETAPA A — hierarquia de ativo ──────────────────────────────
            acat_key = linha["categoria_ativo"].lower()
            if acat_key not in acat_map:
                obj = db.query(models.AtivoCategoria).filter(
                    models.AtivoCategoria.nome.ilike(linha["categoria_ativo"])
                ).first()
                if not obj:
                    obj = models.AtivoCategoria(nome=linha["categoria_ativo"])
                    db.add(obj); db.flush(); n_acat += 1
                acat_map[acat_key] = obj

            agrp_key = (linha["categoria_ativo"].lower(), linha["grupo_ativo"].lower())
            if agrp_key not in agrp_map:
                obj = db.query(models.AtivoGrupo).filter(
                    models.AtivoGrupo.categoria_id == acat_map[acat_key].id,
                    models.AtivoGrupo.nome.ilike(linha["grupo_ativo"]),
                ).first()
                if not obj:
                    obj = models.AtivoGrupo(
                        nome=linha["grupo_ativo"],
                        categoria_id=acat_map[acat_key].id,
                    )
                    db.add(obj); db.flush(); n_agrp += 1
                agrp_map[agrp_key] = obj

            ativo_key = (linha["categoria_ativo"].lower(), linha["grupo_ativo"].lower(), linha["nome_ativo"].lower())
            if ativo_key not in ativo_map:
                obj = db.query(models.Ativo).filter(
                    models.Ativo.grupo_id == agrp_map[agrp_key].id,
                    models.Ativo.nome.ilike(linha["nome_ativo"]),
                    models.Ativo.ativo == True,
                ).first()
                if not obj:
                    obj = models.Ativo(
                        nome=linha["nome_ativo"],
                        descricao=linha["descricao_ativo"] or None,
                        grupo_id=agrp_map[agrp_key].id,
                    )
                    db.add(obj); db.flush(); n_ativo += 1
                ativo_map[ativo_key] = obj
            ativo = ativo_map[ativo_key]

            # ── ETAPA B — material no estoque ──────────────────────────────
            cat_key = linha["categoria_material"].lower()
            if cat_key not in cat_map:
                obj = db.query(models.Categoria).filter(
                    models.Categoria.nome.ilike(linha["categoria_material"])
                ).first()
                if not obj:
                    obj = models.Categoria(nome=linha["categoria_material"])
                    db.add(obj); db.flush()
                cat_map[cat_key] = obj

            grp_key = (linha["categoria_material"].lower(), linha["grupo_material"].lower())
            if grp_key not in grp_map:
                obj = db.query(models.GrupoMaterial).filter(
                    models.GrupoMaterial.categoria_id == cat_map[cat_key].id,
                    models.GrupoMaterial.nome.ilike(linha["grupo_material"]),
                ).first()
                if not obj:
                    obj = models.GrupoMaterial(
                        nome=linha["grupo_material"],
                        categoria_id=cat_map[cat_key].id,
                    )
                    db.add(obj); db.flush()
                grp_map[grp_key] = obj

            mat_key = (linha["categoria_material"].lower(), linha["grupo_material"].lower(), linha["nome_material"].lower())
            if mat_key not in mat_map:
                obj = db.query(models.Material).filter(
                    models.Material.grupo_id == grp_map[grp_key].id,
                    models.Material.nome.ilike(linha["nome_material"]),
                    models.Material.ativo == True,
                ).first()
                if not obj:
                    obj = models.Material(
                        nome=linha["nome_material"],
                        descricao=linha["descricao_material"] or None,
                        quantidade=0.0,
                        unidade=linha["unidade"],
                        grupo_id=grp_map[grp_key].id,
                        valor_unitario=linha["valor_unitario"],
                        fator_embalagem=1.0,
                        usa_patrimonio=False,
                        ativo=True,
                    )
                    db.add(obj); db.flush()
                    mov_e = models.Movimentacao(
                        material_id=obj.id, usuario_id=atual.id,
                        tipo="entrada", quantidade=float(linha["quantidade"]),
                        observacao="Importacao via ativos (planilha)",
                    )
                    db.add(mov_e); db.flush()
                    obj.quantidade += linha["quantidade"]
                    n_mat += 1
                elif obj.usa_patrimonio and not linha["codigo_patrimonio"]:
                    erros_imp.append({"linha": ln, "campo": "codigo_patrimonio",
                        "mensagem": f"Material '{linha['nome_material']}' usa controle de patrimônio — informe codigo_patrimonio"})
                    continue
                else:
                    delta = max(0, linha["quantidade"] - obj.quantidade)
                    if delta > 0:
                        mov_e = models.Movimentacao(
                            material_id=obj.id, usuario_id=atual.id,
                            tipo="entrada", quantidade=float(delta),
                            observacao="Complemento de estoque via importacao de ativos (planilha)",
                        )
                        db.add(mov_e); db.flush()
                        obj.quantidade += delta
                mat_map[mat_key] = obj
            mat = mat_map[mat_key]

            # ── ETAPA C — duplicata de atribuição ──────────────────────────
            duplicado = db.query(models.AtivoItem).filter(
                models.AtivoItem.ativo_id == ativo.id,
                models.AtivoItem.material_id == mat.id,
                models.AtivoItem.devolvido_em == None,
            ).first()
            if duplicado:
                avisos.append({"linha": ln,
                    "mensagem": f"Material '{linha['nome_material']}' já atribuído a '{linha['nome_ativo']}' — linha ignorada"})
                continue

            # ── ETAPA D — atribuir ─────────────────────────────────────────
            cod_patr = linha["codigo_patrimonio"]
            if cod_patr:
                if cod_patr in cod_cache:
                    erros_imp.append({"linha": ln, "campo": "codigo_patrimonio",
                        "mensagem": f"Código de patrimônio '{cod_patr}' duplicado no lote"})
                    continue
                cod_cache.add(cod_patr)
                unidade_pat = models.UnidadePatrimonio(
                    material_id=mat.id,
                    codigo=cod_patr,
                    status=models.StatusUnidade.ativo,
                    origem="importacao_ativo",
                    tag="atribuido",
                )
                db.add(unidade_pat); db.flush()
                sync_qty(mat, db)
                item = models.AtivoItem(
                    ativo_id=ativo.id, material_id=mat.id,
                    unidade_id=unidade_pat.id, quantidade=1.0,
                    observacao=linha["observacao"] or None,
                )
            else:
                mat.quantidade -= linha["quantidade"]
                mov_s = models.Movimentacao(
                    material_id=mat.id, usuario_id=atual.id,
                    tipo="saida", quantidade=float(linha["quantidade"]),
                    observacao="Atribuicao via importacao de ativos (planilha)",
                )
                db.add(mov_s); db.flush()
                item = models.AtivoItem(
                    ativo_id=ativo.id, material_id=mat.id,
                    unidade_id=None, quantidade=float(linha["quantidade"]),
                    observacao=linha["observacao"] or None,
                )

            db.add(item); db.flush()
            n_item += 1

        except Exception as exc:
            db.rollback()
            erros_imp.append({"linha": ln, "campo": "geral",
                "mensagem": f"Erro inesperado: {exc}"})
            continue

    db.commit()

    detalhe = (
        f"acat={n_acat} agrp={n_agrp} ativos={n_ativo} "
        f"materiais={n_mat} itens={n_item} "
        f"avisos={len(avisos)} erros={len(erros_imp)}"
    )
    registrar_log(db, atual.id, "importacao_ativos_excel", "onboarding", None, detalhe)

    payload = {
        "sucesso": True,
        "criados": {
            "ativos_categorias": n_acat,
            "ativos_grupos":     n_agrp,
            "ativos":            n_ativo,
            "materiais":         n_mat,
            "ativos_itens":      n_item,
        },
        "avisos": avisos,
        "erros":  erros_imp,
    }
    status_code = 207 if (erros_imp or avisos) else 200
    return JSONResponse(content=payload, status_code=status_code)


# ── T5 — GET /api/onboarding/ativos/exportar-excel ────────────────────────────

@router.get("/ativos/exportar-excel")
def exportar_ativos_excel(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
) -> StreamingResponse:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from datetime import datetime

    # Query 1 — ativos COM itens atribuídos
    itens = (
        db.query(models.AtivoItem)
        .filter(models.AtivoItem.devolvido_em == None)
        .join(models.Ativo, models.AtivoItem.ativo_id == models.Ativo.id)
        .filter(models.Ativo.ativo == True)
        .all()
    )
    ids_com_itens = {item.ativo_id for item in itens}

    # Query 2 — ativos SEM itens
    q_vazios = (
        db.query(models.Ativo)
        .join(models.AtivoGrupo, models.Ativo.grupo_id == models.AtivoGrupo.id)
        .join(models.AtivoCategoria, models.AtivoGrupo.categoria_id == models.AtivoCategoria.id)
        .filter(models.Ativo.ativo == True)
    )
    if ids_com_itens:
        q_vazios = q_vazios.filter(~models.Ativo.id.in_(ids_com_itens))
    ativos_vazios = q_vazios.all()

    # montar linhas
    linhas_excel: list[dict] = []

    for item in itens:
        linhas_excel.append({
            "categoria_ativo":    item.ativo_obj.grupo.categoria.nome,
            "grupo_ativo":        item.ativo_obj.grupo.nome,
            "nome_ativo":         item.ativo_obj.nome,
            "descricao_ativo":    item.ativo_obj.descricao or "",
            "categoria_material": item.material.grupo.categoria.nome,
            "grupo_material":     item.material.grupo.nome,
            "nome_material":      item.material.nome,
            "descricao_material": item.material.descricao or "",
            "quantidade":         int(item.quantidade),
            "unidade":            item.material.unidade,
            "valor_unitario":     item.material.valor_unitario or "",
            "codigo_patrimonio":  item.unidade_patr.codigo if item.unidade_patr else "",
            "observacao":         item.observacao or "",
        })

    for ativo in ativos_vazios:
        linhas_excel.append({
            "categoria_ativo":    ativo.grupo.categoria.nome,
            "grupo_ativo":        ativo.grupo.nome,
            "nome_ativo":         ativo.nome,
            "descricao_ativo":    ativo.descricao or "",
            "categoria_material": "",
            "grupo_material":     "",
            "nome_material":      "",
            "descricao_material": "",
            "quantidade":         "",
            "unidade":            "",
            "valor_unitario":     "",
            "codigo_patrimonio":  "",
            "observacao":         "",
        })

    linhas_excel.sort(key=lambda r: (
        r["categoria_ativo"].lower(),
        r["grupo_ativo"].lower(),
        r["nome_ativo"].lower(),
    ))

    # gerar workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Ativos"

    fill_header = PatternFill("solid", fgColor="1B3A2D")
    font_header = Font(bold=True, color="FFFFFF", size=11)
    al_center   = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, nome in enumerate(_COLUNAS_ATIVOS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=nome)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = al_center

    for row_idx, linha in enumerate(linhas_excel, start=2):
        for col_idx, campo in enumerate(_COLUNAS_ATIVOS, start=1):
            ws.cell(row=row_idx, column=col_idx, value=linha[campo])

    ws.freeze_panes = "A2"
    for col_letra, larg in _LARGURAS_ATIVOS.items():
        ws.column_dimensions[col_letra].width = larg

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    data_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"exportacao_ativos_{data_str}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
