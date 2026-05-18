# © Todos os direitos reservados – github.com/Wbad-02
"""
Serviço de envio de e-mails via SMTP.
Configuração lida de smtp_config.json (criado pela interface admin).
Envios são disparados em thread daemon para não bloquear requisições.

Notificações do tipo "entrada" são agrupadas em uma janela de 30 minutos:
a primeira entrada inicia um timer; todas as entradas subsequentes dentro
da janela são acumuladas e enviadas juntas em um único e-mail ao final.
"""
import json
import os
import smtplib
import threading
from collections import defaultdict
from datetime import datetime, timezone, timedelta

_BR = timezone(timedelta(hours=-3))
def _agora_br(): return datetime.now(_BR).replace(tzinfo=None)
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Batch de notificações de entrada ──────────────────────────────────────────
_BATCH_WINDOW = 30 * 60          # 30 minutos em segundos

_batch_lock         = threading.Lock()
_batch_pending:     list[dict]  = []   # variáveis de cada entrada acumulada
_batch_destinatarios: list[str] = []   # resolvidos na 1ª entrada da janela
_batch_assunto_tpl: str         = ""   # assunto do template (sem substituição)
_batch_corpo_tpl:   str         = ""   # corpo do template (sem substituição)
_batch_timer:       threading.Timer | None = None

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


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _linha_info(rotulo: str, valor: str, destaque: bool = False) -> str:
    """Gera uma <tr> com rótulo e valor para tabela de detalhes."""
    if destaque:
        td_valor = (
            f'<td style="padding:6px 0;font-size:13px;color:#1B3A2D;'
            f'font-weight:600">{valor}</td>'
        )
    else:
        td_valor = (
            f'<td style="padding:6px 0;font-size:13px;color:#222">{valor}</td>'
        )
    return (
        f'<tr>'
        f'<td style="padding:6px 0;font-size:13px;color:#666;width:140px;'
        f'vertical-align:top">{rotulo}</td>'
        f'{td_valor}'
        f'</tr>'
    )


def _badge_status(status: str) -> str:
    """Retorna um span HTML com badge colorido por status."""
    cores = {
        "aguardando": ("#FFF3CD", "#856404"),
        "aprovado":   ("#D4EDDA", "#155724"),
        "aprovada":   ("#D4EDDA", "#155724"),
        "rejeitado":  ("#FDECEA", "#C0392B"),
        "rejeitada":  ("#FDECEA", "#C0392B"),
    }
    bg, fg = cores.get(status.lower(), ("#eee", "#333"))
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:12px;'
        f'font-size:12px;font-weight:600;background:{bg};color:{fg}">'
        f'{status.capitalize()}</span>'
    )


def _html_email(titulo: str, corpo_linhas: str) -> str:
    """
    Monta o HTML completo do e-mail com layout responsivo.

    titulo:       texto do cabeçalho principal.
    corpo_linhas: string HTML representando o corpo (parágrafos, tabelas, links).
    """
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:32px 0">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.10)">
        <tr><td style="background:#1B3A2D;padding:24px 32px">
          <p style="margin:0;color:#C9A84C;font-size:11px;font-weight:600;letter-spacing:2px;text-transform:uppercase">Sistema de Estoque</p>
          <h1 style="margin:6px 0 0;color:#ffffff;font-size:22px;font-weight:700">{titulo}</h1>
        </td></tr>
        <tr><td style="background:#ffffff;padding:28px 32px">
          {corpo_linhas}
        </td></tr>
        <tr><td style="background:#f8f8f8;padding:16px 32px;border-top:1px solid #e8e8e8">
          <p style="margin:0;font-size:11px;color:#999">Este e-mail foi gerado automaticamente pelo Sistema de Controle de Estoque.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ── Envio ─────────────────────────────────────────────────────────────────────

def _enviar(
    destinatarios: list[str],
    assunto: str,
    corpo_texto: str,
    corpo_html: str | None = None,
):
    cfg = ler_config()
    if not cfg.get("host"):
        raise ValueError("SMTP não configurado — acesse Notificações > Config. SMTP")
    if not destinatarios:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"]    = cfg.get("remetente") or cfg.get("usuario", "")
    msg["To"]      = ", ".join(destinatarios)
    msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))
    if corpo_html:
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))

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


def _enviar_seguro(
    destinatarios: list[str],
    assunto: str,
    corpo_texto: str,
    corpo_html: str | None = None,
):
    try:
        _enviar(destinatarios, assunto, corpo_texto, corpo_html)
        print(f"[email] Enviado para {destinatarios}: {assunto}")
    except Exception as exc:
        print(f"[email] Erro ao enviar para {destinatarios}: {exc}")


def _preencher(template: str, variaveis: dict) -> str:
    return template.format_map(defaultdict(lambda: "—", variaveis))


# ── Batch de entradas ─────────────────────────────────────────────────────────

def _flush_batch():
    """Disparado pelo timer: envia um único e-mail com todas as entradas acumuladas."""
    global _batch_pending, _batch_destinatarios, _batch_assunto_tpl, _batch_corpo_tpl, _batch_timer

    with _batch_lock:
        pendentes      = _batch_pending[:]
        destinatarios  = _batch_destinatarios[:]
        assunto_tpl    = _batch_assunto_tpl
        corpo_tpl      = _batch_corpo_tpl
        _batch_pending       = []
        _batch_destinatarios = []
        _batch_assunto_tpl   = ""
        _batch_corpo_tpl     = ""
        _batch_timer         = None

    if not pendentes or not destinatarios:
        return

    n     = len(pendentes)
    agora = _agora_br().strftime("%d/%m/%Y %H:%M")

    if n == 1:
        assunto    = _preencher(assunto_tpl, pendentes[0])
        corpo_txt  = _preencher(corpo_tpl,   pendentes[0])
        corpo_html = None
    else:
        assunto = f"Resumo de entradas de estoque — {n} movimentações"

        # Plain-text
        linhas_txt = [
            f"{n} entradas de estoque foram registradas.",
            f"Gerado em: {agora}",
            "=" * 52,
        ]
        for i, v in enumerate(pendentes, 1):
            linhas_txt.append(
                f"\n{i}. Material:    {v.get('material', '—')}\n"
                f"   Quantidade:  {v.get('quantidade', '—')} {v.get('unidade', '')}\n"
                f"   Responsável: {v.get('usuario', '—')}\n"
                f"   Data/hora:   {v.get('data', '—')}"
            )
            linhas_txt.append("-" * 40)
        corpo_txt = "\n".join(linhas_txt)

        # HTML
        linhas_html = []
        linhas_html.append(
            f'<p style="margin:0 0 16px;font-size:15px;color:#444">'
            f'{n} entradas de estoque foram registradas. Gerado em: <b>{agora}</b></p>'
        )
        linhas_html.append('<table style="width:100%;border-collapse:collapse">')
        for v in pendentes:
            linhas_html.append(_linha_info("Material", v.get("material", "—"), destaque=True))
            linhas_html.append(_linha_info("Quantidade", f"{v.get('quantidade', '—')} {v.get('unidade', '')}"))
            linhas_html.append(_linha_info("Responsável", v.get("usuario", "—")))
            linhas_html.append(_linha_info("Data/hora", v.get("data", "—")))
            linhas_html.append(
                '<tr><td colspan="2" style="padding:4px 0;border-bottom:1px solid #eee"></td></tr>'
            )
        linhas_html.append("</table>")
        corpo_html = _html_email(
            f"Resumo de entradas — {n} movimentações",
            "\n".join(linhas_html),
        )

    threading.Thread(
        target=_enviar_seguro,
        args=(destinatarios, assunto, corpo_txt, corpo_html),
        daemon=True,
    ).start()


# ── Ponto de entrada principal ────────────────────────────────────────────────

def disparar_notificacao(
    db,
    tipo: str,
    variaveis: dict,
    extras: list[str] | None = None,
    corpo_html: str | None = None,
):
    """
    Busca destinatários e template no banco, preenche variáveis e agenda envio.
    `extras` permite incluir endereços adicionais (ex: criador do requerimento)
    sem duplicá-los caso já estejam na lista cadastrada.
    `corpo_html` quando fornecido é enviado junto ao texto plain (multipart).

    Notificações do tipo 'entrada' são agrupadas em uma janela de 30 minutos:
    a primeira entrada inicia o timer; entradas seguintes acumulam na fila.
    Todos os outros tipos são enviados imediatamente.
    """
    global _batch_timer, _batch_assunto_tpl, _batch_corpo_tpl

    from models import NotificacaoEmail, NotificacaoTemplate

    emails = db.query(NotificacaoEmail).filter(
        NotificacaoEmail.tipo  == tipo,
        NotificacaoEmail.ativo == True,
    ).all()
    destinatarios = [e.email for e in emails]

    # Adiciona extras sem duplicar
    if extras:
        for e in extras:
            if e and e not in destinatarios:
                destinatarios.append(e)

    if not destinatarios:
        return

    template = db.query(NotificacaoTemplate).filter(
        NotificacaoTemplate.tipo == tipo
    ).first()
    if not template:
        return

    if tipo == "entrada":
        with _batch_lock:
            _batch_pending.append(variaveis)

            # Armazena destinatários e template da 1ª entrada da janela
            if not _batch_destinatarios:
                _batch_destinatarios.extend(destinatarios)
                _batch_assunto_tpl = template.assunto
                _batch_corpo_tpl   = template.corpo

            # Inicia timer apenas na 1ª entrada; as demais apenas acumulam
            if _batch_timer is None:
                t = threading.Timer(_BATCH_WINDOW, _flush_batch)
                t.daemon = True
                t.start()
                _batch_timer = t
        return

    # Outros tipos: envio imediato
    assunto   = _preencher(template.assunto, variaveis)
    corpo_txt = _preencher(template.corpo,   variaveis)

    threading.Thread(
        target=_enviar_seguro,
        args=(destinatarios, assunto, corpo_txt, corpo_html),
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

    n     = len(mats_alerta)
    agora = _agora_br().strftime("%d/%m/%Y %H:%M")
    assunto = f"Alerta de estoque minimo — {n} material(is) abaixo do minimo"

    # Plain-text
    linhas_txt = [
        f"{n} material(is) atingiram ou estao abaixo do estoque minimo.",
        f"Data do alerta: {agora}",
        "=" * 50,
    ]
    for mat in mats_alerta:
        grupo = mat.grupo.nome if mat.grupo else "—"
        linhas_txt.append(
            f"\nMaterial: {mat.nome}\n"
            f"Quantidade atual: {mat.quantidade} {mat.unidade}\n"
            f"Quantidade minima: {mat.quantidade_minima} {mat.unidade}\n"
            f"Grupo: {grupo}"
        )
        linhas_txt.append("-" * 40)
    corpo_txt = "\n".join(linhas_txt)

    # HTML
    linhas_html = []
    linhas_html.append(
        f'<p style="margin:0 0 16px;font-size:15px;color:#444">'
        f'<b>{n}</b> material(is) atingiram ou estão abaixo do estoque mínimo.'
        f' Alerta gerado em: <b>{agora}</b></p>'
    )
    linhas_html.append('<table style="width:100%;border-collapse:collapse">')
    for mat in mats_alerta:
        grupo = mat.grupo.nome if mat.grupo else "—"
        linhas_html.append(_linha_info("Material", mat.nome, destaque=True))
        linhas_html.append(_linha_info("Qtd atual", f"{mat.quantidade} {mat.unidade}"))
        linhas_html.append(_linha_info("Qtd mínima", f"{mat.quantidade_minima} {mat.unidade}"))
        linhas_html.append(_linha_info("Grupo", grupo))
        linhas_html.append(
            '<tr><td colspan="2" style="padding:4px 0;border-bottom:1px solid #eee"></td></tr>'
        )
    linhas_html.append("</table>")
    corpo_html = _html_email(
        f"Alerta de estoque — {n} material(is)",
        "\n".join(linhas_html),
    )

    threading.Thread(
        target=_enviar_seguro,
        args=(destinatarios, assunto, corpo_txt, corpo_html),
        daemon=True,
    ).start()
