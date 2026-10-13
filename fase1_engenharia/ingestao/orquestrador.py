"""Orquestrador de ingestão de um único PDF.

Recebe o caminho de um PDF e roda
o pipeline completo de uma vez:

    extrair (pdfplumber) → estruturar (LLM + Pydantic) → indexar (pgvector)

"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from fase1_engenharia.schemas.documents_schemas import DocumentoEstruturado

log = logging.getLogger(__name__)

# ~500 tokens por chunk com ~50 de sobreposição.
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200

# Prompt de estruturação — idêntico ao do pipeline em lote, para o resultado da
_PROMPT_ESTRUTURACAO = "Extraia as informações estruturadas deste documento jurídico:\n\n{texto}"


# ── Resultado e erros ──────────────────────────────────────────────────────────

@dataclass
class ResultadoIngestao:
    """O que a ingestão produziu, devolvido a quem chamou (ex.: para gravar no
    registro `documentos_ingestao`)."""

    num_chunks: int                      # quantos chunks novos foram indexados
    processo_numero: Optional[str]       # extraído na estruturação (pode ser None)
    tipo_documento: Optional[str]        # extraído na estruturação (pode ser None)


class IngestaoError(Exception):
    """Falha em alguma etapa da ingestão.

    Carrega a `etapa` onde ocorreu ("extraindo" | "estruturando" | "indexando")
    e uma `mensagem` amigável em PT (sem detalhe técnico). A `causa` original é
    guardada só para log interno — nunca chega ao usuário final.
    """

    def __init__(self, etapa: str, mensagem: str, causa: Optional[Exception] = None) -> None:
        self.etapa = etapa
        self.mensagem = mensagem
        self.causa = causa
        super().__init__(mensagem)


# ── Recursos pesados ──────────────────────────────────\

_llm = None
_modelo_embedding = None


def _get_llm():
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI

        log.info("Inicializando LLM de estruturação (OpenAI)...")
        _llm = ChatOpenAI(
            model="gpt-5.4-mini-2026-03-17",
            temperature=0,  # determinístico: não inventar campos
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    return _llm


def _get_modelo_embedding():
    global _modelo_embedding
    if _modelo_embedding is None:
        from sentence_transformers import SentenceTransformer

        log.info("Carregando modelo de embeddings (nomic)...")
        _modelo_embedding = SentenceTransformer(
            "nomic-ai/nomic-embed-text-v1", trust_remote_code=True
        )
    return _modelo_embedding


# ── Etapas (funções separadas: fáceis de testar e de trocar isoladamente) ──────

def _extrair(caminho: Path) -> str:
    """Etapa 1 — texto do PDF via pdfplumber."""
    from fase1_engenharia.utils.pdf_handler import extrair_texto_pdf

    return extrair_texto_pdf(str(caminho))


def _estruturar(texto: str) -> DocumentoEstruturado:
    """Etapa 2 — texto bruto → `DocumentoEstruturado` validado pelo Pydantic."""
    modelo_estruturado = _get_llm().with_structured_output(DocumentoEstruturado)
    return modelo_estruturado.invoke(_PROMPT_ESTRUTURACAO.format(texto=texto))


def _flatten(dados: dict) -> str:
    """Achata o dict estruturado em texto 'chave: valor' para virar embedding —
    mesma representação usada na indexação em lote."""
    partes = []
    for chave, valor in dados.items():
        if isinstance(valor, list):
            valor = ", ".join(str(v) for v in valor)
        partes.append(f"{chave}: {valor}")
    return "\n".join(partes)


def _chunkar(texto: str) -> list[str]:
    chunks: list[str] = []
    inicio = 0
    while inicio < len(texto):
        chunks.append(texto[inicio:inicio + CHUNK_SIZE])
        inicio += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _indexar(dados: dict, documento_fonte: str, session: Session) -> int:
    """Etapa 3 — chunk → embedding → insert no pgvector. Devolve nº de chunks
    novos inseridos. Idempotente: chunks de conteúdo idêntico são ignorados.
    """
    texto = _flatten(dados)
    chunks = _chunkar(texto)
    modelo = _get_modelo_embedding()

    # script em lote.
    proximo_id = session.execute(
        text("SELECT COALESCE(MAX(id_chunk), 0) + 1 FROM documento_chunks")
    ).scalar()

    inseridos = 0
    for chunk in chunks:
        ja_existe = session.execute(
            text("SELECT 1 FROM documento_chunks WHERE conteudo = :conteudo"),
            {"conteudo": chunk},
        ).fetchone()
        if ja_existe:
            continue

        embedding = modelo.encode(chunk, normalize_embeddings=True).tolist()
        session.execute(
            text("""
                INSERT INTO documento_chunks
                    (id_chunk, conteudo, embedding, movimentacao_id,
                     processo_numero, documento_fonte, tipo_documento)
                VALUES
                    (:id, :conteudo, :embedding, NULL,
                     :processo_numero, :documento_fonte, :tipo_documento)
            """),
            {
                "id": proximo_id,
                "conteudo": chunk,
                "embedding": str(embedding),
                "processo_numero": dados.get("numero_processo"),
                "documento_fonte": documento_fonte,
                "tipo_documento": dados.get("tipo_documento"),
            },
        )
        proximo_id += 1
        inseridos += 1

    session.commit()
    return inseridos


# ── Orquestração ───────────────────────────────────────────────────────────────

def ingerir_pdf(
    caminho_pdf: str | Path,
    session: Session,
    on_etapa: Optional[Callable[[str], None]] = None,
) -> ResultadoIngestao:
    """Roda o pipeline completo para um PDF: extrair → estruturar → indexar.

    `on_etapa(etapa)` é chamado no início de cada etapa ("extraindo",
    "estruturando", "indexando"), permitindo a quem orquestra refletir o
    progresso (ex.: atualizar o status em `documentos_ingestao`).

    Levanta `IngestaoError` (com etapa + mensagem amigável) se qualquer etapa
    falhar. Em sucesso, devolve um `ResultadoIngestao`.
    """
    caminho = Path(caminho_pdf)

    def _avisar(etapa: str) -> None:
        log.info("[ingestao] %s — %s", caminho.name, etapa)
        if on_etapa is not None:
            on_etapa(etapa)

    # 1) Extração
    _avisar("extraindo")
    try:
        texto = _extrair(caminho)
    except Exception as e:
        raise IngestaoError(
            "extraindo",
            "Não consegui ler o conteúdo deste PDF. Verifique se o arquivo não está corrompido.",
            e,
        ) from e
    if not texto or not texto.strip():
        raise IngestaoError(
            "extraindo",
            "Este PDF não tem texto selecionável (pode ser um documento escaneado em imagem). "
            "Envie um PDF com texto.",
        )

    # 2) Estruturação
    _avisar("estruturando")
    try:
        estruturado = _estruturar(texto)
    except Exception as e:
        raise IngestaoError(
            "estruturando",
            "Não consegui interpretar as informações deste documento. Tente novamente em instantes.",
            e,
        ) from e

    dados = estruturado.model_dump()

    # 3) Indexação
    _avisar("indexando")
    try:
        num_chunks = _indexar(dados, caminho.stem, session)
    except Exception as e:
        raise IngestaoError(
            "indexando",
            "Não consegui salvar o documento para consulta. Tente novamente em instantes.",
            e,
        ) from e

    return ResultadoIngestao(
        num_chunks=num_chunks,
        processo_numero=dados.get("numero_processo"),
        tipo_documento=dados.get("tipo_documento"),
    )