# © Todos os direitos reservados – github.com/Wbad-02
"""
Serviço de envio de e-mails via SMTP.
Configuração lida de smtp_config.json (criado pela interface admin).
Envios são disparados em thread daemon para não bloquear requisições.
"""
import json
import os
import smtplib
import threading
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

CONFIG_PATH = Path("smtp_config.json")


def _resolver_senha(senha: str) -> str:
    """Suporta valor env:NOME_VAR — lê da variável de ambiente em vez do arquivo."""
    if senha and senha.startswith("env:"):
        return os.environ.get(senha[4:], "")
    return senha


def ler_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg["senha"] = _resolver_senha(cfg.get("senha", ""))
            return cfg
        except Exception:
            return {}
    return {}


def salvar_config(dados: dict):
    CONFIG_PATH.write_text(
        json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _enviar(destinatarios: list[str], assunto: str, corpo: str):
    cfg = ler_config()
    if not cfg.get("host"):
        raise ValueError("SMTP não configurado — acesse Notificações > Config. SMTP")
    if not destinatarios:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"]    = cfg.get("remetente") or cfg.get("usuario", "")
    msg["To"]      = ", ".join(destinatarios)
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    porta   = int(cfg.get("porta", 587))
    host    = cfg["host"]
    use_ssl = bool(cfg.get("ssl", False))
    use_tls = bool(cfg.get("tls", True)) and not use_ssl

    if use_ssl:
        conn = smtplib.SMTP_SSL(host, porta, timeout=15)
    else:
        conn = smtplib.SMTP(host, porta, timeout=15)

    with conn as s:
        if use_tls:
            s.starttls()
        if cfg.get("usuario") and cfg.get("senha"):
            s.login(cfg["usuario"], cfg["senha"])
        s.sendmail(msg["From"], destinatarios, msg.as_string())


def _enviar_seguro(destinatarios: list[str], assunto: str, corpo: str):
    try:
        _enviar(destinatarios, assunto, corpo)
        print(f"[email] Enviado para {destinatarios}: {assunto}")
    except Exception as exc:
        print(f"[email] Erro ao enviar para {destinatarios}: {exc}")


def _preencher(template: str, variaveis: dict) -> str:
    return template.format_map(defaultdict(lambda: "—", variaveis))


def disparar_notificacao(db, tipo: str, variaveis: dict):
    """
    Busca destinatários e template no banco, preenche variáveis
    e dispara o envio em background (não bloqueia a requisição).
    """
    from models import NotificacaoEmail, NotificacaoTemplate

    emails = db.query(NotificacaoEmail).filter(
        NotificacaoEmail.tipo  == tipo,
        NotificacaoEmail.ativo == True,
    ).all()
    destinatarios = [e.email for e in emails]
    if not destinatarios:
        return

    template = db.query(NotificacaoTemplate).filter(
        NotificacaoTemplate.tipo == tipo
    ).first()
    if not template:
        return

    assunto = _preencher(template.assunto, variaveis)
    corpo   = _preencher(template.corpo,   variaveis)

    # Apenas strings passadas para a thread — seguro após fechar sessão
    threading.Thread(
        target=_enviar_seguro,
        args=(destinatarios, assunto, corpo),
        daemon=True,
    ).start()


def disparar_alerta_consolidado(db, mats_alerta: list):
    """
    Envia um único e-mail consolidado listando todos os materiais em alerta.
    Usado quando há múltiplos itens abaixo do mínimo para evitar spam.
    """
    from models import NotificacaoEmail

    emails = db.query(NotificacaoEmail).filter(
        NotificacaoEmail.tipo  == "alerta",
        NotificacaoEmail.ativo == True,
    ).all()
    destinatarios = [e.email for e in emails]
    if not destinatarios or not mats_alerta:
        return

    n = len(mats_alerta)
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    assunto = f"Alerta de estoque minimo — {n} material(is) abaixo do minimo"

    linhas = [
        f"{n} material(is) atingiram ou estao abaixo do estoque minimo.",
        f"Data do alerta: {agora}",
        "=" * 50,
    ]
    for mat in mats_alerta:
        grupo = mat.grupo.nome if mat.grupo else "—"
        linhas.append(
            f"\nMaterial: {mat.nome}\n"
            f"Quantidade atual: {mat.quantidade} {mat.unidade}\n"
            f"Quantidade minima: {mat.quantidade_minima} {mat.unidade}\n"
            f"Grupo: {grupo}"
        )
        linhas.append("-" * 40)

    corpo = "\n".join(linhas)

    threading.Thread(
        target=_enviar_seguro,
        args=(destinatarios, assunto, corpo),
        daemon=True,
    ).start()
