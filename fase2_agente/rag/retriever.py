from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun

from sentence_transformers import SentenceTransformer
from sqlalchemy import text

from fase1_engenharia.db.database import SessionLocal

import logging
from dotenv import load_dotenv

load_dotenv()

_modelo: SentenceTransformer | None = None
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)
log = logging.getLogger(__name__)


def _get_modelo() -> SentenceTransformer:
    global _modelo
    if _modelo is None:
        log.info("Carregando modelo de embeddings (%s)...", EMBEDDING_MODEL)
        _modelo = SentenceTransformer(EMBEDDING_MODEL, trust_remote_code=True)
        log.info("Modelo carregado!")
    return _modelo


class PgVectorRetriever(BaseRetriever):
    """Retriever semântico sobre pgvector (distância cosseno).

    Retorna List[Document] onde cada Document tem:
        - page_content: texto do chunk
        - metadata: {processo_numero, tipo_documento, distancia, chunk_id}

    Se ``processos_filtro`` for informado, a busca é restrita aos chunks
    daqueles processos (usado pela rota híbrida para cruzar o resultado
    relacional com os documentos). Vazio/None → busca global (padrão).
    """

    k: int = 5
    processos_filtro: Optional[List[str]] = None

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:

        """Busca os k chunks mais similares à query no pgvector."""

        # 1. Gerar embedding da pergunta
        #    normalize_embeddings=True — consistente com a indexação (Fase 1)
        modelo = _get_modelo()
        embedding = modelo.encode(query, normalize_embeddings=True).tolist()

        # 2. Montar o WHERE condicional.
        #    Só restringe por processo quando há filtro não-vazio;
        #    caso contrário, mantém a busca global (comportamento padrão).
        params = {"embedding": str(embedding), "k": self.k}
        where = ""
        if self.processos_filtro:
            where = "WHERE processo_numero = ANY(:processos)"
            params["processos"] = self.processos_filtro
            log.info("Busca vetorial escopada a %d processo(s)", len(self.processos_filtro))

        # 3. Buscar no pgvector os k chunks mais próximos (distância cosseno)
        sql = text(f"""
            SELECT
                id_chunk,
                conteudo,
                processo_numero,
                documento_fonte,
                tipo_documento,
                embedding <=> :embedding AS distancia
            FROM documento_chunks
            {where}
            ORDER BY distancia
            LIMIT :k
        """)

        with SessionLocal() as session:
            resultados = session.execute(sql, params).fetchall()

        # 4. Montar List[Document] com metadado de origem
        documentos: List[Document] = []
        for row in resultados:
            doc = Document(
                page_content=row.conteudo,
                metadata={
                    "chunk_id": row.id_chunk,
                    "processo_numero": row.processo_numero,
                    "documento_fonte": row.documento_fonte,
                    "tipo_documento": row.tipo_documento,
                    "distancia": round(row.distancia, 4),
                },
            )
            documentos.append(doc)

        return documentos