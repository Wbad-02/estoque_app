# © Todos os direitos reservados – github.com/Wbad-02
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
import models, schemas
from auth import get_usuario_atual, requer_editor_ou_admin, requer_admin, registrar_log
from database import get_db
from utils import sync_qty
from models import agora
import email_service as _es
from email_service import _html_email, _linha_info, _badge_status

router = APIRouter(prefix="/api/solicitacoes", tags=["solicitacoes"])


def _build_out(s: models.SolicitacaoEstoque) -> schemas.SolicitacaoOut:
    return schemas.SolicitacaoOut(
        id=s.id,
        material_id=s.material_id,
        ativo_id=s.ativo_id,
        quantidade=s.quantidade,
        motivo=s.motivo,
        status=s.status.value if s.status else "aguardando",
        criado_em=s.criado_em,
        atualizado_em=s.atualizado_em,
        observacao=s.observacao,
        criador_nome=s.criador.nome if s.criador else "",
        decididor_nome=s.decididor.nome if s.decididor else "",
        material_nome=s.material.nome if s.material else "",
        ativo_nome=s.ativo.nome if s.ativo else "",
    )


def _load(sol_id: int, db: Session) -> models.SolicitacaoEstoque:
    s = (
        db.query(models.SolicitacaoEstoque)
        .options(
            joinedload(models.SolicitacaoEstoque.material),
            joinedload(models.SolicitacaoEstoque.ativo),
            joinedload(models.SolicitacaoEstoque.criador),
            joinedload(models.SolicitacaoEstoque.decididor),
        )
        .filter(models.SolicitacaoEstoque.id == sol_id)
        .first()
    )
    if not s:
        raise HTTPException(404, "Solicitacao nao encontrada")
    return s


@router.post("/", response_model=schemas.SolicitacaoOut, status_code=201)
def criar_solicitacao(
    payload: schemas.SolicitacaoCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    mat = (
        db.query(models.Material)
        .filter(models.Material.id == payload.material_id, models.Material.ativo == True)
        .first()
    )
    if not mat:
        raise HTTPException(404, "Material nao encontrado")
    if mat.quantidade < payload.quantidade:
        raise HTTPException(
            422,
            f"Estoque insuficiente. Disponivel: {mat.quantidade} {mat.unidade}",
        )

    if payload.ativo_id is not None:
        ativo = db.query(models.Ativo).filter(
            models.Ativo.id == payload.ativo_id, models.Ativo.ativo == True
        ).first()
        if not ativo:
            raise HTTPException(404, "Ativo nao encontrado")

    sol = models.SolicitacaoEstoque(
        material_id=payload.material_id,
        ativo_id=payload.ativo_id,
        quantidade=payload.quantidade,
        motivo=payload.motivo.strip(),
        status=models.StatusSolicitacao.aguardando,
        criado_por=atual.id,
    )
    db.add(sol)
    db.commit()
    db.refresh(sol)
    registrar_log(db, atual.id, "criar", "solicitacao", sol.id, mat.nome)

    # ── Notifica admins sobre nova solicitação ────────────────────────────────
    try:
        sol_loaded = _load(sol.id, db)
        admins = [
            u.email
            for u in db.query(models.Usuario).filter(
                models.Usuario.grupo.in_([
                    models.GrupoPermissao.admin,
                    models.GrupoPermissao.mestre,
                ]),
                models.Usuario.ativo == True,
            ).all()
            if u.email
        ]

        data_fmt  = agora().strftime("%d/%m/%Y %H:%M")
        ativo_nome = sol_loaded.ativo.nome if sol_loaded.ativo else "—"
        link       = os.environ.get("APP_URL", "http://localhost:8000")

        corpo_linhas = f"""
<p style="margin:0 0 16px;font-size:15px;color:#444">
  Uma nova <b>solicitação de material</b> foi criada e aguarda sua aprovação.
</p>
<table style="width:100%;border-collapse:collapse">
  {_linha_info("Material", mat.nome, destaque=True)}
  {_linha_info("Quantidade", f"{sol.quantidade} {mat.unidade}")}
  {_linha_info("Solicitante", sol_loaded.criador.nome if sol_loaded.criador else atual.nome)}
  {_linha_info("Motivo", sol.motivo)}
  {_linha_info("Ativo destino", ativo_nome)}
  {_linha_info("Data", data_fmt)}
</table>
<div style="margin-top:24px;padding-top:16px;border-top:1px solid #eee">
  <a href="{link}/#requerimentos" style="display:inline-block;padding:10px 24px;background:#1B3A2D;color:#fff;text-decoration:none;border-radius:6px;font-size:14px;font-weight:600">
    Ver solicitação
  </a>
</div>
"""
        corpo_html = _html_email("Nova solicitação de estoque", corpo_linhas)

        variaveis = {
            "material":    mat.nome,
            "quantidade":  f"{sol.quantidade} {mat.unidade}",
            "criador":     atual.nome,
            "motivo":      sol.motivo,
            "ativo":       ativo_nome,
            "data":        data_fmt,
            "link":        link,
        }
        _es.disparar_notificacao(
            db, "solicitacao", variaveis, extras=admins, corpo_html=corpo_html
        )
    except Exception as exc:
        print(f"[email] Erro ao notificar admins sobre solicitacao #{sol.id}: {exc}")

    return _build_out(_load(sol.id, db))


@router.get("/", response_model=list[schemas.SolicitacaoOut])
def listar_solicitacoes(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_editor_ou_admin),
):
    sols = (
        db.query(models.SolicitacaoEstoque)
        .options(
            joinedload(models.SolicitacaoEstoque.material),
            joinedload(models.SolicitacaoEstoque.ativo),
            joinedload(models.SolicitacaoEstoque.criador),
            joinedload(models.SolicitacaoEstoque.decididor),
        )
        .order_by(models.SolicitacaoEstoque.criado_em.desc())
        .all()
    )
    return [_build_out(s) for s in sols]


def _notificar_decisao(
    db: Session,
    sol: models.SolicitacaoEstoque,
    mat: models.Material,
    atual: models.Usuario,
    decisao: str,
    observacao: str,
):
    """Notifica o criador da solicitação sobre aprovação ou rejeição."""
    if not (sol.criador and sol.criador.email):
        return

    status_label = "aprovada" if decisao == "aprovado" else "rejeitada"
    titulo_email = f"Solicitação {status_label}"

    corpo_linhas = f"""
<p style="margin:0 0 16px;font-size:15px;color:#444">
  Sua solicitação de material foi <b>{status_label}</b>.
</p>
<table style="width:100%;border-collapse:collapse">
  {_linha_info("Material", mat.nome, destaque=True)}
  {_linha_info("Quantidade", f"{sol.quantidade} {mat.unidade}")}
  {_linha_info("Status", _badge_status(status_label))}
  {_linha_info("Decidido por", atual.nome)}
  {_linha_info("Observação", observacao or "—")}
</table>
"""
    corpo_html = _html_email(titulo_email, corpo_linhas)

    variaveis = {
        "material":   mat.nome,
        "quantidade": f"{sol.quantidade} {mat.unidade}",
        "status":     status_label,
        "decididor":  atual.nome,
        "observacao": observacao or "—",
    }
    _es.disparar_notificacao(
        db,
        "solicitacao_decisao",
        variaveis,
        extras=[sol.criador.email],
        corpo_html=corpo_html,
    )


@router.post("/{sol_id}/aprovar", response_model=schemas.SolicitacaoOut)
def aprovar_solicitacao(
    sol_id: int,
    body: schemas.AprovarSolicitacaoBody = schemas.AprovarSolicitacaoBody(),
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    sol = _load(sol_id, db)
    if sol.status != models.StatusSolicitacao.aguardando:
        raise HTTPException(409, f"Solicitacao ja esta '{sol.status.value}'")

    mat = db.query(models.Material).filter(models.Material.id == sol.material_id).first()
    if not mat:
        raise HTTPException(404, "Material nao encontrado")

    if mat.usa_patrimonio:
        qtd_int = max(1, int(sol.quantidade))
        unidades_disp = (
            db.query(models.UnidadePatrimonio)
            .filter(
                models.UnidadePatrimonio.material_id == mat.id,
                models.UnidadePatrimonio.status == models.StatusUnidade.ativo,
                # tag IS NULL ou tag != 'atribuido' — espelha exatamente sync_qty
                or_(
                    models.UnidadePatrimonio.tag == None,
                    models.UnidadePatrimonio.tag != "atribuido",
                ),
            )
            .limit(qtd_int)
            .all()
        )
        if len(unidades_disp) < qtd_int:
            raise HTTPException(
                422,
                f"Estoque insuficiente. Disponiveis: {len(unidades_disp)} unidade(s)",
            )
        for u in unidades_disp:
            if sol.ativo_id:
                u.tag = "atribuido"
                db.add(models.AtivoItem(
                    ativo_id=sol.ativo_id,
                    material_id=sol.material_id,
                    unidade_id=u.id,
                    quantidade=1,
                    observacao=body.observacao,
                ))
            else:
                # Cria movimentacao individual por unidade para rastrear na timeline
                # e linka movimentacao_saida_id, seguindo o padrao de patrimonio.py
                mov_unit = models.Movimentacao(
                    material_id=sol.material_id,
                    usuario_id=atual.id,
                    unidade_id=u.id,
                    tipo="saida",
                    quantidade=1,
                    motivo=f"Solicitacao #{sol_id}: {sol.motivo}",
                    observacao=body.observacao,
                )
                db.add(mov_unit)
                db.flush()
                u.status = models.StatusUnidade.retirado
                u.retirado_em = agora()
                u.movimentacao_saida_id = mov_unit.id
        db.flush()
        sync_qty(mat, db)
    else:
        if mat.quantidade < sol.quantidade:
            raise HTTPException(422, "Estoque insuficiente para aprovar")
        mat.quantidade -= sol.quantidade
        if sol.ativo_id:
            db.add(models.AtivoItem(
                ativo_id=sol.ativo_id,
                material_id=sol.material_id,
                unidade_id=None,
                quantidade=sol.quantidade,
                observacao=body.observacao,
            ))

    # Para patrimônio sem ativo_id as movimentacoes já foram criadas individualmente acima.
    # Para os demais casos (patrimônio com ativo_id, ou material sem patrimônio),
    # cria uma única movimentacao consolidada de saída.
    if not (mat.usa_patrimonio and not sol.ativo_id):
        db.add(models.Movimentacao(
            material_id=sol.material_id,
            usuario_id=atual.id,
            tipo="saida",
            quantidade=sol.quantidade,
            motivo=f"Solicitacao #{sol_id}: {sol.motivo}",
            observacao=body.observacao,
        ))

    sol.status = models.StatusSolicitacao.aprovado
    sol.decidido_por = atual.id
    sol.observacao = body.observacao
    sol.atualizado_em = agora()
    db.commit()
    registrar_log(db, atual.id, "aprovar", "solicitacao", sol_id,
                  f"{mat.nome} x{sol.quantidade}")

    # ── Notifica criador sobre a aprovação ────────────────────────────────────
    try:
        sol_reloaded = _load(sol_id, db)
        _notificar_decisao(db, sol_reloaded, mat, atual, "aprovado", body.observacao or "")
    except Exception as exc:
        print(f"[email] Erro ao notificar criador sobre aprovacao #{sol_id}: {exc}")

    return _build_out(_load(sol_id, db))


@router.post("/{sol_id}/rejeitar", response_model=schemas.SolicitacaoOut)
def rejeitar_solicitacao(
    sol_id: int,
    body: schemas.RejeitarSolicitacaoBody,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    sol = _load(sol_id, db)
    if sol.status != models.StatusSolicitacao.aguardando:
        raise HTTPException(409, f"Solicitacao ja esta '{sol.status.value}'")

    mat = db.query(models.Material).filter(models.Material.id == sol.material_id).first()
    if not mat:
        raise HTTPException(404, "Material nao encontrado")

    sol.status = models.StatusSolicitacao.rejeitado
    sol.decidido_por = atual.id
    sol.observacao = body.observacao
    sol.atualizado_em = agora()
    db.commit()
    registrar_log(db, atual.id, "rejeitar", "solicitacao", sol_id, body.observacao)

    # ── Notifica criador sobre a rejeição ─────────────────────────────────────
    try:
        sol_reloaded = _load(sol_id, db)
        _notificar_decisao(db, sol_reloaded, mat, atual, "rejeitado", body.observacao or "")
    except Exception as exc:
        print(f"[email] Erro ao notificar criador sobre rejeicao #{sol_id}: {exc}")

    return _build_out(_load(sol_id, db))
