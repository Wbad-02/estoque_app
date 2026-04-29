# © Todos os direitos reservados – github.com/Wbad-02
"""Utilitários compartilhados entre routers."""
from sqlalchemy.orm import Session
import models


def sync_qty(mat: models.Material, db: Session) -> None:
    """
    Recalcula mat.quantidade a partir das unidades físicas reais.
    Deve ser chamado após qualquer operação que altere a disponibilidade
    de UnidadePatrimonio (criar, retirar, atribuir, devolver).
    """
    disponiveis = db.query(models.UnidadePatrimonio).filter(
        models.UnidadePatrimonio.material_id == mat.id,
        models.UnidadePatrimonio.status == models.StatusUnidade.ativo,
        models.UnidadePatrimonio.tag != "atribuido",
    ).count()
    mat.quantidade = float(disponiveis)
