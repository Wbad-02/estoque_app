# © Todos os direitos reservados – github.com/Wbad-02
"""Utilitários compartilhados entre routers."""
import os
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
import models


def get_app_url() -> str:
    """URL pública do sistema, usada em links de e-mail.
    Lê APP_URL; se não definida, tenta o primeiro valor de CORS_ORIGINS."""
    url = os.environ.get("APP_URL", "").strip().rstrip("/")
    if not url:
        origens = os.environ.get("CORS_ORIGINS", "")
        url = origens.split(",")[0].strip().rstrip("/")
    return url or "http://localhost:8000"

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
