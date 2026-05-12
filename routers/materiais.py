# © Todos os direitos reservados – github.com/Wbad-02
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from database import get_db
from auth import requer_editor_ou_admin, requer_admin, get_usuario_atual, registrar_log
from email_service import disparar_notificacao
from utils import sync_qty
import models, schemas

router = APIRouter(prefix="/api/materiais", tags=["materiais"])


def _out(m: models.Material) -> schemas.MaterialOut:
    return schemas.MaterialOut.from_orm_with_alert(m)


@router.get("/", response_model=list[schemas.MaterialOut])
def listar_materiais(
    grupo_id:        int | None = Query(None),
    categoria_id:    int | None = Query(None),
    apenas_alertas:  bool       = Query(False),
    incluir_zerados: bool       = Query(False),
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    q = (
        db.query(models.Material)
        .options(
            joinedload(models.Material.grupo).joinedload(models.GrupoMaterial.categoria),
            joinedload(models.Material.grupo).joinedload(models.GrupoMaterial.materiais),
            joinedload(models.Material.unidades),
        )
        .filter(models.Material.ativo == True)
    )

    if grupo_id:
        q = q.filter(models.Material.grupo_id == grupo_id)

    if categoria_id:
        q = q.join(models.GrupoMaterial).filter(
            models.GrupoMaterial.categoria_id == categoria_id
        )

    materiais = q.order_by(models.Material.nome).all()

    saida = [_out(m) for m in materiais]

    if not incluir_zerados:
        saida = [o for o in saida if o.quantidade > 0]

    if apenas_alertas:
        saida = [o for o in saida if o.alerta_minimo]

    return saida


@router.get("/alertas/count")
def contar_alertas(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    total = db.query(models.Material).filter(models.Material.ativo == True).all()
    return {"total_alertas": sum(1 for m in total if m.alerta_minimo)}


@router.get("/{mat_id}", response_model=schemas.MaterialOut)
def obter_material(
    mat_id: int,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(get_usuario_atual),
):
    mat = db.query(models.Material).filter(
        models.Material.id == mat_id,
        models.Material.ativo == True,
    ).first()
    if not mat:
        raise HTTPException(404, "Material não encontrado")
    return _out(mat)


@router.post("/", response_model=schemas.MaterialOut, status_code=201)
def criar_material(
    payload: schemas.MaterialCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    grupo = db.query(models.GrupoMaterial).filter(
        models.GrupoMaterial.id == payload.grupo_id
    ).first()
    if not grupo:
        raise HTTPException(404, "Grupo não encontrado")

    mat = models.Material(**{k: v for k, v in payload.model_dump().items()
                             if k not in ("codigo_patrimonio",)})
    mat.usa_patrimonio = True
    db.add(mat)
    db.flush()

    if payload.usa_patrimonio:
        if payload.codigo_patrimonio:
            if db.query(models.UnidadePatrimonio).filter(
                models.UnidadePatrimonio.material_id == mat.id,
                models.UnidadePatrimonio.codigo == payload.codigo_patrimonio,
            ).first():
                raise HTTPException(409, f"Código '{payload.codigo_patrimonio}' já cadastrado neste material")
            db.add(models.UnidadePatrimonio(
                material_id=mat.id,
                codigo=payload.codigo_patrimonio,
                status=models.StatusUnidade.ativo,
                origem="manual",
                valor_unitario=payload.valor_unitario,
                tag="novo",
            ))
        elif payload.quantidade >= 1:
            import math
            for _ in range(max(1, math.floor(payload.quantidade))):
                db.add(models.UnidadePatrimonio(
                    material_id=mat.id,
                    status=models.StatusUnidade.ativo,
                    origem="manual",
                    valor_unitario=payload.valor_unitario,
                    tag="novo",
                ))

    db.flush()
    sync_qty(mat, db)
    db.commit()
    db.refresh(mat)
    registrar_log(db, atual.id, "criar", "material", mat.id, payload.nome)
    return _out(mat)


@router.put("/{mat_id}", response_model=schemas.MaterialOut)
def atualizar_material(
    mat_id: int,
    payload: schemas.MaterialUpdate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    mat = db.query(models.Material).filter(
        models.Material.id == mat_id,
        models.Material.ativo == True,
    ).first()
    if not mat:
        raise HTTPException(404, "Material não encontrado")

    if payload.grupo_id:
        g = db.query(models.GrupoMaterial).filter(
            models.GrupoMaterial.id == payload.grupo_id
        ).first()
        if not g:
            raise HTTPException(404, "Grupo não encontrado")

    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(mat, campo, valor)

    db.commit()
    db.refresh(mat)
    registrar_log(db, atual.id, "editar", "material", mat_id)
    return _out(mat)


@router.delete("/{mat_id}", status_code=204)
def remover_material(
    mat_id: int,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    mat = db.query(models.Material).filter(
        models.Material.id == mat_id,
        models.Material.ativo == True,
    ).first()
    if not mat:
        raise HTTPException(404, "Material não encontrado")

    mat.ativo = False
    db.commit()
    registrar_log(db, atual.id, "remover", "material", mat_id, mat.nome)


@router.post("/{mat_id}/entrada", response_model=schemas.MaterialOut)
def entrada_material(
    mat_id: int,
    payload: schemas.EntradaMaterialCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_editor_ou_admin),
):
    """Registra entrada de estoque para um material existente."""
    mat = db.query(models.Material).filter(
        models.Material.id == mat_id,
        models.Material.ativo == True,
    ).first()
    if not mat:
        raise HTTPException(404, "Material não encontrado")

    if payload.valor_unitario is not None:
        mat.valor_unitario = payload.valor_unitario
    if payload.usa_patrimonio is not None:
        mat.usa_patrimonio = payload.usa_patrimonio

    if mat.usa_patrimonio and payload.codigo_patrimonio:
        dup = db.query(models.UnidadePatrimonio).filter(
            models.UnidadePatrimonio.material_id == mat_id,
            models.UnidadePatrimonio.codigo == payload.codigo_patrimonio,
        ).first()
        if dup:
            raise HTTPException(409, f"Código '{payload.codigo_patrimonio}' já cadastrado neste material")
        db.add(models.UnidadePatrimonio(
            material_id=mat_id,
            codigo=payload.codigo_patrimonio,
            origem="manual",
            status=models.StatusUnidade.ativo,
            valor_unitario=payload.valor_unitario,
            tag="novo",
        ))
    elif mat.usa_patrimonio:
        import math
        for _ in range(max(1, math.floor(payload.quantidade))):
            db.add(models.UnidadePatrimonio(
                material_id=mat_id,
                origem="manual",
                status=models.StatusUnidade.ativo,
                valor_unitario=payload.valor_unitario,
                tag="novo",
            ))
    else:
        mat.quantidade += payload.quantidade

    mov = models.Movimentacao(
        material_id=mat_id,
        usuario_id=atual.id,
        tipo="entrada",
        quantidade=1 if (mat.usa_patrimonio and payload.codigo_patrimonio) else payload.quantidade,
        valor_unitario=payload.valor_unitario,
        observacao=payload.observacao,
        tag="novo",
    )
    db.add(mov)
    db.flush()
    if mat.usa_patrimonio:
        sync_qty(mat, db)
    db.commit()
    db.refresh(mat)
    registrar_log(db, atual.id, "entrada", "material", mat_id,
                  f"+{payload.quantidade} {mat.unidade}")

    from datetime import datetime
    disparar_notificacao(db, "entrada", {
        "material":   mat.nome,
        "quantidade": str(mov.quantidade),
        "unidade":    mat.unidade,
        "usuario":    atual.nome,
        "data":       datetime.now().strftime("%d/%m/%Y %H:%M"),
    })
    return _out(mat)
