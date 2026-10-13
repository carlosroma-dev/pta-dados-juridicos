import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from fase1_engenharia.api.models.alertas import AlertaDisparoRequest, AlertaDisparoResponse
from fase2_agente.automacoes.verificar_prazos import (
    EMAILS_ADVOGADOS,
    agrupar_por_advogado,
    buscar_prazos,
    enviar_emails,
    resumir_processos,
)

router = APIRouter(prefix="/alertas", tags=["alertas"])
log = logging.getLogger(__name__)

_HISTORICO_FILE = Path(__file__).resolve().parents[3] / "logs" / "alertas_historico.json"
_EMAILS_FILE    = Path(__file__).resolve().parents[3] / "logs" / "emails_advogados.json"


def _carregar_historico() -> list[dict]:
    if not _HISTORICO_FILE.exists():
        return []
    try:
        return json.loads(_HISTORICO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _salvar_historico(entrada: dict) -> None:
    historico = _carregar_historico()
    historico.insert(0, entrada)
    historico = historico[:20]
    _HISTORICO_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HISTORICO_FILE.write_text(
        json.dumps(historico, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


# ── Emails dos advogados ──────────────────────────────────────────────────────

@router.get("/emails")
def get_emails_advogados():
    """Retorna a configuração atual de emails dos advogados.
    Se ainda não foi salva, retorna os valores padrão do .env.
    """
    if _EMAILS_FILE.exists():
        try:
            return json.loads(_EMAILS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return EMAILS_ADVOGADOS   # fallback para os valores do .env


@router.put("/emails")
def salvar_emails_advogados(emails: dict[str, str]):
    """Salva a configuração de emails dos advogados."""
    if not emails:
        raise HTTPException(status_code=422, detail="Nenhum email informado.")
    _EMAILS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _EMAILS_FILE.write_text(
        json.dumps(emails, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"status": "salvo", "total": len(emails)}


# ── Disparo ───────────────────────────────────────────────────────────────────

@router.post("/disparar", response_model=AlertaDisparoResponse)
def disparar_alertas(body: AlertaDisparoRequest):
    if body.n_dias < 1 or body.n_dias > 90:
        raise HTTPException(status_code=422, detail="n_dias deve ser entre 1 e 90.")

    try:
        estado = {
            "n_dias": body.n_dias,
            "processos": [],
            "grupos": {},
            "emails_enviados": 0,
            "emails_advogados": body.emails_advogados or {},
        }
        estado = buscar_prazos(estado)
        estado = resumir_processos(estado) 
        estado = agrupar_por_advogado(estado)

        if not body.dry_run:
            estado = enviar_emails(estado)

    except Exception as exc:
        log.error("Erro ao executar workflow de alertas: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    resultado = {
        "executado_em": datetime.now().isoformat(),
        "n_dias": body.n_dias,
        "dry_run": body.dry_run,
        "processos_encontrados": len(estado["processos"]),
        "emails_enviados": estado["emails_enviados"],
        "grupos": estado["grupos"],
    }
    _salvar_historico(resultado)
    return resultado


@router.get("/historico")
def historico_alertas():
    return _carregar_historico()