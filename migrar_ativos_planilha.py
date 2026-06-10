"""
migrar_ativos_planilha.py

Migra atribuições da planilha static/importacao_ativos.xlsx para o banco de produção.

Uso:
  python migrar_ativos_planilha.py          → dry-run (mostra o que fará, sem alterar)
  python migrar_ativos_planilha.py --apply  → aplica as mudanças

Deve ser executado na raiz do projeto com o virtualenv ativado.
"""

import sys, os, re, sqlite3
from openpyxl import load_workbook
from datetime import datetime, timezone

DRY_RUN = "--apply" not in sys.argv
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8")

# ── caminhos ──────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "estoque.db")
XLSX    = os.path.join(BASE, "static", "importacao_ativos.xlsx")

# ── mapeamento planilha → ativo_id no servidor ────────────────────────────────
# Chave: (nome_curto_lower, grupo_planilha_lower)
# Valor: ativo_id existente, ou None → criar ativo novo
ATIVO_MAP = {
    # Comercial / CS
    ("eduardo",          "comercial"): None,   # não existe; criar Comercial - Eduardo
    ("ana luizze",       "comercial"): 48,
    ("betania",          "comercial"): 49,
    ("alex",             "comercial"): 47,
    # Certitech
    ("lara",             "certitech"): 57,
    # Fiscal
    ("neiviton",         "fiscal"):    33,
    ("marcio",           "fiscal"):    41,      # ADM - Marcio Neves (depto diferente, ok)
    ("eduardo",          "fiscal"):    28,
    ("lumara",           "fiscal"):    31,
    ("carlos",           "fiscal"):    27,
    ("pamela",           "fiscal"):    34,
    ("ana tereza",       "fiscal"):    26,
    ("marcos",           "fiscal"):    None,    # não existe; criar Fiscal - Marcos
    ("felipe",           "fiscal"):    29,
    # Atendimento → Administrativo no servidor
    ("elaine",           "atendimento"): None,  # não existe; criar ADM - Elaine
    ("leidiane",         "atendimento"): 36,
    ("maria eduarda",    "atendimento"): 37,
    ("eduarda cipriano", "atendimento"): None,  # não existe; criar ADM - Eduarda Cipriano
    # Administrativo
    ("gabriel",          "administrativo"): 39,
    ("amanda",           "administrativo"): 38,
    ("glaucia",          "administrativo"): 40,
    # Processos
    ("ariela",           "processos"):  42,
    ("emilly",           "processos"):  45,
    ("jaqueline",        "processos"):  14,
    ("diogo",            "processos"):  44,
    ("daiane",           "processos"):  43,
    # DP
    ("victoria",         "dp"):         8,
    ("samela",           "dp"):        16,
    ("myrian",           "dp"):         9,
    ("gerlane",          "dp"):         7,
    ("diana",            "dp"):        10,
    ("eduardo",          "dp"):        15,
    ("daiany",           "dp"):        11,
    ("jessica",          "dp"):        12,
    # RH
    ("ana julia",        "rh"):        51,
    ("thays",            "rh"):        50,
    # Auditoria
    ("thalita",          "auditoria"): 55,
    ("gabriel",          "auditoria"): 56,
    # Contábil
    ("patricia",         "contabil"):  22,
    ("gilciane",         "contabil"):  23,
    ("kayo",             "contabil"):  24,
    ("vanessa",          "contabil"):  25,
    ("maria barbara",    "contabil"):  20,
    ("paulo",            "contabil"):  21,
    ("luana",            "contabil"):  18,
    ("nata",             "contabil"):  17,
    # Financeiro
    ("thaina",           "financeiro"): 54,
    ("kamily",           "financeiro"): 35,    # ADM - Kamilly Matias (depto diferente, ok)
}

# grupo_id para ativos a criar (Departamento X no servidor)
NOVO_ATIVO_GRUPO = {
    ("eduardo",          "comercial"):    7,   # Departamento Comercial
    ("marcos",           "fiscal"):      10,   # Departamento Fiscal
    ("elaine",           "atendimento"):  4,   # Departamento Administrativo
    ("eduarda cipriano", "atendimento"):  4,   # Departamento Administrativo
}

# nome completo para ativos a criar
NOVO_ATIVO_NOME = {
    ("eduardo",          "comercial"):    "Comercial - Eduardo",
    ("marcos",           "fiscal"):       "Fiscal - Marcos",
    ("elaine",           "atendimento"):  "ADM - Elaine",
    ("eduarda cipriano", "atendimento"):  "ADM - Eduarda Cipriano",
}

# ── mapeamento de material planilha → material servidor ──────────────────────
# Será resolvido em tempo de execução contra o banco.
# Chave: nome exato na planilha
# Valor: None → precisa criar; int → id existente (preenchido no load_materiais)
MAT_MAP: dict = {
    "Monitor 24\"": None,          # criar
    "Monitor 23\"": None,          # criar (planilha usa "Monitor" genérico)
    "Monitor Jingshu 23, 23 Pol, FHD, 5ms, 75Hz, HDMI/VGA, JGS-OFFC23-JL01": 66,  # existente
    "Gabinete": None,              # criar
    "All-in-One": None,            # criar
    "Teclado": None,               # criar (grupo já existe no servidor, id=5)
    "Notebook": 44,                # NOTEBOOK POSITIVO ... (existente)
    "Mouse Sem Fio": 43,           # Mouse Sem Fio Recarregavel ... (existente)
    "Fone": 45,                    # Fone De Ouvido Headset ... (existente)
}

# planilha usa "Monitor" para monitores 23" não-Jingshu → mapear para "Monitor 23\""
PLANILHA_MAT_ALIAS = {
    "Monitor": "Monitor 23\"",
}

# especificações para criar novos materiais
NOVO_MAT_SPEC = {
    "Monitor 24\"":  {"grupo_id": 6,  "unidade": "un", "valor": 0.0},  # grupo Monitor
    "Monitor 23\"":  {"grupo_id": 6,  "unidade": "un", "valor": 0.0},  # grupo Monitor
    "Gabinete":      {"grupo_id": 60, "unidade": "un", "valor": 0.0},  # grupo novo
    "All-in-One":    {"grupo_id": 61, "unidade": "un", "valor": 0.0},  # grupo novo
    "Teclado":       {"grupo_id": 5,  "unidade": "un", "valor": 0.0},  # grupo Teclado
}

# grupos a criar se não existirem (grupo_id_placeholder → spec)
NOVOS_GRUPOS_MAT = {
    60: {"nome": "Gabinete",    "categoria_id": 7},  # Dispositivo Completo
    61: {"nome": "All-in-One",  "categoria_id": 7},  # Dispositivo Completo
}

# ── helpers ───────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ler_planilha(xlsx_path):
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Ativos"]
    itens = []
    # linha 1 = cabeçalho de colunas; dados começam na linha 2
    for row in ws.iter_rows(min_row=2):
        v = [str(c.value or "").strip() for c in row[:13]]
        cat_at, grp_at, nome_at = v[0], v[1], v[2]
        nome_mat, cod = v[6], v[11]
        descr_mat = v[7]
        unidade = v[9] or "un"
        try:
            valor = float(v[10].replace(",", ".")) if v[10] else 0.0
        except ValueError:
            valor = 0.0
        if not nome_at and not nome_mat:
            break
        if nome_at and nome_mat:
            itens.append({
                "cat_ativo": cat_at,
                "grp_ativo": grp_at.strip(),
                "nome_ativo": nome_at.strip(),
                "nome_mat": nome_mat.strip(),
                "descr_mat": descr_mat.strip(),
                "unidade": unidade,
                "valor": valor,
                "codigo": cod.strip(),
            })
    wb.close()
    return itens


def resolve_ativo_id(cur, nome, grp, criados_cache):
    """Retorna (ativo_id, criou_novo)."""
    chave = (nome.lower(), grp.lower())
    ativo_id = ATIVO_MAP.get(chave)

    if ativo_id is not None:
        return ativo_id, False

    # None → criar
    if chave in criados_cache:
        return criados_cache[chave], False

    nome_servidor = NOVO_ATIVO_NOME.get(chave, f"{grp.title()} - {nome}")
    grupo_id = NOVO_ATIVO_GRUPO.get(chave)
    if grupo_id is None:
        return None, False  # impossível mapear

    if DRY_RUN:
        fake_id = -(len(criados_cache) + 1)
        criados_cache[chave] = fake_id
        return fake_id, True

    cur.execute(
        "INSERT INTO ativos (nome, descricao, grupo_id, ativo, criado_em) VALUES (?,?,?,1,?)",
        (nome_servidor, None, grupo_id, now_iso()),
    )
    new_id = cur.lastrowid
    criados_cache[chave] = new_id
    return new_id, True


def resolve_mat_id(cur, nome_planilha, criados_mat_cache, grupos_criados_cache):
    """Retorna (mat_id, criou_novo).  Aplica alias se necessário."""
    nome_real = PLANILHA_MAT_ALIAS.get(nome_planilha, nome_planilha)
    mid = MAT_MAP.get(nome_real)

    if mid is not None:
        return mid, False

    if nome_real in criados_mat_cache:
        return criados_mat_cache[nome_real], False

    spec = NOVO_MAT_SPEC.get(nome_real)
    if spec is None:
        return None, False  # não sabemos como criar

    grupo_id = spec["grupo_id"]

    # garantir grupo existe
    if grupo_id in NOVOS_GRUPOS_MAT and grupo_id not in grupos_criados_cache:
        gspec = NOVOS_GRUPOS_MAT[grupo_id]
        if DRY_RUN:
            grupos_criados_cache[grupo_id] = grupo_id
        else:
            cur.execute(
                "INSERT INTO grupos_material (nome, categoria_id) VALUES (?,?)",
                (gspec["nome"], gspec["categoria_id"]),
            )
            real_grupo_id = cur.lastrowid
            grupos_criados_cache[grupo_id] = real_grupo_id
            grupo_id = real_grupo_id

    if grupo_id in NOVOS_GRUPOS_MAT:
        grupo_id = grupos_criados_cache.get(grupo_id, grupo_id)

    if DRY_RUN:
        fake_id = -(len(criados_mat_cache) + 100)
        criados_mat_cache[nome_real] = fake_id
        MAT_MAP[nome_real] = fake_id
        return fake_id, True

    cur.execute(
        """INSERT INTO materiais
           (nome, descricao, quantidade, unidade, grupo_id, valor_unitario, fator_embalagem,
            usa_patrimonio, ativo, criado_em)
           VALUES (?,?,0,?,?,?,1.0,1,1,?)""",
        (nome_real, None, spec["unidade"], grupo_id, spec["valor"], now_iso()),
    )
    new_id = cur.lastrowid
    criados_mat_cache[nome_real] = new_id
    MAT_MAP[nome_real] = new_id
    return new_id, True


def ja_atribuido(cur, ativo_id, mat_id):
    """Retorna (existe: bool, up_id: int|None, up_codigo: str|None)."""
    if ativo_id is None or ativo_id < 0:
        return False, None, None
    cur.execute(
        """SELECT ai.unidade_id, up.codigo
           FROM ativos_itens ai
           LEFT JOIN unidades_patrimonio up ON ai.unidade_id = up.id
           WHERE ai.ativo_id=? AND ai.material_id=? AND ai.devolvido_em IS NULL
           LIMIT 1""",
        (ativo_id, mat_id),
    )
    row = cur.fetchone()
    if row is None:
        return False, None, None
    return True, row[0], row[1]


def atualizar_codigo_up(cur, up_id, novo_codigo):
    if DRY_RUN or not up_id or not novo_codigo:
        return
    cur.execute("UPDATE unidades_patrimonio SET codigo=? WHERE id=? AND (codigo IS NULL OR codigo='')",
                (novo_codigo, up_id))


def sync_qty(cur, mat_id):
    """Recalcula quantidade como número de UPs ativas não-atribuídas."""
    cur.execute(
        """SELECT COUNT(*) FROM unidades_patrimonio
           WHERE material_id=? AND status='ativo' AND (tag IS NULL OR tag NOT IN ('atribuido','solicitado'))""",
        (mat_id,),
    )
    qty = cur.fetchone()[0]
    cur.execute("UPDATE materiais SET quantidade=? WHERE id=?", (qty, mat_id))


def criar_up_e_item(cur, ativo_id, mat_id, codigo, stats):
    """Cria UnidadePatrimonio + AtivoItem. Retorna True se criou."""
    tag = "atribuido"
    codigo_val = codigo if codigo else None

    if DRY_RUN:
        stats["criados"] += 1
        return True

    # UP
    cur.execute(
        """INSERT INTO unidades_patrimonio
           (material_id, status, origem, tag, codigo, criado_em)
           VALUES (?,?,?,?,?,?)""",
        (mat_id, "ativo", "importacao_planilha", tag, codigo_val, now_iso()),
    )
    up_id = cur.lastrowid

    # AtivoItem
    cur.execute(
        """INSERT INTO ativos_itens
           (ativo_id, material_id, unidade_id, quantidade, atribuido_em)
           VALUES (?,?,?,1.0,?)""",
        (ativo_id, mat_id, up_id, now_iso()),
    )
    sync_qty(cur, mat_id)
    stats["criados"] += 1
    return True


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"{'[DRY-RUN] ' if DRY_RUN else ''}Banco: {DB_PATH}")
    print(f"Planilha: {XLSX}\n")

    itens = ler_planilha(XLSX)
    print(f"Itens na planilha: {len(itens)}\n")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    criados_ativo = {}   # chave → id fictício ou real
    criados_mat = {}     # nome_real → id
    grupos_criados = {}  # placeholder_id → real_id

    stats = {
        "criados": 0,
        "pulados_dup": 0,
        "sem_mapeamento": 0,
        "ativos_criados": [],
        "materiais_criados": [],
    }

    for item in itens:
        nome_at = item["nome_ativo"]
        grp_at  = item["grp_ativo"]
        nome_mat = item["nome_mat"]
        codigo   = item["codigo"]

        # ── ativo ──
        ativo_id, ativo_novo = resolve_ativo_id(cur, nome_at, grp_at, criados_ativo)
        if ativo_id is None:
            print(f"  [SEM_MAPA] ativo='{nome_at}' grp='{grp_at}'  mat='{nome_mat}'")
            stats["sem_mapeamento"] += 1
            continue
        if ativo_novo:
            chave = (nome_at.lower(), grp_at.lower())
            stats["ativos_criados"].append(NOVO_ATIVO_NOME.get(chave, f"{grp_at} - {nome_at}"))

        # ── material ──
        mat_id, mat_novo = resolve_mat_id(cur, nome_mat, criados_mat, grupos_criados)
        if mat_id is None:
            print(f"  [SEM_MAT]  ativo='{nome_at}'  mat='{nome_mat}'")
            stats["sem_mapeamento"] += 1
            continue
        if mat_novo:
            nome_real = PLANILHA_MAT_ALIAS.get(nome_mat, nome_mat)
            stats["materiais_criados"].append(nome_real)

        # ── verificar duplicata ──
        existe, up_id, up_cod = ja_atribuido(cur, ativo_id, mat_id)
        if existe:
            # atualizar código se a planilha tem mas o servidor não tem
            if codigo and not up_cod:
                atualizar_codigo_up(cur, up_id, codigo)
                if DRY_RUN:
                    print(f"  ~ {nome_at:22s} | {nome_mat:45s} atualiza cod → {codigo}")
                else:
                    print(f"  ~ {nome_at:22s} | código atualizado → {codigo}")
                stats["cod_atualizados"] = stats.get("cod_atualizados", 0) + 1
            else:
                stats["pulados_dup"] += 1
            continue

        # ── criar ──
        cod_info = f" cod={codigo}" if codigo else ""
        print(f"  + {nome_at:22s} | {nome_mat:45s}{cod_info}")
        criar_up_e_item(cur, ativo_id, mat_id, codigo, stats)

    if not DRY_RUN:
        conn.commit()

    conn.close()

    print("\n" + "=" * 60)
    print(f"Modo: {'DRY-RUN (nenhuma alteração feita)' if DRY_RUN else 'APLICADO'}")
    print(f"Atribuições criadas:    {stats['criados']}")
    print(f"Puladas (já existem):   {stats['pulados_dup']}")
    if stats.get("cod_atualizados"):
        print(f"Códigos atualizados:    {stats['cod_atualizados']}")
    print(f"Sem mapeamento:         {stats['sem_mapeamento']}")
    if stats["ativos_criados"]:
        print(f"Ativos criados:         {', '.join(stats['ativos_criados'])}")
    if stats["materiais_criados"]:
        print(f"Materiais criados:      {', '.join(set(stats['materiais_criados']))}")


if __name__ == "__main__":
    main()
