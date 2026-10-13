"""Persistência das conversas recentes do agente (Fase 3).

Guarda as últimas conversas num arquivo JSON local para que apareçam na barra
lateral entre sessões — no espírito da lista "Recentes". É um armazenamento de
arquivo único, pensado para uso local / cliente único; não substitui um banco
multiusuário (cada usuário do escritório compartilharia o mesmo arquivo).

O arquivo fica em `fase3_interface/.dados/conversas.json` e deve entrar no
.gitignore — são dados de uso, não código.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

MAX_RECENTES = 5

# .../app/services/historico.py → sobe 3 níveis → fase3_interface/
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ARQUIVO = os.path.join(_BASE, ".dados", "conversas.json")


def carregar() -> list[dict[str, Any]]:
    """Lê as conversas salvas (mais recente primeiro). Nunca levanta exceção."""
    try:
        with open(_ARQUIVO, encoding="utf-8") as arq:
            dados = json.load(arq)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    if not isinstance(dados, list):
        return []
    return dados


def _gravar(conversas: list[dict[str, Any]]) -> None:
    """Gravação atômica para não corromper o arquivo em caso de falha."""
    os.makedirs(os.path.dirname(_ARQUIVO), exist_ok=True)
    temporario = _ARQUIVO + ".tmp"
    with open(temporario, "w", encoding="utf-8") as arq:
        json.dump(conversas, arq, ensure_ascii=False, indent=2)
    os.replace(temporario, _ARQUIVO)


def salvar(conversa: dict[str, Any]) -> dict[str, Any]:
    """Insere ou atualiza uma conversa e mantém só as MAX_RECENTES mais recentes.

    Gera um `id` se a conversa ainda não tiver um. Devolve a conversa já com o
    `id` garantido, para o chamador guardar a referência.
    """
    conversa = dict(conversa)
    if not conversa.get("id"):
        conversa["id"] = uuid.uuid4().hex
    conversa["atualizada_em"] = time.time()

    restantes = [c for c in carregar() if c.get("id") != conversa["id"]]
    restantes.insert(0, conversa)
    restantes.sort(key=lambda c: c.get("atualizada_em", 0), reverse=True)
    _gravar(restantes[:MAX_RECENTES])
    return conversa