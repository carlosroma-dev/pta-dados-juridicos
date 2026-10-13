"""
Teste das ferramentas do agente jurídico (Fase 2).

Executa chamadas reais em cada ferramenta, valida a estrutura da saída
e imprime o resultado para inspeção visual.

Uso (na raiz do projeto):
    python -m fase2_agente.ferramentas.testar_ferramentas
"""

from fase2_agente.ferramentas import (
    buscar_documento,
    checar_honorarios,
    status_carteira,
    verificar_prazos,
)


def secao(titulo: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {titulo}")
    print("=" * 70)


def subsecao(titulo: str) -> None:
    print(f"\n  ── {titulo}")
    print("  " + "─" * 50)


# ── buscar_documento ─────────────────────────────────────────────────────────

def testar_buscar_documento() -> int:
    secao("buscar_documento")
    erros = 0

    casos = [
        ("contrato de honorários advocatícios",   3),
        ("cláusula de rescisão contratual",        3),
        ("prazo para recurso de apelação",         3),
    ]

    for pergunta, top_k in casos:
        subsecao(f'pergunta="{pergunta}" top_k={top_k}')
        resultado = buscar_documento.invoke({"pergunta": pergunta, "top_k": top_k})

        assert isinstance(resultado, str), "resultado deve ser str"
        assert len(resultado) > 0, "resultado não pode ser vazio"
        print(resultado[:400], "..." if len(resultado) > 400 else "")

    # top_k fora do intervalo — deve ser clampado sem erro
    subsecao("top_k=0 → deve ser tratado como 1 (clamp)")
    resultado = buscar_documento.invoke({"pergunta": "honorários", "top_k": 0})
    assert isinstance(resultado, str)
    print(f"  ok — retornou {len(resultado)} caracteres")

    subsecao("top_k=999 → deve ser tratado como 20 (clamp)")
    resultado = buscar_documento.invoke({"pergunta": "honorários", "top_k": 999})
    assert isinstance(resultado, str)
    print(f"  ok — retornou {len(resultado)} caracteres")

    print(f"\n  buscar_documento: {len(casos) + 2} caso(s) — {erros} erro(s)")
    return erros


# ── verificar_prazos ─────────────────────────────────────────────────────────

def testar_verificar_prazos() -> int:
    secao("verificar_prazos")
    erros = 0

    subsecao("janela padrão (7 dias)")
    resultado = verificar_prazos.invoke({})
    assert isinstance(resultado, str)
    assert len(resultado) > 0
    print(resultado[:500], "..." if len(resultado) > 500 else "")

    subsecao("janela de 30 dias")
    resultado = verificar_prazos.invoke({"dias": 30})
    assert isinstance(resultado, str)
    print(resultado[:500], "..." if len(resultado) > 500 else "")

    subsecao("janela de 1 dia")
    resultado = verificar_prazos.invoke({"dias": 1})
    assert isinstance(resultado, str)
    print(f"  ok — retornou {len(resultado)} caracteres")

    subsecao("filtro por tipo: trabalhista")
    resultado = verificar_prazos.invoke({"dias": 30, "tipo": "trabalhista"})
    assert isinstance(resultado, str)
    print(f"  ok — retornou {len(resultado)} caracteres")

    subsecao("dias fora do intervalo (0 → clamp 1, 999 → clamp 90)")
    r0 = verificar_prazos.invoke({"dias": 0})
    r999 = verificar_prazos.invoke({"dias": 999})
    assert isinstance(r0, str)
    assert isinstance(r999, str)
    print("  ok — ambos retornaram str sem exceção")

    print(f"\n  verificar_prazos: 5 caso(s) — {erros} erro(s)")
    return erros


# ── checar_honorarios ─────────────────────────────────────────────────────────

def testar_checar_honorarios() -> int:
    secao("checar_honorarios")
    erros = 0

    subsecao("carteira completa (sem filtros)")
    resultado = checar_honorarios.invoke({})
    assert isinstance(resultado, str)
    assert "RESUMO DE HONORÁRIOS" in resultado, "cabeçalho esperado ausente"
    assert "Total contratado" in resultado
    assert "Total pago" in resultado
    assert "Total em aberto" in resultado
    print(resultado[:600], "..." if len(resultado) > 600 else "")

    subsecao("filtro status=atrasado")
    resultado = checar_honorarios.invoke({"status_pagamento": "atrasado"})
    assert isinstance(resultado, str)
    # se houver atrasados, o ícone deve aparecer; se não houver, a msg de vazio
    print(resultado[:400], "..." if len(resultado) > 400 else "")

    subsecao("filtro status=quitado")
    resultado = checar_honorarios.invoke({"status_pagamento": "quitado"})
    assert isinstance(resultado, str)
    print(f"  ok — retornou {len(resultado)} caracteres")

    subsecao("processo_numero inexistente → mensagem de vazio")
    resultado = checar_honorarios.invoke({"processo_numero": "0000000-00.0000.0.00.0000"})
    assert isinstance(resultado, str)
    assert len(resultado) > 0
    print(f"  ok — {resultado.strip()}")

    print(f"\n  checar_honorarios: 4 caso(s) — {erros} erro(s)")
    return erros


# ── status_carteira ───────────────────────────────────────────────────────────

def testar_status_carteira() -> int:
    secao("status_carteira")
    erros = 0

    subsecao("painel completo")
    resultado = status_carteira.invoke({})
    assert isinstance(resultado, str)
    assert "PAINEL DA CARTEIRA" in resultado, "cabeçalho esperado ausente"
    assert "PROCESSOS" in resultado
    assert "ALERTAS DE PRAZO" in resultado
    assert "HONORÁRIOS" in resultado
    print(resultado[:800], "..." if len(resultado) > 800 else "")

    print(f"\n  status_carteira: 1 caso(s) — {erros} erro(s)")
    return erros


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    total_erros = 0

    total_erros += testar_buscar_documento()
    total_erros += testar_verificar_prazos()
    total_erros += testar_checar_honorarios()
    total_erros += testar_status_carteira()

    print(f"\n{'='*70}")
    if total_erros == 0:
        print("Todos os asserts passaram ✓")
    else:
        print(f"{total_erros} caso(s) falharam ✗")
    print("=" * 70)


if __name__ == "__main__":
    main()