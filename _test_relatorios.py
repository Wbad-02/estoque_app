# © Wbad-02 — Todos os direitos reservados.
"""
Script de teste para todos os endpoints de relatórios.
Faz login como admin e verifica status 200 + content-type em cada rota.
"""

import sys
import requests

BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
RELATORIOS_URL = f"{BASE_URL}/api/relatorios"

CREDENCIAIS = {"email": "admin@estoque.local", "senha": "admin123"}

CT_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CT_PDF = "application/pdf"
CT_JSON = "application/json"


# ── Definição dos testes ─────────────────────────────────────

TESTES = [
    # (nome, método, url, content-type esperado, é JSON?)
    # Estoque completo
    ("Estoque Excel",                  f"{RELATORIOS_URL}/excel",                             CT_EXCEL, False),
    ("Estoque PDF",                    f"{RELATORIOS_URL}/pdf",                               CT_PDF,   False),
    ("Estoque Excel (alertas)",        f"{RELATORIOS_URL}/excel?apenas_alertas=true",         CT_EXCEL, False),
    ("Estoque PDF (alertas)",          f"{RELATORIOS_URL}/pdf?apenas_alertas=true",           CT_PDF,   False),

    # Saídas
    ("Saídas Excel",                   f"{RELATORIOS_URL}/saidas/excel",                      CT_EXCEL, False),
    ("Saídas PDF",                     f"{RELATORIOS_URL}/saidas/pdf",                        CT_PDF,   False),

    # Geral (estoque consolidado)
    ("Geral JSON",                     f"{RELATORIOS_URL}/geral",                             CT_JSON,  True),
    ("Geral Excel",                    f"{RELATORIOS_URL}/geral/excel",                       CT_EXCEL, False),
    ("Geral PDF",                      f"{RELATORIOS_URL}/geral/pdf",                         CT_PDF,   False),

    # Entradas NF-e
    ("Entradas NF-e JSON",             f"{RELATORIOS_URL}/entradas-nfe?mes=6&ano=2026",       CT_JSON,  True),
    ("Entradas NF-e Excel",            f"{RELATORIOS_URL}/entradas-nfe/excel?mes=6&ano=2026", CT_EXCEL, False),
    ("Entradas NF-e PDF",              f"{RELATORIOS_URL}/entradas-nfe/pdf?mes=6&ano=2026",   CT_PDF,   False),

    # Ativos (hierárquico)
    ("Ativos JSON",                    f"{RELATORIOS_URL}/ativos?status=ativo",               CT_JSON,  True),
    ("Ativos Excel",                   f"{RELATORIOS_URL}/ativos/excel?status=ativo",         CT_EXCEL, False),
    ("Ativos PDF",                     f"{RELATORIOS_URL}/ativos/pdf?status=ativo",           CT_PDF,   False),

    # Consumo médio
    ("Consumo Médio JSON",             f"{RELATORIOS_URL}/consumo-medio?meses=3",             CT_JSON,  True),
    ("Consumo Médio Excel",            f"{RELATORIOS_URL}/consumo-medio/excel",               CT_EXCEL, False),
    ("Consumo Médio PDF",              f"{RELATORIOS_URL}/consumo-medio/pdf",                 CT_PDF,   False),

    # Solicitações por material
    ("Solicitações/Material JSON",     f"{RELATORIOS_URL}/solicitacoes-por-material",         CT_JSON,  True),
    ("Solicitações/Material Excel",    f"{RELATORIOS_URL}/solicitacoes-por-material/excel",   CT_EXCEL, False),
    ("Solicitações/Material PDF",      f"{RELATORIOS_URL}/solicitacoes-por-material/pdf",     CT_PDF,   False),

    # Valor imobilizado
    ("Valor Imobilizado JSON",         f"{RELATORIOS_URL}/valor-imobilizado",                 CT_JSON,  True),
    ("Valor Imobilizado Excel",        f"{RELATORIOS_URL}/valor-imobilizado/excel",           CT_EXCEL, False),
    ("Valor Imobilizado PDF",          f"{RELATORIOS_URL}/valor-imobilizado/pdf",             CT_PDF,   False),

    # Notificações
    ("Notificações Excel",             f"{RELATORIOS_URL}/notificacoes/excel",                CT_EXCEL, False),

    # Entradas gerais
    ("Entradas JSON",                  f"{RELATORIOS_URL}/entradas",                          CT_JSON,  True),
    ("Entradas Excel",                 f"{RELATORIOS_URL}/entradas/excel",                    CT_EXCEL, False),
    ("Entradas PDF",                   f"{RELATORIOS_URL}/entradas/pdf",                      CT_PDF,   False),

    # Requerimentos consolidado
    ("Requerimentos JSON",             f"{RELATORIOS_URL}/requerimentos",                     CT_JSON,  True),
    ("Requerimentos Excel",            f"{RELATORIOS_URL}/requerimentos/excel",               CT_EXCEL, False),
    ("Requerimentos PDF",              f"{RELATORIOS_URL}/requerimentos/pdf",                 CT_PDF,   False),

    # NF-e por fornecedor
    ("NF-e Fornecedores JSON",         f"{RELATORIOS_URL}/nfe-fornecedores",                  CT_JSON,  True),
    ("NF-e Fornecedores Excel",        f"{RELATORIOS_URL}/nfe-fornecedores/excel",            CT_EXCEL, False),
    ("NF-e Fornecedores PDF",          f"{RELATORIOS_URL}/nfe-fornecedores/pdf",              CT_PDF,   False),

    # ABC/Pareto
    ("ABC JSON",                       f"{RELATORIOS_URL}/abc",                               CT_JSON,  True),
    ("ABC Excel",                      f"{RELATORIOS_URL}/abc/excel",                         CT_EXCEL, False),
    ("ABC PDF",                        f"{RELATORIOS_URL}/abc/pdf",                           CT_PDF,   False),

    # Patrimônio/Inventário
    ("Patrimônio JSON",                f"{RELATORIOS_URL}/patrimonio?status=ativo",           CT_JSON,  True),
    ("Patrimônio Excel",               f"{RELATORIOS_URL}/patrimonio/excel?status=ativo",     CT_EXCEL, False),
    ("Patrimônio PDF",                 f"{RELATORIOS_URL}/patrimonio/pdf?status=ativo",       CT_PDF,   False),
]

TESTES_EXTRAS = [
    # (nome, url, content-type esperado, é JSON?)
    ("Auditoria (admin)",              f"{BASE_URL}/api/auditoria/",                          CT_JSON,  True),
    ("Auditoria Excel",                f"{BASE_URL}/api/auditoria/excel",                     CT_EXCEL, False),
    ("Auditoria PDF",                  f"{BASE_URL}/api/auditoria/pdf",                       CT_PDF,   False),
    ("Motivos Dinâmicos",              f"{BASE_URL}/api/motivos/",                            CT_JSON,  True),

    # Atividade por usuário (admin)
    ("Atividade Usuários JSON",        f"{BASE_URL}/api/relatorios/atividade-usuarios",       CT_JSON,  True),
    ("Atividade Usuários Excel",       f"{BASE_URL}/api/relatorios/atividade-usuarios/excel", CT_EXCEL, False),
    ("Atividade Usuários PDF",         f"{BASE_URL}/api/relatorios/atividade-usuarios/pdf",   CT_PDF,   False),
]


# ── Funções auxiliares ───────────────────────────────────────

def fazer_login() -> str | None:
    """Faz login e retorna o token JWT, ou None em caso de falha."""
    try:
        resp = requests.post(LOGIN_URL, json=CREDENCIAIS, timeout=10)
        if resp.status_code != 200:
            print(f"[ERRO] Login falhou — status {resp.status_code}: {resp.text}")
            return None
        token = resp.json().get("access_token")
        if not token:
            print("[ERRO] Login retornou 200, mas sem access_token no corpo.")
            return None
        print(f"[OK]   Login realizado com sucesso (token obtido)\n")
        return token
    except requests.ConnectionError:
        print(f"[ERRO] Não foi possível conectar em {BASE_URL}. O servidor está rodando?")
        return None
    except Exception as exc:
        print(f"[ERRO] Exceção inesperada no login: {exc}")
        return None


def executar_teste(nome: str, url: str, ct_esperado: str, eh_json: bool, headers: dict) -> bool:
    """Executa um GET e valida status + content-type. Retorna True se passou."""
    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except Exception as exc:
        print(f"[FALHOU] {nome:<40} — Exceção: {exc}")
        return False

    # Verificar status 200
    if resp.status_code != 200:
        print(f"[FALHOU] {nome:<40} — Status {resp.status_code}: {resp.text[:120]}")
        return False

    # Verificar content-type
    ct_real = resp.headers.get("content-type", "")
    if ct_esperado not in ct_real:
        print(f"[FALHOU] {nome:<40} — Content-Type esperado '{ct_esperado}', recebido '{ct_real}'")
        return False

    # Para JSON, verificar que o corpo é válido
    if eh_json:
        try:
            dados = resp.json()
            # Verifica que não é None/vazio de forma inesperada
            if dados is None:
                print(f"[FALHOU] {nome:<40} — JSON retornou None")
                return False
            tipo = "lista" if isinstance(dados, list) else "objeto"
            tamanho = len(dados) if isinstance(dados, (list, dict)) else "?"
            print(f"[OK]    {nome:<40} — JSON válido ({tipo}, {tamanho} itens)")
        except ValueError:
            print(f"[FALHOU] {nome:<40} — Corpo não é JSON válido")
            return False
    else:
        # Para binários (Excel/PDF), verificar tamanho > 0
        tamanho = len(resp.content)
        if tamanho == 0:
            print(f"[FALHOU] {nome:<40} — Arquivo vazio (0 bytes)")
            return False
        tamanho_kb = tamanho / 1024
        ext = "xlsx" if "spreadsheet" in ct_esperado else "pdf"
        print(f"[OK]    {nome:<40} — {ext.upper()} recebido ({tamanho_kb:.1f} KB)")

    return True


# ── Main ─────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  TESTE DE ENDPOINTS DE RELATÓRIOS — Estoque Privado")
    print("=" * 65)
    print()

    # 1. Login
    print("--- Autenticação ---")
    token = fazer_login()
    if not token:
        print("\nAbortando: não foi possível obter o token de autenticação.")
        sys.exit(1)

    auth_headers = {"Authorization": f"Bearer {token}"}

    # 2. Testes de relatórios
    print("--- Relatórios (/api/relatorios) ---")
    passou = 0
    total = 0

    for nome, url, ct, eh_json in TESTES:
        total += 1
        if executar_teste(nome, url, ct, eh_json, auth_headers):
            passou += 1

    # 3. Testes extras (auditoria, motivos)
    print()
    print("--- Endpoints Extras ---")
    for nome, url, ct, eh_json in TESTES_EXTRAS:
        total += 1
        if executar_teste(nome, url, ct, eh_json, auth_headers):
            passou += 1

    # 4. Resumo final
    print()
    print("=" * 65)
    falhou = total - passou
    if falhou == 0:
        print(f"  RESULTADO: {passou}/{total} testes passaram. Tudo OK!")
    else:
        print(f"  RESULTADO: {passou}/{total} testes passaram. {falhou} FALHOU(ARAM)!")
    print("=" * 65)

    sys.exit(0 if falhou == 0 else 1)


if __name__ == "__main__":
    main()
