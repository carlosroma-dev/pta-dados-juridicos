import os
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy import text
from fase1_engenharia.db.database import SessionLocal

load_dotenv()

modelo = SentenceTransformer("nomic-ai/nomic-embed-text-v1", trust_remote_code=True)

def buscar(consulta: str, top_k: int = 3):
    print(f"\n🔍 Busca: '{consulta}'")
    print("-" * 60)
    embedding = modelo.encode(consulta, normalize_embeddings=True).tolist()
    with SessionLocal() as session:
        resultados = session.execute(
            text("""
                SELECT conteudo, embedding <=> :embedding AS distancia
                FROM documento_chunks
                ORDER BY distancia
                LIMIT :k
            """),
            {"embedding": str(embedding), "k": top_k}
        ).fetchall()
    for i, (conteudo, distancia) in enumerate(resultados, 1):
        print(f"\n[{i}] Distância: {distancia:.4f}")
        print(conteudo[:300])

if __name__ == "__main__":
    buscar("acordo de indenização por danos morais")
    buscar("contrato de honorários advocatícios")
    buscar("intimação para contrarrazões de apelação")