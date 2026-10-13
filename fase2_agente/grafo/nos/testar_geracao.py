"""
Teste do nó gerar_resposta (Fase 2).

Puxa chunks reais via PgVectorRetriever e verifica se o LLM
gera uma resposta coerente com o contexto recuperado.

Uso (na raiz do projeto):
    python3 -m fase2_agente.grafo.nos.testar_geracao
"""

from fase2_agente.grafo.nos.gerar_resposta import gerar_resposta
from fase2_agente.rag.retriever import PgVectorRetriever


def main():
    retriever = PgVectorRetriever(k=3)

    perguntas = [
        "Qual é o valor da causa?",
        "Quem são as partes do processo?",
        "Qual é o status do processo?",
    ]

    for pergunta in perguntas:
        chunks = retriever.invoke(pergunta)

        resultado = gerar_resposta({
            "pergunta": pergunta,
            "tipo_consulta": "vetorial",
            "chunks_recuperados": chunks,
            "resposta": "",
        })

        print(f"\n{'='*60}")
        print(f"Pergunta: {pergunta}")
        print(f"Chunks usados: {len(chunks)}")
        print(f"Resposta:\n{resultado['resposta']}")

    # Validações
    print(f"\n{'='*60}")
    print("Validações")
    print("-" * 60)

    chunks = retriever.invoke("contrato de honorários")
    resultado = gerar_resposta({
        "pergunta": "contrato de honorários",
        "tipo_consulta": "vetorial",
        "chunks_recuperados": chunks,
        "resposta": "",
    })

    assert resultado["resposta"], "Resposta veio vazia"
    assert "resposta" in resultado, "Campo 'resposta' ausente no estado"
    print("Todos os asserts passaram ✓")


if __name__ == "__main__":
    main()
