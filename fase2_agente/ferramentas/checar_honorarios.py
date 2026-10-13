"""Ferramenta: checar_honorarios

Resume a situação financeira de honorários de um processo específico
ou de toda a carteira, consultando o banco relacional.

Dor resolvida: o escritório não tinha visibilidade rápida sobre
inadimplência — saber quais clientes estão em atraso exigia abrir
planilhas manualmente. Essa ferramenta entrega o resumo financeiro
em linguagem natural, com valores pendentes destacados.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import text

from fase1_engenharia.db.database import SessionLocal

log = logging.getLogger(__name__)


@tool
def checar_honorarios(
    processo_numero: Optional[str] = None,
    status_pagamento: Optional[str] = None,
) -> str:
    """Resume a situação financeira dos honorários advocatícios.

    Sem argumentos, retorna o panorama de toda a carteira agrupado por
    status de pagamento. Com `processo_numero`, detalha apenas aquele
    processo. Com `status_pagamento`, filtra pelo status informado.

    Args:
        processo_numero:  Número do processo no formato CNJ (opcional).
                          Exemplo: "0001234-56.2023.8.17.0001"
        status_pagamento: Filtro por situação financeira (opcional).
                          Valores: "atrasado", "em_dia", "quitado".

    Returns:
        Resumo financeiro formatado com valores totais, pagos e em aberto,
        número de parcelas e forma de pagamento.
    """
    log.info(
        "checar_honorarios | processo=%s status=%s",
        processo_numero or "todos",
        status_pagamento or "todos",
    )

    sql = """
        SELECT
            h.id_honorarios,
            h.processo_numero,
            h.status_pagamento,
            h.valor_total_contratado,
            h.valor_pago,
            h.valor_em_aberto,
            h.numero_parcelas,
            h.parcelas_pagas,
            h.data_vencimento,
            h.forma_pagamento,
            h.honorario_exito,
            h.percentual_exito,
            c.nome AS cliente
        FROM honorarios h
        LEFT JOIN processos p ON p.numero_processo = h.processo_numero
        LEFT JOIN clientes c ON c.id_cliente = p.cliente_id
        WHERE 1=1
    """
    params: dict = {}

    if processo_numero:
        sql += " AND h.processo_numero = :numero"
        params["numero"] = processo_numero.strip()

    if status_pagamento:
        sql += " AND LOWER(h.status_pagamento) = :status"
        params["status"] = status_pagamento.lower()

    sql += " ORDER BY h.status_pagamento, h.data_vencimento"

    try:
        with SessionLocal() as session:
            rows = session.execute(text(sql), params).fetchall()
    except Exception as exc:
        log.error("Erro ao consultar honorários: %s", exc)
        return f"Erro ao acessar o banco de dados: {exc}"

    if not rows:
        return (
            "Nenhum registro de honorários encontrado "
            f"(processo={processo_numero or 'todos'}, "
            f"status={status_pagamento or 'todos'})."
        )

    total_contratado = sum(r.valor_total_contratado or 0 for r in rows)
    total_pago = sum(r.valor_pago or 0 for r in rows)
    total_em_aberto = sum(r.valor_em_aberto or 0 for r in rows)

    por_status: dict[str, list] = {}
    for r in rows:
        chave = r.status_pagamento or "indefinido"
        por_status.setdefault(chave, []).append(r)

    MAX_DETALHE = 30  # máximo de registros detalhados por resposta (evita estourar o LLM)

    linhas: list[str] = [
        f"{'='*60}",
        f"RESUMO DE HONORÁRIOS — {len(rows)} registro(s)",
        f"{'='*60}",
        f"Total contratado : R$ {total_contratado:,.2f}",
        f"Total pago       : R$ {total_pago:,.2f}",
        f"Total em aberto  : R$ {total_em_aberto:,.2f}",
        "",
    ]

    if len(rows) > MAX_DETALHE:
        linhas.append(
            f"⚠️  Exibindo os primeiros {MAX_DETALHE} de {len(rows)} registros "
            f"(os totais acima consideram TODOS os {len(rows)}).\n"
        )

    icones = {"atrasado": "🔴", "em_dia": "🟡", "quitado": "✅", "indefinido": "⚪"}

    detalhados = 0  # conta quantos registros já foram impressos em detalhe

    for status, registros in sorted(por_status.items()):
        icone = icones.get(status, "•")
        subtotal = sum(r.valor_em_aberto or 0 for r in registros)
        linhas.append(f"{icone} {status.upper()} ({len(registros)} processo(s))")
        linhas.append("─" * 60)

        for r in registros:
            if detalhados >= MAX_DETALHE:
                linhas.append("  [...] demais registros omitidos (ver totais no topo)")
                break

            parcelas_info = (
                f"{r.parcelas_pagas}/{r.numero_parcelas} parcelas"
                if r.numero_parcelas else "parcela única"
            )
            exito_info = (
                f" | Êxito: {r.percentual_exito:.0%}" if r.honorario_exito and r.percentual_exito else ""
            )
            v_contratado = r.valor_total_contratado or 0
            v_pago = r.valor_pago or 0
            v_aberto = r.valor_em_aberto or 0
            linhas.append(
                f"• Processo  : {r.processo_numero}\n"
                f"  Cliente   : {r.cliente or 'N/A'}\n"
                f"  Contratado: R$ {v_contratado:,.2f}\n"
                f"  Pago      : R$ {v_pago:,.2f} ({parcelas_info})\n"
                f"  Em aberto : R$ {v_aberto:,.2f}{exito_info}\n"
                f"  Vencimento: {r.data_vencimento} | Pagamento: {r.forma_pagamento or 'N/A'}\n"
            )
            detalhados += 1

        if status == "atrasado":
            linhas.append(f"  → Subtotal em aberto (atrasados): R$ {subtotal:,.2f}")
        linhas.append("")

    return "\n".join(linhas)