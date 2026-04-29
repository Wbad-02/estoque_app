# © Todos os direitos reservados – github.com/Wbad-02
"""
Script de migração do banco de dados.
Adiciona colunas novas sem apagar nenhum dado existente.

Execute UMA VEZ após atualizar o sistema:
    python migrar_banco.py
"""
import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

DB_PATH = Path("estoque.db")

def migrar():
    if not DB_PATH.exists():
        print("❌ Banco 'estoque.db' não encontrado. Rode o sistema uma vez primeiro.")
        return

    # Backup automático antes de qualquer alteração
    backup = Path(f"estoque_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    shutil.copy2(DB_PATH, backup)
    print(f"✅ Backup criado: {backup}")

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    def coluna_existe(tabela, coluna):
        cur.execute(f"PRAGMA table_info({tabela})")
        return any(r[1] == coluna for r in cur.fetchall())

    migracoes = 0

    # ── 1. materiais.usa_patrimonio ──────────────────────────────
    if not coluna_existe("materiais", "usa_patrimonio"):
        cur.execute("ALTER TABLE materiais ADD COLUMN usa_patrimonio BOOLEAN DEFAULT 0")
        print("✅ Coluna adicionada: materiais.usa_patrimonio (padrão: False)")
        migracoes += 1
    else:
        print("   materiais.usa_patrimonio já existe — ok")

    # ── 2. movimentacoes.unidade_id ──────────────────────────────
    if not coluna_existe("movimentacoes", "unidade_id"):
        cur.execute("""
            ALTER TABLE movimentacoes
            ADD COLUMN unidade_id INTEGER REFERENCES unidades_patrimonio(id)
        """)
        print("✅ Coluna adicionada: movimentacoes.unidade_id (padrão: NULL)")
        migracoes += 1
    else:
        print("   movimentacoes.unidade_id já existe — ok")

    # ── 3. unidades_patrimonio.origem ───────────────────────────
    if not coluna_existe("unidades_patrimonio", "origem"):
        cur.execute("ALTER TABLE unidades_patrimonio ADD COLUMN origem VARCHAR(20) DEFAULT 'manual'")
        print("✅ Coluna adicionada: unidades_patrimonio.origem (padrão: manual)")
        migracoes += 1
    else:
        print("   unidades_patrimonio.origem já existe — ok")

    # ── 4. unidades_patrimonio.nf_numero ─────────────────────────
    if not coluna_existe("unidades_patrimonio", "nf_numero"):
        cur.execute("ALTER TABLE unidades_patrimonio ADD COLUMN nf_numero VARCHAR(50)")
        print("✅ Coluna adicionada: unidades_patrimonio.nf_numero (padrão: NULL)")
        migracoes += 1
    else:
        print("   unidades_patrimonio.nf_numero já existe — ok")

    # ── 5. materiais.valor_unitario ──────────────────────────────
    if not coluna_existe("materiais", "valor_unitario"):
        cur.execute("ALTER TABLE materiais ADD COLUMN valor_unitario REAL")
        print("✅ Coluna adicionada: materiais.valor_unitario (padrão: NULL)")
        migracoes += 1
    else:
        print("   materiais.valor_unitario já existe — ok")

    # ── 6. materiais.tag ─────────────────────────────────────────
    if not coluna_existe("materiais", "tag"):
        cur.execute("ALTER TABLE materiais ADD COLUMN tag VARCHAR(10)")
        print("✅ Coluna adicionada: materiais.tag (padrão: NULL)")
        migracoes += 1
    else:
        print("   materiais.tag já existe — ok")

    # ── 7. movimentacoes.valor_unitario ───────────────────────────
    if not coluna_existe("movimentacoes", "valor_unitario"):
        cur.execute("ALTER TABLE movimentacoes ADD COLUMN valor_unitario REAL")
        print("✅ Coluna adicionada: movimentacoes.valor_unitario (padrão: NULL)")
        migracoes += 1
    else:
        print("   movimentacoes.valor_unitario já existe — ok")

    # ── 8. unidades_patrimonio.valor_unitario ────────────────────
    if not coluna_existe("unidades_patrimonio", "valor_unitario"):
        cur.execute("ALTER TABLE unidades_patrimonio ADD COLUMN valor_unitario REAL")
        print("✅ Coluna adicionada: unidades_patrimonio.valor_unitario (padrão: NULL)")
        migracoes += 1
    else:
        print("   unidades_patrimonio.valor_unitario já existe — ok")

    # ── 9. unidades_patrimonio.tag ───────────────────────────────
    if not coluna_existe("unidades_patrimonio", "tag"):
        cur.execute("ALTER TABLE unidades_patrimonio ADD COLUMN tag VARCHAR(10)")
        print("✅ Coluna adicionada: unidades_patrimonio.tag (padrão: NULL)")
        migracoes += 1
    else:
        print("   unidades_patrimonio.tag já existe — ok")

    # ── 10. notificacoes_emails.intervalo_dias ──────────────────
    if not coluna_existe("notificacoes_emails", "intervalo_dias"):
        cur.execute("ALTER TABLE notificacoes_emails ADD COLUMN intervalo_dias INTEGER")
        print("✅ Coluna adicionada: notificacoes_emails.intervalo_dias (padrão: NULL)")
        migracoes += 1
    else:
        print("   notificacoes_emails.intervalo_dias já existe — ok")

    # ── 11. motivos_personalizados (nova tabela) ────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS motivos_personalizados (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nome      VARCHAR(100) NOT NULL UNIQUE,
            ativo     BOOLEAN NOT NULL DEFAULT 1,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ Tabela motivos_personalizados verificada/criada")

    # ── 12. movimentacoes.tag ────────────────────────────────────
    if not coluna_existe("movimentacoes", "tag"):
        cur.execute("ALTER TABLE movimentacoes ADD COLUMN tag VARCHAR(10)")
        print("✅ Coluna adicionada: movimentacoes.tag (padrão: NULL)")
        migracoes += 1
    else:
        print("   movimentacoes.tag já existe — ok")

    # ── 13. ativos_itens.unidade_id ─────────────────────────────
    if not coluna_existe("ativos_itens", "unidade_id"):
        cur.execute("""
            ALTER TABLE ativos_itens
            ADD COLUMN unidade_id INTEGER REFERENCES unidades_patrimonio(id)
        """)
        print("Coluna adicionada: ativos_itens.unidade_id (padrao: NULL)")
        migracoes += 1
    else:
        print("   ativos_itens.unidade_id ja existe -- ok")

    conn.commit()
    conn.close()

    print()
    if migracoes > 0:
        print(f"✅ Migração concluída — {migracoes} coluna(s) adicionada(s)")
        print("   Todos os dados anteriores foram preservados.")
    else:
        print("✅ Banco já estava atualizado — nenhuma alteração necessária.")

    print(f"   Backup salvo em: {backup}")

if __name__ == "__main__":
    migrar()
