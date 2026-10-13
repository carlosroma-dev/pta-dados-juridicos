import resend
import logging
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM", "onboarding@resend.dev")


def enviar_email(
    destinatario: str,
    assunto: str,
    html: Optional[str] = None,
    texto: Optional[str] = None,
) -> bool:
    """Envia um email via Resend.

    Prefere HTML quando disponível; texto puro como fallback.
    Retorna True se enviou com sucesso.
    """
    if not html and not texto:
        log.error("enviar_email chamado sem conteúdo (html e texto vazios).")
        return False

    try:
        params: dict = {
            "from":    EMAIL_FROM,
            "to":      [destinatario],
            "subject": assunto,
        }
        if html:
            params["html"] = html
        if texto:
            params["text"] = texto

        resend.Emails.send(params)
        log.info("Email enviado para %s", destinatario)
        return True

    except Exception as e:
        log.error("Erro ao enviar email para %s: %s", destinatario, e)
        return False