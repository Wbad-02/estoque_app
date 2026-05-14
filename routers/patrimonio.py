# © Todos os direitos reservados – github.com/Wbad-02
"""
Router de patrimônio — gerencia unidades individuais de materiais.
Cada unidade rastreia: origem (manual/xml), código de patrimônio,
data de cadastro, data de retirada e histórico completo.
"""
from models import agora
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_editor_ou_admin, get_usuario_atual, registrar_log
from utils import sync_qty
import models, schemas

router = APIRouter(prefix="/api/patrimonio", tags=["patrimonio"])


def _enriquecer_unidade(u: models.UnidadePatrimonio, db: Session) -> schemas.UnidadeOut:
    """Serializa unidade com campos extras: nome_material, retirado_por, motivo_saida, ativo_nome."""
    out = schemas.UnidadeOut.model_validate(u)
    out.nome_material = u.material.nome if u.material else ""

    if u.movimentacao_saida_id:
        mov = db.query(models.Movimentacao).filter(
            models.Movimentacao.id == u.movimentacao_saida_id
        ).first()
        if mov:
            out.retirado_por = mov.usuario.nome if mov.usuario else "Sistema"
            out.motivo_saida = mov.motivo if mov.motivo else ""

    if u.tag == "atribuido":
        item = db.query(models.AtivoItem).filter(
            models.AtivoItem.unidade_id == u.id,
            models.AtivoItem.devolvido_em == None,
        ).first()
        if item and item.ativo_obj:
            out.ativo_nome = item.ativo_obj.nome
            if item.ativo_obj.grupo and item.ativo_obj.grupo.categoria:
                out.ativo_categoria = item.ativo_obj.grupo.categoria.nome

    return out


# ── Listar unidades de um material ───────────────────────────
@router.get("/{material_id}/unidades", response_model=list[schemas.UnidadeOut])
def listar_unidades(
    material_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(404, "Material não encontrado")
    return [_enriquecer_unidade(u, db) for u in mat.unidades]


# ── Detalhes de uma unidade específica ───────────────────────
@router.get("/{material_id}/unidades/{unidade_id}", response_model=schemas.UnidadeOut)
def detalhe_unidade(
    material_id: int,
    unidade_id:  int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    u = db.query(models.UnidadePatrimonio).filter(
        models.UnidadePatrimonio.id == unidade_id,
        models.UnidadePatrimonio.material_id == material_id,
    ).first()
    if not u:
        raise HTTPException(404, "Unidade não encontrada")
    return _enriquecer_unidade(u, db)


# ── Editar código de patrimônio de uma unidade ────────────────
@router.patch("/{material_id}/unidades/{unidade_id}/codigo", response_model=schemas.UnidadeOut)
def editar_codigo_unidade(
    material_id: int,
    unidade_id:  int,
    payload:     schemas.EditarCodigoUnidade,
    db:          Session = Depends(get_db),
    atual:       models.Usuario = Depends(requer_editor_ou_admin),
):
    u = db.query(models.UnidadePatrimonio).filter(
        models.UnidadePatrimonio.id == unidade_id,
        models.UnidadePatrimonio.material_id == material_id,
    ).first()
    if not u:
        raise HTTPException(404, "Unidade não encontrada")

    # Checar duplicidade dentro do mesmo material
    dup = db.query(models.UnidadePatrimonio).filter(
        models.UnidadePatrimonio.material_id == material_id,
        models.UnidadePatrimonio.codigo == payload.codigo,
        models.UnidadePatrimonio.id != unidade_id,
    ).first()
    if dup:
        raise HTTPException(409, f"Código '{payload.codigo}' já está em uso neste material")

    u.codigo = payload.codigo
    db.commit(); db.refresh(u)
    registrar_log(db, atual.id, "editar_codigo", "unidade", unidade_id,
                  f"material_id={material_id} codigo={payload.codigo}")
    return _enriquecer_unidade(u, db)


# ── Timeline completa: entradas + saídas de um material ──────
@router.get("/{material_id}/timeline")
def timeline_material(
    material_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    mat = db.query(models.Material).filter(models.Material.id == material_id).first()
    if not mat:
        raise HTTPException(404, "Material não encontrado")

    eventos = []

    if mat.usa_patrimonio:
        for u in mat.unidades:
            eventos.append({
                "id":        u.id,
                "tipo":      "entrada",
                "subtipo":   "patrimonio",
                "data":      u.criado_em.isoformat(),
                "codigo":    u.codigo or "—",
                "origem":    u.origem or "manual",
                "nf_numero": u.nf_numero,
                "observacao": u.observacao or "",
                "status":    u.status.value,
            })
            if u.status == models.StatusUnidade.retirado and u.retirado_em:
                mov = None
                if u.movimentacao_saida_id:
                    mov = db.query(models.Movimentacao).filter(
                        models.Movimentacao.id == u.movimentacao_saida_id
                    ).first()
                eventos.append({
                    "id":        u.id,
                    "tipo":      "saida",
                    "subtipo":   "patrimonio",
                    "data":      u.retirado_em.isoformat(),
                    "codigo":    u.codigo or "—",
                    "motivo":    mov.motivo if mov and mov.motivo else "—",
                    "observacao": mov.observacao if mov else "",
                    "usuario":   mov.usuario.nome if mov and mov.usuario else "Sistema",
                })
    else:
        for mov in sorted(mat.movimentacoes, key=lambda x: x.criado_em):
            eventos.append({
                "id":            mov.id,
                "tipo":          mov.tipo,
                "subtipo":       "movimentacao",
                "data":          mov.criado_em.isoformat(),
                "quantidade":    mov.quantidade,
                "valor_unitario": mov.valor_unitario,
                "motivo":        mov.motivo if mov.motivo else None,
                "observacao":    mov.observacao or "",
                "usuario":       mov.usuario.nome if mov.usuario else "Sistema",
                "tag":           mov.tag,
            })

    eventos.sort(key=lambda e: e["data"])

    return {
        "material": {
            "id":             mat.id,
            "nome":           mat.nome,
            "grupo":          mat.grupo.nome if mat.grupo else "",
            "categoria":      mat.grupo.categoria.nome if mat.grupo and mat.grupo.categoria else "",
            "usa_patrimonio": mat.usa_patrimonio,
            "quantidade":     mat.quantidade,
            "unidade":        mat.unidade,
        },
        "eventos":        eventos,
        "total_entradas": sum(1 for e in eventos if e["tipo"] == "entrada"),
        "total_saidas":   sum(1 for e in eventos if e["tipo"] == "saida"),
    }


# ── Adicionar unidade(s) com patrimônio ──────────────────────
@router.post("/{material_id}/unidades", status_code=201)
def adicionar_unidades(
    material_id: int,
    payload:     list[schemas.UnidadeCreate],
    db:          Session = Depends(get_db),
    atual:       models.Usuario = Depends(requer_editor_ou_admin),
):
    mat = db.query(models.Material).filter(
        models.Material.id == material_id,
        models.Material.ativo == True,
    ).first()
    if not mat:
        raise HTTPException(404, "Material não encontrado")
    if not mat.usa_patrimonio:
        raise HTTPException(422, "Este material não usa controle por patrimônio")

    criadas = []
    for item in payload:
        if item.codigo:
            existe = db.query(models.UnidadePatrimonio).filter(
                models.UnidadePatrimonio.material_id == material_id,
                models.UnidadePatrimonio.codigo == item.codigo,
            ).first()
            if existe:
                raise HTTPException(409, f"Código '{item.codigo}' já cadastrado neste material")

        unidade = models.UnidadePatrimonio(
            material_id=material_id,
            codigo=item.codigo,
            observacao=item.observacao,
            status=models.StatusUnidade.ativo,
            origem=item.origem,
            nf_numero=item.nf_numero,
            tag=item.tag,
        )
        db.add(unidade); db.flush()

        mov = models.Movimentacao(
            material_id=material_id,
            usuario_id=atual.id,
            tipo="entrada",
            quantidade=1,
            unidade_id=unidade.id,
            observacao=f"NF-e {item.nf_numero}" if item.nf_numero else "Cadastro manual",
        )
        db.add(mov)
        criadas.append(unidade.id)

    db.flush()
    sync_qty(mat, db)
    db.commit()

    registrar_log(db, atual.id, "adicionar_unidades", "material", material_id,
                  f"{len(payload)} unidade(s) | códigos: {[p.codigo for p in payload]}")
    return {"criadas": len(criadas), "ids": criadas}


# ── Retirar unidade específica por patrimônio ─────────────────
@router.post("/{material_id}/retirar-unidade", status_code=201,
             response_model=schemas.MovimentacaoOut)
def retirar_unidade_patrimonio(
    material_id: int,
    payload:     schemas.RetiradaPatrimonioCreate,
    db:          Session = Depends(get_db),
    atual:       models.Usuario = Depends(requer_editor_ou_admin),
):
    mat = db.query(models.Material).filter(
        models.Material.id == material_id,
        models.Material.ativo == True,
    ).first()
    if not mat:
        raise HTTPException(404, "Material não encontrado")

    unidade = db.query(models.UnidadePatrimonio).filter(
        models.UnidadePatrimonio.id == payload.unidade_id,
        models.UnidadePatrimonio.material_id == material_id,
    ).first()
    if not unidade:
        raise HTTPException(404, "Unidade não encontrada")
    if unidade.status == models.StatusUnidade.retirado:
        raise HTTPException(422, "Esta unidade já foi retirada do estoque")

    mov = models.Movimentacao(
        material_id=material_id,
        usuario_id=atual.id,
        unidade_id=unidade.id,
        tipo="saida",
        quantidade=1,
        motivo=payload.motivo,
        observacao=payload.observacao,
    )
    db.add(mov); db.flush()

    unidade.status = models.StatusUnidade.retirado
    unidade.retirado_em = agora()
    unidade.movimentacao_saida_id = mov.id
    db.flush()
    sync_qty(mat, db)
    db.commit(); db.refresh(mov)

    registrar_log(db, atual.id, "retirar_unidade", "material", material_id,
                  f"unidade_id={unidade.id} código={unidade.codigo} motivo={payload.motivo}")

    out = schemas.MovimentacaoOut.model_validate(mov)
    out.nome_material  = mat.nome
    out.nome_usuario   = atual.nome
    out.grupo_nome     = mat.grupo.nome if mat.grupo else ""
    out.categoria_nome = mat.grupo.categoria.nome if mat.grupo and mat.grupo.categoria else ""
    out.unidade_codigo = unidade.codigo
    return out
