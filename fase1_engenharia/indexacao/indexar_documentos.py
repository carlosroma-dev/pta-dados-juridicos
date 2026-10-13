import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from fase1_engenharia.db.database import SessionLocal

load_dotenv()

# Configuração do log
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-7s | %(message)s')
log = logging.getLogger(__name__)

# Modelo de embeddings
log.info("Carregando modelo de embeddings...")
modelo = SentenceTransformer("nomic-ai/nomic-embed-text-v1", trust_remote_code=True)
log.info("Modelo carregado!")

# Caminhos
PASTA_STRUCTURED = Path("data/structured")

# Estratégia de chunking
# ~500 tokens ≈ 2000 caracteres | sobreposição de ~50 tokens ≈ 200 caracteres
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200


def gerar_embedding(texto: str) -> list[float]:
    vetor = modelo.encode(texto, normalize_embeddings=True)
    return vetor.tolist()


def texto_do_json(dados: dict) -> str:
    partes = []
    for chave, valor in dados.items():
        if isinstance(valor, list):
            valor = ", ".join(str(v) for v in valor)
        partes.append(f"{chave}: {valor}")
    return "\n".join(partes)


def chunkar_texto(texto: str) -> list[str]:
    chunks = []
    inicio = 0
    while inicio < len(texto):
        fim = inicio + CHUNK_SIZE
        chunks.append(texto[inicio:fim])
        inicio += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def indexar_documento(caminho_json: Path, session):
    with open(caminho_json, "r", encoding="utf-8") as f:
        dados = json.load(f)

    # Metadados de origem — gravados em colunas dedicadas
    processo_numero = dados.get("numero_processo")
    tipo_documento = dados.get("tipo_documento")
    documento_fonte = caminho_json.stem   # nome do arquivo sem extensão

    texto = texto_do_json(dados)
    chunks = chunkar_texto(texto)

    inseridos = 0
    ignorados = 0

    for i, chunk in enumerate(chunks):
        # Idempotência
        resultado = session.execute(
            text("SELECT id_chunk FROM documento_chunks WHERE conteudo = :conteudo"),
            {"conteudo": chunk}
        ).fetchone()

        if resultado:
            ignorados += 1
            continue

        embedding = gerar_embedding(chunk)

        max_id = session.execute(
            text("SELECT COALESCE(MAX(id_chunk), 0) + 1 FROM documento_chunks")
        ).scalar()

        session.execute(
            text("""
                INSERT INTO documento_chunks
                    (id_chunk, conteudo, embedding, movimentacao_id,
                     processo_numero, documento_fonte, tipo_documento)
                VALUES
                    (:id, :conteudo, :embedding, :mov_id,
                     :processo_numero, :documento_fonte, :tipo_documento)
            """),
            {
                "id": max_id,
                "conteudo": chunk,
                "embedding": str(embedding),

                "mov_id": None,
                "processo_numero": processo_numero,
                "documento_fonte": documento_fonte,
                "tipo_documento": tipo_documento,
            }
        )
        inseridos += 1

    session.commit()
    log.info(f"{caminho_json.name}: {inseridos} chunks inseridos, {ignorados} ignorados")


def main():
    arquivos = list(PASTA_STRUCTURED.glob("*.json"))
    log.info(f"Encontrados {len(arquivos)} documentos para indexar.")

    with SessionLocal() as session:
        for arquivo in arquivos:
            try:
                indexar_documento(arquivo, session)
            except Exception as e:
                log.error(f"Erro ao indexar {arquivo.name}: {e}")
                session.rollback()

    log.info("Indexação concluída!")


if __name__ == "__main__":
    main()
