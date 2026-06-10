"""
Corrige materiais criados incorretamente pelo ativo import:
- Fone (id=39), Mouse Sem Fio (id=38), Teclado (id=37): usa_patrimonio=False,
  qty=-46, 47 AtivoItems sem UnidadePatrimonio
- All-in-One (id=42): usa_patrimonio=False, 1 AtivoItem sem UP (Ana Julia)

Fix: para cada AtivoItem sem unidade_id, cria UnidadePatrimonio(atribuido),
vincula, limpa movimentacoes erroneas do import, converte para usa_patrimonio=True,
e recalcula qty via sync_qty.
"""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "i:/Meu Drive/WEMERSON/APLICATIVOS/estoque_app")

from database import SessionLocal
import models
from utils import sync_qty

db = SessionLocal()

# IDs a corrigir: (material_id, nome)
MATERIAIS = [
    (37, "Teclado"),
    (38, "Mouse Sem Fio"),
    (39, "Fone"),
    (42, "All-in-One"),
]

try:
    for mat_id, nome in MATERIAIS:
        mat = db.query(models.Material).filter(models.Material.id == mat_id).first()
        if not mat:
            print(f"  {nome} (id={mat_id}): NAO ENCONTRADO — pulando")
            continue

        # AtivoItems sem UP vinculada
        items_sem_up = db.query(models.AtivoItem).filter(
            models.AtivoItem.material_id == mat_id,
            models.AtivoItem.unidade_id == None,
            models.AtivoItem.devolvido_em == None,
        ).all()

        # Movimentacoes do import ativo (entrada + saidas falsas)
        movs_import = db.query(models.Movimentacao).filter(
            models.Movimentacao.material_id == mat_id,
            models.Movimentacao.observacao.in_([
                "Importacao via ativos (planilha)",
                "Atribuicao via importacao de ativos (planilha)",
            ]),
        ).all()

        print(f"\n{nome} (id={mat_id}): usa_patrimonio={mat.usa_patrimonio}, qty={mat.quantidade}")
        print(f"  AtivoItems sem UP: {len(items_sem_up)}")
        print(f"  Movimentacoes a remover: {len(movs_import)}")

        # Criar UP para cada AtivoItem sem unidade
        for item in items_sem_up:
            up = models.UnidadePatrimonio(
                material_id=mat_id,
                status=models.StatusUnidade.ativo,
                origem="importacao_ativo",
                tag="atribuido",
            )
            db.add(up)
            db.flush()
            item.unidade_id = up.id
            db.flush()

        # Remover movimentacoes erroneas
        for mov in movs_import:
            db.delete(mov)
        db.flush()

        # Ativar usa_patrimonio e recalcular
        mat.usa_patrimonio = True
        db.flush()
        sync_qty(mat, db)
        db.flush()

        print(f"  -> qty apos sync_qty: {mat.quantidade}")

    db.commit()
    print("\nCorrecao concluida com sucesso.")

except Exception as exc:
    db.rollback()
    print(f"ERRO — rollback: {exc}")
    raise
finally:
    db.close()
