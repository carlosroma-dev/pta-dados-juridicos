"""Schemas Pydantic da ingestão de documentos (entrada/saída da API).

Separados dos modelos ORM (`db/models.py`) de propósito: estes definem só o
formato JSON que a API troca com a interface. `from_attributes=True` permite
converter o objeto SQLAlchemy `DocumentoIngestao` direto em resposta.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class IngestaoOut(BaseModel):
    """Representa uma linha de `documentos_ingestao` na API.

    Usado como resposta do `POST /documentos/ingerir` e (no passo 5b) do
    `GET /documentos/{id}` que a interface consulta no polling.
    """

    model_config = ConfigDict(from_attributes=True)

    id_ingestao: int
    nome_arquivo: str
    nome_original: Optional[str] = None
    status: str
    mensagem_erro: Optional[str] = None
    num_chunks: Optional[int] = None
    processo_numero: Optional[str] = None
    tipo_documento: Optional[str] = None
    data_ingestao: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None