"""
Teste do retriever semântico (Fase 2).

Roda algumas perguntas de exemplo, imprime os chunks recuperados com
seus metadados de origem, e valida o comportamento esperado com asserts.

Uso (na raiz do projeto):
    python -m fase2_agente.rag.testar_retriever
"""

from fase2_agente.rag.retriever import PgVectorRetriever

def exibir_resultados(pergunta: str, docs):
    print(f"\n{'='*70}")
    print(f"Pergunta: \"{pergunta}\"")
    print(f"Chunks retornados: {len(docs)}")
    print('-' * 70)

    for i, doc in enumerate(docs, start=1):
        meta = doc.metadata
        print(f"\n  [{i}] distancia: {meta['distancia']}")
        print(f"      processo_numero: {meta['processo_numero']}")
        print(f"      documento_fonte: {meta['documento_fonte']}")
        print(f"      tipo_documento:  {meta['tipo_documento']}")
        print(f"      chunk_id:        {meta['chunk_id']}")
        print(f"      trecho: {doc.page_content[:150]}...")

def main():
    retriever = PgVectorRetriever(k=3)

    perguntas = [
        "contrato de honorários advocatícios",
        "ação de cobrança de aluguéis",
        "prestação de serviços jurídicos",
    ]

    for pergunta in perguntas:
        docs = retriever.invoke(pergunta)
        exibir_resultados(pergunta, docs)

# ── Validações automáticas ──────────────────────────────────
    print(f"\n{'='*70}")
    print("Validações")
    print('-' * 70)

    docs = retriever.invoke("contrato de honorários")

    assert len(docs) > 0, "Esperava ao menos 1 documento, veio vazio"
    assert docs[0].page_content, "page_content do primeiro doc está vazio"

    meta = docs[0].metadata
    for chave in ("chunk_id", "processo_numero", "documento_fonte", "tipo_documento", "distancia"):
        assert chave in meta, f"metadata sem a chave '{chave}'"

    assert docs[0].metadata["distancia"] < 1.0, "distância suspeitamente alta"

    print("Todos os asserts passaram ✓")


if __name__ == "__main__":
    main()