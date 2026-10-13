import json
import uuid
from pathlib import Path

from fase2_agente.memoria.janela import TAMANHO_JANELA

_ARQUIVO = Path("fase3_interface/.dados/sessoes.json")


def _carregar() -> dict[str, list[dict]]:
    if not _ARQUIVO.exists():
        return {}
    dados = json.loads(_ARQUIVO.read_text(encoding="utf-8"))
    return {item["id"]: item.get("mensagens", []) for item in dados}


def _salvar(sessoes: dict[str, list[dict]]) -> None:
    _ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    dados = [{"id": sid, "mensagens": msgs} for sid, msgs in sessoes.items()]
    _ARQUIVO.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_sessao(session_id: str | None) -> tuple[str, list[dict]]:
    """Retorna (session_id, historico). Cria nova sessão se session_id for None."""
    sessoes = _carregar()
    sid = session_id or uuid.uuid4().hex
    return sid, sessoes.get(sid, [])


def salvar_sessao(session_id: str, historico: list[dict]) -> None:
    """Persiste o histórico da sessão, aplicando a janela deslizante."""
    sessoes = _carregar()
    sessoes[session_id] = historico[-TAMANHO_JANELA * 2:]
    _salvar(sessoes)
