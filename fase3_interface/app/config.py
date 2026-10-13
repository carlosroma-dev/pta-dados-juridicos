from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Carrega o `.env` da raiz do projeto. Quando o Streamlit é executado a partir
# da raiz, o CWD é a raiz e o python-dotenv encontra o arquivo sozinho.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Configurações lidas do ambiente, agrupadas num objeto imutável."""

    api_base_url: str   # endereço base da FastAPI (ex: http://localhost:8000)
    api_key: str        # chave enviada no header X-API-Key (vazia = sem auth)
    api_timeout: float  # timeout das requisições HTTP em segundos


def get_settings() -> Settings:
    """Lê as variáveis de ambiente e devolve um `Settings`.

    Defaults pensados para desenvolvimento local: a API sobe em :8000 e, se a
    `API_KEY` estiver vazia, a FastAPI roda sem autenticação (mesmo
    comportamento do `main.py`).
    """
    return Settings(
        api_base_url=os.getenv("API_BASE_URL", "http://localhost:8000"),
        api_key=os.getenv("API_KEY", ""),
        api_timeout=float(os.getenv("API_TIMEOUT", "30")),
    )