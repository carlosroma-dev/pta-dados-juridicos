from fastapi import APIRouter, Depends, HTTPException
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from sqlalchemy.orm import Session

from fase1_engenharia.api.models.busca import BuscaRequest, ChunkOut
from fase1_engenharia.db.database import get_db

router = APIRouter(prefix="/busca", tags=["busca"])

# None até a primeira chamada à /busca — evita travar o startup do uvicorn.
_modelo: SentenceTransformer | None = None


def _get_modelo() -> SentenceTransformer:
    global _modelo
    if _modelo is None:
        _modelo = SentenceTransformer("nomic-ai/nomic-embed-text-v1", trust_remote_code=True)
    return _modelo


@router.post("/")
def busca_semantica(body: BuscaRequest, db: Session = Depends(get_db)):
    """Retorna os chunks de documentos mais relevantes para a pergunta fornecida.

    Fluxo:
    1. Converte a pergunta em vetor usando o modelo de embedding.
    2. Consulta o pgvector com distância cosseno (<=>) para ranquear os chunks.
    3. Retorna os top_k mais próximos com o conteúdo e a distância.
    """
    try:
        # Gera o embedding da pergunta — normalize_embeddings=True padroniza a magnitude,
        # tornando a distância cosseno equivalente à similaridade cosseno.
        embedding = _get_modelo().encode(body.pergunta, normalize_embeddings=True).tolist()

        # <=> é o operador de distância cosseno do pgvector.
        # Menor distância = mais similar semanticamente.
        resultados = db.execute(
            text("""
                SELECT conteudo, embedding <=> :embedding AS distancia
                FROM documento_chunks
                ORDER BY distancia
                LIMIT :top_k
            """),
            {"embedding": str(embedding), "top_k": body.top_k},
        ).fetchall()

        chunks = [ChunkOut(conteudo=r.conteudo, distancia=r.distancia) for r in resultados]
        return {
            "pergunta": body.pergunta,
            "resultados": [c.model_dump() for c in chunks],
            "total": len(chunks),
            "status": "ok",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chunks")
def listar_todos_chunks(limite: int = 200, db: Session = Depends(get_db)):
    """Retorna todos os chunks indexados (até `limite`), sem filtro de relevância.

    Usado pela aba de Insights para análise autônoma da base completa.
    """
    try:
        resultados = db.execute(
            text("""
                SELECT conteudo, documento_fonte, tipo_documento
                FROM documento_chunks
                ORDER BY id_chunk
                LIMIT :limite
            """),
            {"limite": limite},
        ).fetchall()

        return {
            "chunks": [
                {"conteudo": r.conteudo, "documento_fonte": r.documento_fonte, "tipo_documento": r.tipo_documento}
                for r in resultados
            ],
            "total": len(resultados),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
