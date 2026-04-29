# © Todos os direitos reservados – github.com/Wbad-02
"""
Backup automático do banco SQLite.

Uso direto:
    python backup.py

Agendamento (Windows Task Scheduler):
    Programa: python
    Argumentos: "C:\caminho\estoque_app\backup.py"
    Frequência: diária

Mantém os últimos MANTER_BACKUPS arquivos e remove os mais antigos.
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

DB_ORIGEM    = Path(__file__).parent / "estoque.db"
BACKUP_DIR   = Path(__file__).parent / "backups"
MANTER_BACKUPS = 30  # quantos arquivos manter


def fazer_backup() -> Path:
    if not DB_ORIGEM.exists():
        print(f"[backup] ERRO: banco não encontrado em {DB_ORIGEM}")
        sys.exit(1)

    BACKUP_DIR.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = BACKUP_DIR / f"estoque_backup_{ts}.db"
    shutil.copy2(DB_ORIGEM, destino)
    print(f"[backup] Backup criado: {destino.name} ({destino.stat().st_size // 1024} KB)")
    return destino


def limpar_antigos():
    arquivos = sorted(BACKUP_DIR.glob("estoque_backup_*.db"), key=lambda p: p.stat().st_mtime)
    excedentes = arquivos[:-MANTER_BACKUPS] if len(arquivos) > MANTER_BACKUPS else []
    for arq in excedentes:
        arq.unlink()
        print(f"[backup] Removido backup antigo: {arq.name}")


if __name__ == "__main__":
    fazer_backup()
    limpar_antigos()
    print("[backup] Concluído.")
