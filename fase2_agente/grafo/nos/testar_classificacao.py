"""
Teste do nó classificar_pergunta (Fase 2).

Verifica se o classificador roteia corretamente perguntas
para vetorial, relacional e solicita reformulação quando ambíguo.

Uso (na raiz do projeto):
    python3 -m fase2_agente.grafo.nos.testar_classificacao
"""

from fase2_agente.grafo.nos.classificar_pergunta import classificar_pergunta

ESTADO_BASE = {
    "pergunta": "",
    "tipo_consulta": "",
    "chunks_recuperados": [],
    "resposta": "",
}

CASOS = [
    # (pergunta, tipo_esperado)

    # Relacional — contexto suficiente para consulta SQL
    ("Quais honorários estão em atraso?",                            "relacional"),
    ("Quais processos vencem nos próximos 7 dias?",                  "relacional"),
    ("Qual o status do processo 0009876?",                           "relacional"),
    ("Quantos clientes temos cadastrados em Recife?",                "relacional"),
    ("Quais processos do cliente João da Silva estão em recurso?",   "relacional"),

    # Vetorial — conteúdo de documento com identificador claro
    ("O que diz o contrato de honorários da Ana Lima?",              "vetorial"),
    ("Qual a cláusula de rescisão do contrato do processo 0001234?", "vetorial"),
    ("O que foi decidido na intimação de sentença do processo 0009876?", "vetorial"),
    ("O que a petição inicial do processo 0002345 alega?",           "vetorial"),

    # Reformular — válidas mas sem contexto suficiente para buscar
    ("Qual o valor do processo?",                                    "reformular"),
    ("O que foi decidido?",                                          "reformular"),
    ("Quais são os honorários?",                                     "reformular"),
    ("Me fala sobre o contrato",                                     "reformular"),
    ("O que foi decidido na intimação de sentença?",                 "reformular"),
    ("aaabbbccc",                                                    "reformular"),
]


def main():
    print(f"{'='*60}")
    print("Testando classificador de perguntas")
    print(f"{'='*60}")

    erros = 0
    for pergunta, esperado in CASOS:
        resultado = classificar_pergunta({**ESTADO_BASE, "pergunta": pergunta})
        obtido = resultado["tipo_consulta"]
        status = "✓" if obtido == esperado else "✗"
        print(f"\n  {status} [{esperado}] {pergunta}")
        if obtido != esperado:
            print(f"      → obtido: {obtido}")
            erros += 1

    print(f"\n{'='*60}")
    if erros == 0:
        print("Todos os asserts passaram ✓")
    else:
        print(f"{erros} caso(s) falharam ✗")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
