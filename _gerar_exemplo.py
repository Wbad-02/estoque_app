import sqlite3
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation

# ── 1. LIMPAR BANCO (preserva usuarios e configs) ──────────────────────────
conn = sqlite3.connect("i:/Meu Drive/WEMERSON/APLICATIVOS/estoque_app/estoque.db")
cur = conn.cursor()

tabelas = [
    "solicitacoes_estoque",
    "ativos_itens",
    "unidades_patrimonio",
    "movimentacoes",
    "materiais",
    "grupos_material",
    "categorias",
    "ativos",
    "ativos_grupos",
    "ativos_categorias",
    "requerimentos_itens",
    "requerimentos",
    "nfe_importadas",
    "logs_auditoria",
]
for t in tabelas:
    cur.execute(f"DELETE FROM {t}")
    print(f"  limpo: {t}")

conn.commit()
conn.close()
print("Banco limpo.\n")

# ── 2. GERAR EXCEL PRE-PREENCHIDO ──────────────────────────────────────────
dados = [
    # (categoria, grupo, qtd_min_grupo, material, descricao, quantidade, unidade, valor_unitario, fator_embalagem)
    ("Informatica", "Perifericos",          5,  "Mouse USB",                    "Mouse optico sem fio USB",                12, "un",  45.90,  1),
    ("Informatica", "Perifericos",          5,  "Teclado USB",                  "Teclado ABNT2 com fio",                   10, "un",  89.90,  1),
    ("Informatica", "Perifericos",          5,  "Webcam HD",                    "Webcam 1080p com microfone",               4, "un", 159.00,  1),
    ("Informatica", "Perifericos",          5,  "Headset USB",                  "Fone com microfone para reunioes",         6, "un", 120.00,  1),
    ("Informatica", "Computadores",         2,  "Notebook Dell Inspiron",       "Core i5 8GB RAM 256GB SSD",               3, "un", 3200.00, 1),
    ("Informatica", "Computadores",         2,  "Desktop i5",                   "Core i5 16GB RAM 500GB HD",               5, "un", 2500.00, 1),
    ("Informatica", "Computadores",         2,  "Monitor 24 pol",               "Monitor LED Full HD HDMI",                8, "un",  899.00, 1),
    ("Informatica", "Redes",               10,  "Cabo de rede Cat6",            "Cabo UTP Cat6 por metro",               200, "m",     3.50, 1),
    ("Informatica", "Redes",                2,  "Switch 8 portas",              "Switch Gigabit gerenciavel",              3, "un",  350.00, 1),
    ("Informatica", "Redes",                1,  "Roteador WiFi",                "Dual-band AC1200",                        2, "un",  280.00, 1),
    ("Informatica", "Redes",                5,  "Patch cable 1m",               "Cabo de rede pronto Cat6 1m",            30, "un",   12.00, 1),
    ("Escritorio",  "Papelaria",           20,  "Papel A4 500fls",              "Resma papel sulfite 75g",                40, "cx",   28.50, 500),
    ("Escritorio",  "Papelaria",           10,  "Caneta esferografica azul",    "Ponta media 0.7mm",                      60, "un",    1.80, 10),
    ("Escritorio",  "Papelaria",            5,  "Pasta suspensa",               "Pasta AZ oficio",                        15, "un",    9.90, 1),
    ("Escritorio",  "Papelaria",           10,  "Post-it 76x76mm",              "Bloco 100 folhas amarelo",               20, "un",    6.50, 1),
    ("Escritorio",  "Papelaria",            5,  "Grampo 26/6",                  "Caixa com 5000 grampos",                  8, "cx",    7.90, 5000),
    ("Escritorio",  "Impressao",            2,  "Toner HP 85A",                 "Toner original LaserJet P1102",           6, "un",   89.00, 1),
    ("Escritorio",  "Impressao",            2,  "Toner HP 12A",                 "Toner original LaserJet 1020",            4, "un",   95.00, 1),
    ("Escritorio",  "Impressao",            4,  "Cartucho Epson T664 preto",    "Tinta original para L355 L365",           8, "un",   42.00, 1),
    ("Limpeza",     "Higiene",              5,  "Papel toalha folha dupla",     "Rolo 20m c/ 12 unidades",                24, "cx",   18.90, 12),
    ("Limpeza",     "Higiene",              5,  "Sabonete liquido 1L",          "Refil para dispenser",                   10, "un",   12.50, 1),
    ("Limpeza",     "Higiene",              3,  "Alcool gel 500ml",             "Alcool 70pct INPM",                      15, "un",    9.90, 1),
    ("Limpeza",     "Produtos de Limpeza",  3,  "Desinfetante 1L",              "Multiuso concentrado",                    8, "un",    8.00, 1),
    ("Limpeza",     "Produtos de Limpeza",  3,  "Detergente 500ml",             "Neutro",                                 12, "un",    3.50, 1),
    ("Limpeza",     "Produtos de Limpeza",  5,  "Saco de lixo 60L c10",        "Pacote com 10 unidades preto",           20, "pc",    6.90, 10),
    ("Limpeza",     "EPI",                 10,  "Luva de borracha M",           "Par luva nitrilica tam. M",              30, "par",   4.50, 1),
    ("Limpeza",     "EPI",                  5,  "Mascara descartavel c50",      "Caixa com 50 mascaras tripla camada",    6,  "cx",   28.00, 50),
    ("Eletrica",    "Cabos e Conectores",   5,  "Extensao 3 tomadas 2m",        "Extensao com protecao",                   8, "un",   32.00, 1),
    ("Eletrica",    "Cabos e Conectores",   5,  "Cabo HDMI 2m",                 "Cabo HDMI 2.0 Full HD",                  10, "un",   25.00, 1),
    ("Eletrica",    "Cabos e Conectores",   5,  "Adaptador USB-C HDMI",         "Adaptador para notebooks modernos",       4, "un",   45.00, 1),
    ("Eletrica",    "Protecao Eletrica",    2,  "Nobreak 600VA",                "Nobreak bivolt 600VA",                    3, "un",  450.00, 1),
    ("Eletrica",    "Protecao Eletrica",    3,  "Filtro de linha 6 tomadas",    "Com protecao contra surto",              12, "un",   65.00, 1),
]

wb = Workbook()

# ── Aba Materiais ──────────────────────────────────────────────────────────
ws = wb.active
ws.title = "Materiais"

cab_fill = PatternFill("solid", fgColor="1B3A2D")
cab_font = Font(bold=True, color="FFFFFF", size=11)
ex_fill  = PatternFill("solid", fgColor="F2F2F2")
ex_font  = Font(italic=True, color="888888", size=10)
borda = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)

colunas = [
    ("A", "categoria",               22),
    ("B", "grupo",                   22),
    ("C", "quantidade_minima_grupo", 10),
    ("D", "material",                30),
    ("E", "descricao",               35),
    ("F", "quantidade",              12),
    ("G", "unidade",                 10),
    ("H", "valor_unitario",          14),
    ("I", "fator_embalagem",         14),
]

for col_letter, nome, largura in colunas:
    cell = ws[f"{col_letter}1"]
    cell.value = nome
    cell.font = cab_font
    cell.fill = cab_fill
    cell.alignment = Alignment(horizontal="center", vertical="center")
    cell.border = borda
    ws.column_dimensions[col_letter].width = largura

ws.row_dimensions[1].height = 22

# Linha 2: exemplo em cinza
exemplo = ["Informatica", "Perifericos", 5, "Mouse USB", "Mouse optico USB", 10, "un", 45.90, 1]
for i, val in enumerate(exemplo, 1):
    cell = ws.cell(row=2, column=i, value=val)
    cell.font = ex_font
    cell.fill = ex_fill
    cell.border = borda

# Dados reais a partir da linha 3
for row_idx, linha in enumerate(dados, start=3):
    for col_idx, valor in enumerate(linha, start=1):
        cell = ws.cell(row=row_idx, column=col_idx, value=valor)
        cell.border = borda
        cell.alignment = Alignment(vertical="center")
        if col_idx in (3, 6, 8, 9):
            cell.alignment = Alignment(horizontal="right", vertical="center")

# Linhas vazias ate 502
for r in range(3 + len(dados), 503):
    for c in range(1, 10):
        ws.cell(row=r, column=c).border = borda

# Validacoes
dv_unidade = DataValidation(
    type="list",
    formula1='"un,cx,pc,m,l,kg,par,rolo"',
    allow_blank=True,
    showDropDown=False,
    showErrorMessage=True,
    errorTitle="Unidade invalida",
    error="Use: un, cx, pc, m, l, kg, par ou rolo",
)
dv_unidade.sqref = "G3:G502"
ws.add_data_validation(dv_unidade)

dv_qtd = DataValidation(
    type="whole",
    operator="greaterThanOrEqual",
    formula1="0",
    allow_blank=True,
    showErrorMessage=True,
    errorTitle="Quantidade invalida",
    error="Informe um numero inteiro >= 0",
)
dv_qtd.sqref = "F3:F502"
ws.add_data_validation(dv_qtd)

ws.freeze_panes = "A3"

# ── Aba Instrucoes ─────────────────────────────────────────────────────────
ws2 = wb.create_sheet("Instrucoes")
ws2.protection.sheet = True

instrucoes = [
    ("INSTRUCOES DE PREENCHIMENTO",                                                              True),
    ("",                                                                                         False),
    ("COLUNAS OBRIGATORIAS (*)",                                                                 True),
    ("A  categoria*            -- Nome da categoria. Criada automaticamente se nao existir.",    False),
    ("B  grupo*                -- Nome do grupo dentro da categoria. Criado automaticamente.",   False),
    ("D  material*             -- Nome do material.",                                            False),
    ("F  quantidade*           -- Estoque inicial. Inteiro >= 0.",                               False),
    ("",                                                                                         False),
    ("COLUNAS OPCIONAIS",                                                                        True),
    ("C  qtd_minima_grupo      -- Alerta de estoque minimo para o grupo. Padrao: 0.",            False),
    ("E  descricao             -- Descricao livre.",                                             False),
    ("G  unidade               -- Opcoes: un, cx, pc, m, l, kg, par, rolo. Padrao: un.",        False),
    ("H  valor_unitario        -- Valor em reais (ex: 45.90). Opcional.",                        False),
    ("I  fator_embalagem       -- Qtd por embalagem. Padrao: 1.",                               False),
    ("",                                                                                         False),
    ("REGRAS",                                                                                   True),
    ("- Nao altere os cabecalhos da linha 1.",                                                   False),
    ("- A linha 2 e apenas um exemplo visual — nao sera importada.",                             False),
    ("- Preencha os dados a partir da linha 3.",                                                 False),
    ("- Deixe linhas em branco somente no final. A leitura para na 1a linha vazia.",             False),
    ("- Salve sempre como .xlsx antes de enviar.",                                               False),
]

for row_idx, (texto, negrito) in enumerate(instrucoes, start=1):
    cell = ws2.cell(row=row_idx, column=1, value=texto)
    cell.font = Font(bold=negrito, size=11 if negrito else 10)
ws2.column_dimensions["A"].width = 80

# ── Aba Categorias_e_Grupos ────────────────────────────────────────────────
ws3 = wb.create_sheet("Categorias_e_Grupos")
ws3.cell(row=1, column=1, value="Banco vazio -- importe esta planilha para popular o estoque.")
ws3.column_dimensions["A"].width = 60

# ── Salvar ─────────────────────────────────────────────────────────────────
caminho = "i:/Meu Drive/WEMERSON/APLICATIVOS/estoque_app/static/modelo_estoque_exemplo.xlsx"
wb.save(caminho)
print(f"Excel salvo: {caminho}")
print(f"Total de materiais no arquivo: {len(dados)}")
