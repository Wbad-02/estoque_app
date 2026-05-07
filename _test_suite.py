"""
Test suite completo — estoque_app
Cobre: patrimônio, materiais (criar/entrada), retiradas, ativos, notificações, usuários.
"""
import sys, os, json
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

import urllib.request
import urllib.parse
import urllib.error

BASE = "http://localhost:8000/api"
TOKEN = None
PASS_COUNT = 0
FAIL_COUNT = 0
CREATED = {}

# Pré-limpeza: remove resíduos de runs anteriores diretamente no banco
import sqlite3 as _sql
_conn = _sql.connect("estoque.db")
_conn.execute("DELETE FROM usuarios WHERE email='test_tmp@teste.internal'")
_conn.commit(); _conn.close()


def _req(method, path, body=None, token=None):
    global TOKEN
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    tok = token or TOKEN
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            resp_body = r.read().decode()
            code = r.getcode()
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode()
        code = e.code
    try:
        parsed = json.loads(resp_body) if resp_body else {}
    except Exception:
        parsed = {"_raw": resp_body}
    return code, parsed


def chk(label, ok, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if ok:
        PASS_COUNT += 1
        print(f"  PASS  {label}")
    else:
        FAIL_COUNT += 1
        print(f"  FAIL  {label}  <- {detail}")


def section(title):
    print(f"\n=== {title} ===")


# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────
section("AUTH")
code, r = _req("POST", "/auth/login",
               {"email": "ci@teste.internal", "senha": "TesteSeg123!"})
if code == 200 and r.get("access_token"):
    TOKEN = r["access_token"]
    print(f"  LOGIN OK | grupo={r.get('grupo')}")
else:
    print(f"  LOGIN FALHOU ({code}): {r}")
    sys.exit(1)

code, me = _req("GET", "/usuarios/me")
chk("GET /usuarios/me", code == 200 and me.get("email") == "ci@teste.internal", me)


# ──────────────────────────────────────────────
# MATERIAIS — criar sem qty/unidade
# ──────────────────────────────────────────────
section("MATERIAIS — CRUD")

code, grupos = _req("GET", "/grupos/")
chk("GET /grupos/ pre-req", code == 200)
grupo_id = grupos[0]["id"] if grupos else None

# criar material (sem quantidade — novo comportamento; 201 é o código correto)
code, mat = _req("POST", "/materiais/", {
    "nome": "__TEST_MATERIAL__",
    "grupo_id": grupo_id,
    "unidade": "un",
    "quantidade": 0,
    "quantidade_minima": 0,
    "usa_patrimonio": False,
})
chk("POST /materiais/ retorna 201", code == 201, f"got {code}: {mat}")
mat_id = mat.get("id")
CREATED["mat_id"] = mat_id
qty_inicial = mat.get("quantidade", -1)
chk("POST /materiais/ quantidade inicial = 0", qty_inicial == 0.0, f"got {qty_inicial}")

# GET individual
code, mat2 = _req("GET", f"/materiais/{mat_id}")
chk("GET /materiais/{id}", code == 200 and mat2.get("id") == mat_id)

# PUT editar nome (método correto é PUT)
code, mat3 = _req("PUT", f"/materiais/{mat_id}", {
    "nome": "__TEST_MATERIAL_EDIT__",
    "grupo_id": grupo_id,
    "unidade": "un",
    "quantidade": 0,
    "quantidade_minima": 0,
    "usa_patrimonio": False,
})
chk("PUT /materiais/{id} edita", code == 200 and mat3.get("nome") == "__TEST_MATERIAL_EDIT__", mat3)

# entrada de material (não-patrimônio path)
code, ent = _req("POST", f"/materiais/{mat_id}/entrada", {
    "quantidade": 5,
    "observacao": "test entrada",
})
chk("POST /materiais/{id}/entrada retorna 200", code == 200, ent)
code, mat4 = _req("GET", f"/materiais/{mat_id}")
chk("entrada sincroniza quantidade (0→5)", mat4.get("quantidade") == 5.0,
    f"esperado 5.0, got {mat4.get('quantidade')}")

# segunda entrada acumula
code, ent2 = _req("POST", f"/materiais/{mat_id}/entrada", {"quantidade": 3})
code, mat5 = _req("GET", f"/materiais/{mat_id}")
chk("segunda entrada acumula (5→8)", mat5.get("quantidade") == 8.0,
    f"esperado 8.0, got {mat5.get('quantidade')}")


# ──────────────────────────────────────────────
# PATRIMÔNIO — material com usa_patrimonio=True
# ──────────────────────────────────────────────
section("PATRIMÔNIO")

code, matp = _req("POST", "/materiais/", {
    "nome": "__TEST_PATRIM__",
    "grupo_id": grupo_id,
    "unidade": "un",
    "quantidade": 0,
    "quantidade_minima": 0,
    "usa_patrimonio": True,
})
chk("POST /materiais/ usa_patrimonio=True retorna 201", code == 201, matp)
matp_id = matp.get("id")
CREATED["matp_id"] = matp_id

# listar unidades (deve estar vazio)
code, units = _req("GET", f"/patrimonio/{matp_id}/unidades")
chk("GET /patrimonio/{id}/unidades vazio inicialmente", code == 200 and len(units) == 0,
    f"code={code}, count={len(units) if isinstance(units, list) else units}")

# adicionar 3 unidades (201)
code, add_r = _req("POST", f"/patrimonio/{matp_id}/unidades", [
    {"tag": "novo", "numero_serie": "SN-TEST-001"},
    {"tag": "novo", "numero_serie": "SN-TEST-002"},
    {"tag": "novo", "numero_serie": "SN-TEST-003"},
])
chk("POST /patrimonio/{id}/unidades retorna 201", code == 201, add_r)
chk("POST /patrimonio/{id}/unidades criou 3", add_r.get("criadas") == 3, add_r)

# verificar sync_qty
code, mat_sync = _req("GET", f"/materiais/{matp_id}")
chk("sync_qty após adicionar 3 unidades (0→3)", mat_sync.get("quantidade") == 3.0,
    f"esperado 3.0, got {mat_sync.get('quantidade')}")

# listar unidades
code, units2 = _req("GET", f"/patrimonio/{matp_id}/unidades")
chk("GET /patrimonio/{id}/unidades retorna 3", len(units2) == 3,
    f"got {len(units2) if isinstance(units2, list) else units2}")
unit_id_1 = units2[0]["id"] if units2 else None
unit_id_2 = units2[1]["id"] if len(units2) > 1 else None
unit_id_3 = units2[2]["id"] if len(units2) > 2 else None

# retirar unidade (201)
code, ret_r = _req("POST", f"/patrimonio/{matp_id}/retirar-unidade", {
    "unidade_id": unit_id_1,
    "motivo": "Descarte",
    "observacao": "saida teste",
})
chk("POST /patrimonio/{id}/retirar-unidade retorna 201", code == 201, ret_r)
chk("retirada tem nome_material", ret_r.get("nome_material") == "__TEST_PATRIM__", ret_r)

# sync_qty após retirada
code, mat_after_ret = _req("GET", f"/materiais/{matp_id}")
chk("sync_qty após retirar unidade (3→2)", mat_after_ret.get("quantidade") == 2.0,
    f"esperado 2.0, got {mat_after_ret.get('quantidade')}")

# tentar retirar mesma unidade novamente (deve falhar com 422)
code, ret_dup = _req("POST", f"/patrimonio/{matp_id}/retirar-unidade", {
    "unidade_id": unit_id_1,
    "motivo": "dup",
})
chk("retirar unidade já retirada retorna 422", code == 422, f"got {code}: {ret_dup}")


# ──────────────────────────────────────────────
# RETIRADAS — paginação (após fix do selectinload)
# ──────────────────────────────────────────────
section("RETIRADAS")

code, rets_all = _req("GET", "/retiradas/")
chk("GET /retiradas/ lista", code == 200 and isinstance(rets_all, list), rets_all)
total_rets = len(rets_all)

# paginação — limit menor que total
if total_rets > 2:
    code, rets_pg = _req("GET", f"/retiradas/?skip=0&limit={total_rets - 1}")
    chk(f"GET /retiradas/?limit={total_rets-1} respeita limite",
        code == 200 and len(rets_pg) == total_rets - 1,
        f"total={total_rets}, esperado {total_rets-1}, got {len(rets_pg)}")

code, rets_pg5 = _req("GET", "/retiradas/?skip=0&limit=5")
chk("GET /retiradas/?limit=5 retorna <=5", code == 200 and len(rets_pg5) <= 5,
    f"got {len(rets_pg5)}")

code, rets_skip = _req("GET", "/retiradas/?skip=999&limit=10")
chk("GET /retiradas/ skip alto retorna vazio", code == 200 and len(rets_skip) == 0,
    f"got {len(rets_skip)}")

# filtro por material
code, rets_mat = _req("GET", f"/retiradas/?material_id={matp_id}")
chk("GET /retiradas/?material_id= filtra por material", code == 200, rets_mat)
chk("retirada registrada aparece no histórico do material",
    len(rets_mat) >= 1, f"esperado >=1, got {len(rets_mat)}")


# ──────────────────────────────────────────────
# ATIVOS — usando endpoint correto de grupos
# ──────────────────────────────────────────────
section("ATIVOS")

# listar categorias de ativos
code, ativo_cats = _req("GET", "/ativos-categorias/")
chk("GET /ativos-categorias/ lista", code == 200 and isinstance(ativo_cats, list), ativo_cats)

# listar grupos de ativos
code, ativo_grupos = _req("GET", "/ativos-categorias/grupos/")
chk("GET /ativos-categorias/grupos/ lista", code == 200, ativo_grupos)

# criar categoria e grupo de ativo se não existirem
if not ativo_cats:
    code, new_cat = _req("POST", "/ativos-categorias/", {"nome": "__TEST_CAT_ATIVO__"})
    chk("POST /ativos-categorias/ cria", code == 201, new_cat)
    ativo_cat_id = new_cat.get("id")
else:
    ativo_cat_id = ativo_cats[0]["id"]

if not ativo_grupos:
    code, new_ga = _req("POST", "/ativos-categorias/grupos/", {
        "nome": "__TEST_GRUPO_ATIVO__",
        "categoria_id": ativo_cat_id,
    })
    chk("POST /ativos-categorias/grupos/ cria", code == 201, new_ga)
    grupo_ativo_id = new_ga.get("id")
else:
    grupo_ativo_id = ativo_grupos[0]["id"]

# criar ativo (201)
code, ativo = _req("POST", "/ativos/", {
    "nome": "__TEST_ATIVO__",
    "grupo_id": grupo_ativo_id,
    "descricao": "ativo de teste",
})
chk("POST /ativos/ cria ativo (201)", code == 201, ativo)
ativo_id = ativo.get("id")
CREATED["ativo_id"] = ativo_id

# listar ativos ativos
code, ativos = _req("GET", "/ativos/")
chk("GET /ativos/ lista ativos ativos", code == 200, ativos)
chk("ativo criado aparece na lista", any(a["id"] == ativo_id for a in ativos),
    f"id={ativo_id} not in {[a['id'] for a in ativos]}")

# atribuir unidade ao ativo (requer material_id + unidade_id)
code, attr_r = _req("POST", f"/ativos/{ativo_id}/atribuir", {
    "material_id": matp_id,
    "unidade_id": unit_id_2,
})
chk("POST /ativos/{id}/atribuir unidade", code == 200 or code == 201, f"{code}: {attr_r}")
item_id = attr_r.get("id")

# sync_qty após atribuição (atribuído sai da contagem disponível)
code, mat_after_attr = _req("GET", f"/materiais/{matp_id}")
chk("sync_qty após atribuição (tag=atribuido exclui da contagem)",
    mat_after_attr.get("quantidade") == 1.0,
    f"esperado 1.0, got {mat_after_attr.get('quantidade')}")

# verificar ativo_nome no GET unidades
code, units3 = _req("GET", f"/patrimonio/{matp_id}/unidades")
chk("GET /patrimonio/{id}/unidades após atribuição ok", code == 200 and isinstance(units3, list),
    f"code={code}, resp={units3}")
atribuida = next((u for u in units3 if isinstance(units3, list) and u["id"] == unit_id_2), None)
chk("unidade atribuída tem ativo_nome preenchido",
    atribuida and atribuida.get("ativo_nome") not in (None, ""),
    f"ativo_nome='{atribuida.get('ativo_nome') if atribuida else 'unit not found'}' — "
    f"tag='{atribuida.get('tag') if atribuida else '?'}'")
chk("unidade atribuída tem ativo_categoria preenchido",
    atribuida and atribuida.get("ativo_categoria") not in (None, ""),
    f"ativo_categoria='{atribuida.get('ativo_categoria') if atribuida else '?'}'")

# devolver item
if item_id:
    code, dev_r = _req("POST", f"/ativos/{ativo_id}/devolver/{item_id}", {
        "observacao": "devolucao teste",
    })
    chk("POST /ativos/{id}/devolver/{item_id}", code in (200, 204), f"{code}: {dev_r}")

    # sync_qty após devolução (unidade volta ao estoque)
    code, mat_after_dev = _req("GET", f"/materiais/{matp_id}")
    chk("sync_qty após devolução (volta ao estoque: 1→2)",
        mat_after_dev.get("quantidade") == 2.0,
        f"esperado 2.0, got {mat_after_dev.get('quantidade')}")

# inativar ativo (DELETE → 204)
code, _ = _req("DELETE", f"/ativos/{ativo_id}")
chk("DELETE /ativos/{id} inativa (204)", code == 204, f"got {code}")

# verificar lista inativos
code, inativos = _req("GET", "/ativos/inativos")
chk("GET /ativos/inativos inclui ativo inativado",
    code == 200 and any(a["id"] == ativo_id for a in inativos),
    f"id={ativo_id} not in {[a['id'] for a in inativos]}")

# reativar ativo
code, reativ_r = _req("POST", f"/ativos/{ativo_id}/reativar")
chk("POST /ativos/{id}/reativar retorna 200", code == 200, reativ_r)
chk("ativo reativado tem ativo=True", reativ_r.get("ativo") == True, reativ_r)
chk("ativo reativado volta com itens vazios", len(reativ_r.get("itens", [])) == 0,
    f"itens={reativ_r.get('itens')}")

# sync_qty após reativação (unidade devolvida já estava no estoque)
code, mat_after_reativ = _req("GET", f"/materiais/{matp_id}")
chk("quantidade estoque preservada após reativar ativo",
    mat_after_reativ.get("quantidade") == 2.0,
    f"esperado 2.0, got {mat_after_reativ.get('quantidade')}")

# ativo volta à lista de ativos
code, ativos2 = _req("GET", "/ativos/")
chk("ativo reativado aparece em /ativos/",
    any(a["id"] == ativo_id for a in ativos2),
    f"id={ativo_id} not in active list")


# ──────────────────────────────────────────────
# NOTIFICAÇÕES
# ──────────────────────────────────────────────
section("NOTIFICAÇÕES")

code, notif_emails = _req("GET", "/notificacoes/emails")
chk("GET /notificacoes/emails", code == 200 and isinstance(notif_emails, list), notif_emails)

code, templates = _req("GET", "/notificacoes/templates")
chk("GET /notificacoes/templates", code == 200 and isinstance(templates, list), templates)

code, smtp_cfg = _req("GET", "/notificacoes/smtp")
chk("GET /notificacoes/smtp", code in (200, 404), smtp_cfg)

# enviar alertas manuais (endpoint correto é /alertas/enviar)
code, alerta_r = _req("POST", "/notificacoes/alertas/enviar")
chk("POST /notificacoes/alertas/enviar não quebra", code in (200, 400, 422), alerta_r)


# ──────────────────────────────────────────────
# USUÁRIOS
# ──────────────────────────────────────────────
section("USUÁRIOS")

code, users = _req("GET", "/usuarios/")
chk("GET /usuarios/ lista", code == 200 and isinstance(users, list), users)

# criar usuário temporário (201)
code, new_user = _req("POST", "/usuarios/", {
    "nome": "__TEST_USER__",
    "email": "test_tmp@teste.internal",
    "senha": "Senha123!@",
    "grupo": "viewer",
    "ativo": True,
})
chk("POST /usuarios/ cria usuário (201)", code == 201, new_user)
new_user_id = new_user.get("id")

# editar (PUT)
if new_user_id:
    code, upd_u = _req("PUT", f"/usuarios/{new_user_id}", {
        "nome": "__TEST_USER_EDIT__",
        "email": "test_tmp@teste.internal",
        "grupo": "viewer",
        "ativo": True,
    })
    chk("PUT /usuarios/{id}", code == 200, f"{code}: {upd_u}")

    # deletar (204)
    code, _ = _req("DELETE", f"/usuarios/{new_user_id}")
    chk("DELETE /usuarios/{id} (204)", code == 204, f"got {code}")


# ──────────────────────────────────────────────
# LOGS / HISTÓRICO
# ──────────────────────────────────────────────
section("LOGS / AUDITORIA")
# Endpoint de auditoria não está exposto via API — apenas internal (auth.py)
# Verificar que a rota retorna 404 (não exposta, não 500)
code, _ = _req("GET", "/logs/")
chk("GET /logs/ retorna 404 (não exposto)", code == 404, f"got {code}")


# ──────────────────────────────────────────────
# CATEGORIAS & GRUPOS (read-only)
# ──────────────────────────────────────────────
section("CATEGORIAS E GRUPOS")

code, cats = _req("GET", "/categorias/")
chk("GET /categorias/", code == 200 and len(cats) > 0, cats)

code, gs = _req("GET", "/grupos/")
chk("GET /grupos/", code == 200 and len(gs) > 0, gs)


# ──────────────────────────────────────────────
# CLEANUP
# ──────────────────────────────────────────────
section("CLEANUP")

for key, mid in [("mat_id", CREATED.get("mat_id")), ("matp_id", CREATED.get("matp_id"))]:
    if mid:
        code, _ = _req("DELETE", f"/materiais/{mid}")
        chk(f"DELETE /materiais/{mid} ({key}) → 204", code == 204, f"got {code}")

if CREATED.get("ativo_id"):
    code, _ = _req("DELETE", f"/ativos/{CREATED['ativo_id']}")
    chk(f"DELETE /ativos/{CREATED['ativo_id']} cleanup → 204", code == 204, f"got {code}")


# ──────────────────────────────────────────────
# RESULTADO
# ──────────────────────────────────────────────
total = PASS_COUNT + FAIL_COUNT
print(f"\n{'='*50}")
print(f"TOTAL: {PASS_COUNT} OK, {FAIL_COUNT} FAIL  ({total} testes)")
if FAIL_COUNT == 0:
    print("TODOS OS TESTES PASSARAM")
else:
    print(f"ATENCAO: {FAIL_COUNT} FALHA(S) DETECTADA(S)")
sys.exit(0 if FAIL_COUNT == 0 else 1)
