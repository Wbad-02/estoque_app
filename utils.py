# © Todos os direitos reservados – github.com/Wbad-02
"""Utilitários compartilhados entre routers."""
from sqlalchemy import or_
from sqlalchemy.orm import Session
import models


def sync_qty(mat: models.Material, db: Session) -> None:
    """
    Recalcula mat.quantidade a partir das unidades físicas reais.
    Deve ser chamado após qualquer operação que altere a disponibilidade
    de UnidadePatrimonio (criar, retirar, atribuir, devolver).
    """
    # tag IS NULL (novo/usado sem tag) também conta como disponível
    disponiveis = db.query(models.UnidadePatrimonio).filter(
        models.UnidadePatrimonio.material_id == mat.id,
        models.UnidadePatrimonio.status == models.StatusUnidade.ativo,
        or_(
            models.UnidadePatrimonio.tag == None,
            models.UnidadePatrimonio.tag != "atribuido",
        ),
    ).count()
    mat.quantidade = float(disponiveis)
