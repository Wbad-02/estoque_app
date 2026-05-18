# © Todos os direitos reservados – github.com/Wbad-02
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from auth import requer_admin, registrar_log
import email_service
import models, schemas

router = APIRouter(prefix="/api/notificacoes", tags=["notificacoes"])

_TIPOS_VALIDOS = ("retirada", "entrada", "alerta", "solicitacao", "solicitacao_decisao")

_TEMPLATES_PADRAO = {
    "retirada": {
        "assunto": "Retirada de material registrada — {material}",
        "corpo": (
            "Uma retirada foi registrada no sistema de estoque.\n\n"
            "Material: {material}\n"
            "Quantidade: {quantidade} {unidade}\n"
            "Motivo: {motivo}\n"
            "Usuário: {usuario}\n"
            "Data: {data}\n\n"
            "Observação: {observacao}"
        ),
    },
    "entrada": {
        "assunto": "Entrada de material registrada — {material}",
        "corpo": (
            "Uma entrada foi registrada no sistema de estoque.\n\n"
            "Material: {material}\n"
            "Quantidade adicionada: {quantidade} {unidade}\n"
            "Usuário: {usuario}\n"
            "Data: {data}"
        ),
    },
    "alerta": {
        "assunto": "Alerta de estoque mínimo — {material}",
        "corpo": (
            "O material abaixo atingiu ou está abaixo do estoque mínimo.\n\n"
            "Material: {material}\n"
            "Quantidade atual: {quantidade} {unidade}\n"
            "Quantidade mínima: {minimo} {unidade}\n"
            "Grupo: {grupo}\n"
            "Data do alerta: {data}"
        ),
    },
    "solicitacao": {
        "assunto": "Nova solicitação de estoque: {material}",
        "corpo": (
            "Uma nova solicitação de material foi aberta e aguarda aprovação.\n\n"
            "Material:      {material}\n"
            "Quantidade:    {quantidade}\n"
            "Solicitante:   {criador}\n"
            "Motivo:        {motivo}\n"
            "Ativo destino: {ativo}\n"
            "Data:          {data}\n\n"
            "Acesse para aprovar ou rejeitar: {link}"
        ),
    },
    "solicitacao_decisao": {
        "assunto": "Solicitação de '{material}' foi {status}",
        "corpo": (
            "Sua solicitação de material teve uma decisão registrada.\n\n"
            "Material:     {material}\n"
            "Quantidade:   {quantidade}\n"
            "Status:       {status}\n"
            "Decidido por: {decididor}\n"
            "Observação:   {observacao}"
        ),
    },
}


# ── Emails ────────────────────────────────────────────

@router.get("/emails", response_model=list[schemas.NotificacaoEmailOut])
def listar_emails(
    tipo: str | None = None,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    q = db.query(models.NotificacaoEmail).filter(models.NotificacaoEmail.ativo == True)
    if tipo:
        q = q.filter(models.NotificacaoEmail.tipo == tipo)
    return q.order_by(models.NotificacaoEmail.email).all()


@router.post("/emails", response_model=schemas.NotificacaoEmailOut, status_code=201)
def adicionar_email(
    payload: schemas.NotificacaoEmailCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    existente = db.query(models.NotificacaoEmail).filter(
        models.NotificacaoEmail.email == payload.email,
        models.NotificacaoEmail.tipo  == payload.tipo,
        models.NotificacaoEmail.ativo == True,
    ).first()
    if existente:
        raise HTTPException(409, "E-mail já cadastrado para este tipo de notificação")

    reg = models.NotificacaoEmail(
        email=payload.email,
        tipo=payload.tipo,
        intervalo_dias=payload.intervalo_dias,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    registrar_log(db, atual.id, "criar", "notificacao_email", reg.id, payload.email)
    return reg


@router.delete("/emails/{email_id}", status_code=204)
def remover_email(
    email_id: int,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    reg = db.query(models.NotificacaoEmail).filter(
        models.NotificacaoEmail.id == email_id
    ).first()
    if not reg:
        raise HTTPException(404, "E-mail não encontrado")
    reg.ativo = False
    db.commit()
    registrar_log(db, atual.id, "remover", "notificacao_email", email_id)


# ── Templates ─────────────────────────────────────────

@router.get("/templates", response_model=list[schemas.NotificacaoTemplateOut])
def listar_templates(
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    templates = db.query(models.NotificacaoTemplate).all()
    existentes = {t.tipo for t in templates}

    # Garante que todos os templates padrão existam
    for tipo, dados in _TEMPLATES_PADRAO.items():
        if tipo not in existentes:
            t = models.NotificacaoTemplate(tipo=tipo, **dados)
            db.add(t)
    db.commit()

    return db.query(models.NotificacaoTemplate).order_by(models.NotificacaoTemplate.tipo).all()


@router.get("/templates/{tipo}", response_model=schemas.NotificacaoTemplateOut)
def obter_template(
    tipo: str,
    db: Session = Depends(get_db),
    _: models.Usuario = Depends(requer_admin),
):
    if tipo not in _TIPOS_VALIDOS:
        raise HTTPException(400, f"Tipo inválido. Use: {', '.join(_TIPOS_VALIDOS)}")
    t = db.query(models.NotificacaoTemplate).filter(
        models.NotificacaoTemplate.tipo == tipo
    ).first()
    if not t:
        padrao = _TEMPLATES_PADRAO[tipo]
        t = models.NotificacaoTemplate(tipo=tipo, **padrao)
        db.add(t)
        db.commit()
        db.refresh(t)
    return t


@router.put("/templates/{tipo}", response_model=schemas.NotificacaoTemplateOut)
def atualizar_template(
    tipo: str,
    payload: schemas.NotificacaoTemplateCreate,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    if tipo not in _TIPOS_VALIDOS:
        raise HTTPException(400, f"Tipo inválido. Use: {', '.join(_TIPOS_VALIDOS)}")
    t = db.query(models.NotificacaoTemplate).filter(
        models.NotificacaoTemplate.tipo == tipo
    ).first()
    if not t:
        t = models.NotificacaoTemplate(tipo=tipo, assunto=payload.assunto, corpo=payload.corpo)
        db.add(t)
    else:
        t.assunto = payload.assunto
        t.corpo   = payload.corpo
    db.commit()
    db.refresh(t)
    registrar_log(db, atual.id, "editar", "notificacao_template", t.id, tipo)
    return t


# ── SMTP Config ────────────────────────────────────────

class _SmtpPayload(BaseModel):
    host:      str
    porta:     int  = 587
    usuario:   str  = ""
    senha:     str  = ""
    remetente: str  = ""
    tls:       bool = True
    ssl:       bool = False


@router.get("/smtp")
def obter_smtp(_: models.Usuario = Depends(requer_admin)):
    cfg = email_service.ler_config()
    if cfg.get("senha"):
        cfg = {**cfg, "senha": "••••••••"}
    return cfg


@router.put("/smtp")
def salvar_smtp(
    payload: _SmtpPayload,
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    dados = payload.model_dump()
    # Preserva senha anterior se vier mascarada
    if dados.get("senha") == "••••••••":
        dados["senha"] = email_service.ler_config().get("senha", "")
    email_service.salvar_config(dados)
    registrar_log(db, atual.id, "editar", "smtp_config", None, payload.host)
    return {"ok": True}


@router.post("/smtp/testar")
def testar_smtp(atual: models.Usuario = Depends(requer_admin)):
    try:
        email_service._enviar(
            [atual.email],
            "Teste de e-mail — Controle de Estoque",
            (
                "Se você recebeu este e-mail, o SMTP está configurado corretamente.\n\n"
                f"Enviado para: {atual.email}"
            ),
        )
        return {"ok": True, "enviado_para": atual.email}
    except Exception as exc:
        raise HTTPException(500, f"Erro ao enviar: {exc}")


# ── Envio manual de alertas ───────────────────────────

@router.post("/alertas/enviar")
def enviar_alertas_manual(
    db: Session = Depends(get_db),
    atual: models.Usuario = Depends(requer_admin),
):
    """Dispara imediatamente os e-mails de alerta para todos os materiais abaixo do mínimo."""
    cfg = email_service.ler_config()
    if not cfg.get("host"):
        return {"ok": False, "alertas_enviados": 0,
                "mensagem": "SMTP não configurado — acesse Config. SMTP para configurar"}

    destinatarios_count = db.query(models.NotificacaoEmail).filter(
        models.NotificacaoEmail.tipo  == "alerta",
        models.NotificacaoEmail.ativo == True,
    ).count()
    if not destinatarios_count:
        return {"ok": False, "alertas_enviados": 0,
                "mensagem": "Nenhum e-mail cadastrado para alertas — adicione destinatários na aba Alertas"}

    mats_alerta = [
        m for m in db.query(models.Material).filter(models.Material.ativo == True).all()
        if m.alerta_minimo
    ]
    if not mats_alerta:
        return {"ok": True, "alertas_enviados": 0, "mensagem": "Nenhum material em situação de alerta"}

    email_service.disparar_alerta_consolidado(db, mats_alerta)
    enviados = len(mats_alerta)

    registrar_log(db, atual.id, "envio_manual", "alertas", None, f"{enviados} alerta(s)")
    return {"ok": True, "alertas_enviados": enviados,
            "mensagem": f"{enviados} alerta(s) em 1 e-mail para {destinatarios_count} destinatário(s)"}
