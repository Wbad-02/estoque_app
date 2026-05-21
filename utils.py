# © Todos os direitos reservados – github.com/Wbad-02
"""Utilitários compartilhados entre routers."""
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
import models

_TAGS_INDISPONIVEIS = ("atribuido", "solicitado")


def sync_qty(mat: models.Material, db: Session) -> None:
    """
    Recalcula mat.quantidade a partir das unidades físicas reais.
    Exclui unidades atribuídas a ativos ou reservadas por solicitação pendente.
    """
    disponiveis = db.query(models.UnidadePatrimonio).filter(
        models.UnidadePatrimonio.material_id == mat.id,
        models.UnidadePatrimonio.status == models.StatusUnidade.ativo,
        or_(
            models.UnidadePatrimonio.tag == None,
            and_(
                models.UnidadePatrimonio.tag != "atribuido",
                models.UnidadePatrimonio.tag != "solicitado",
            ),
        ),
    ).count()
    mat.quantidade = float(disponiveis)
