"""Ferramenta: status_carteira

Gera um painel consolidado da carteira do escritório: distribuição de
processos por status, alertas de prazo iminente e inadimplência.

Dor resolvida: a sócia do escritório precisava abrir três planilhas
diferentes para ter uma visão geral da carteira. Essa ferramenta
entrega o dashboard completo em uma única consulta, permitindo
decisões rápidas sobre prioridades do dia.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from langchain_core.tools import tool
from sqlalchemy import text

from fase1_engenharia.db.database import SessionLocal

log = logging.getLogger(__name__)


@tool
def status_carteira() -> str:
    """Retorna um painel consolidado com a situação atual da carteira.

    Agrega em uma única consulta:
    - Total de processos por status (ativo, suspenso, em_recurso, etc.)
    - Processos com prazo vencendo em até 7 dias (alerta crítico)
    - Processos com prazo vencendo entre 8 e 30 dias (alerta de atenção)
    - Resumo financeiro: valor total em aberto e inadimplência

    Não recebe argumentos — sempre retorna o estado atual completo.

    Returns:
        Painel formatado com indicadores da carteira, pronto para
        ser lido pelo LLM e transformado em resposta em linguagem natural.
    """
    log.info("status_carteira | consultando painel completo")

    hoje = date.today()
    critico = hoje + timedelta(days=7)
    atencao = hoje + timedelta(days=30)

    sqls = {
        "por_status": """
            SELECT status, COUNT(*) AS total
            FROM processos
            GROUP BY status
            ORDER BY total DESC
        """,
        "por_tipo": """
            SELECT tipo, COUNT(*) AS total
            FROM processos
            WHERE status NOT IN ('encerrado', 'acordo')
            GROUP BY tipo
            ORDER BY total DESC
        """,
        "prazos_criticos": """
            SELECT
                p.numero_processo,
                p.tipo,
                p.prazo_proximo,
                c.nome AS cliente,
                a.nome AS advogado,
                (p.prazo_proximo - CURRENT_DATE) AS dias_restantes
            FROM processos p
            LEFT JOIN clientes c ON c.id_cliente = p.cliente_id
            LEFT JOIN advogados a ON a.id_advogado = p.advogado_id
            WHERE
                p.prazo_proximo IS NOT NULL
                AND p.prazo_proximo BETWEEN :hoje AND :critico
                AND p.status NOT IN ('encerrado', 'acordo')
            ORDER BY p.prazo_proximo ASC
        """,
        "prazos_atencao": """
            SELECT COUNT(*) AS total
            FROM processos
            WHERE
                prazo_proximo IS NOT NULL
                AND prazo_proximo BETWEEN :critico_mais_1 AND :atencao
                AND status NOT IN ('encerrado', 'acordo')
        """,
        "financeiro": """
            SELECT
                status_pagamento,
                COUNT(*) AS quantidade,
                SUM(valor_total_contratado) AS total_contratado,
                SUM(valor_em_aberto) AS total_em_aberto
            FROM honorarios
            GROUP BY status_pagamento
            ORDER BY status_pagamento
        """,
    }

    try:
        with SessionLocal() as session:
            por_status = session.execute(text(sqls["por_status"])).fetchall()
            por_tipo = session.execute(text(sqls["por_tipo"])).fetchall()
            prazos_criticos = session.execute(
                text(sqls["prazos_criticos"]), {"hoje": hoje, "critico": critico}
            ).fetchall()
            prazos_atencao = session.execute(
                text(sqls["prazos_atencao"]),
                {"critico_mais_1": critico + timedelta(days=1), "atencao": atencao},
            ).fetchone()
            financeiro = session.execute(text(sqls["financeiro"])).fetchall()
    except Exception as exc:
        log.error("Erro ao gerar painel da carteira: %s", exc)
        return f"Erro ao acessar o banco de dados: {exc}"

    linhas: list[str] = [
        "=" * 60,
        f"PAINEL DA CARTEIRA — {hoje.strftime('%d/%m/%Y')}",
        "=" * 60,
        "",
    ]

    total_processos = sum(r.total for r in por_status)
    linhas.append(f"📁 PROCESSOS ({total_processos} total)")
    linhas.append("─" * 40)
    icones_status = {
        "ativo": "🟢", "suspenso": "🔵", "em_recurso": "🟠",
        "encerrado": "⚫", "acordo": "✅",
    }
    for r in por_status:
        icone = icones_status.get(r.status or "", "•")
        linhas.append(f"  {icone} {r.status or 'N/A':<15} {r.total:>4} processo(s)")
    linhas.append("")

    linhas.append("⚖️  PROCESSOS ATIVOS POR TIPO")
    linhas.append("─" * 40)
    for r in por_tipo:
        linhas.append(f"  • {r.tipo or 'N/A':<18} {r.total:>4} processo(s)")
    linhas.append("")

    linhas.append("⏰ ALERTAS DE PRAZO")
    linhas.append("─" * 40)

    if prazos_criticos:
        linhas.append(f"  🔴 CRÍTICO (até 7 dias): {len(prazos_criticos)} processo(s)")
        for r in prazos_criticos:
            linhas.append(
                f"     → {r.numero_processo} | {r.cliente or 'N/A'} | "
                f"Prazo: {r.prazo_proximo} ({r.dias_restantes}d)"
            )
    else:
        linhas.append("  🔴 CRÍTICO (até 7 dias): nenhum")

    qtd_atencao = prazos_atencao.total if prazos_atencao else 0
    linhas.append(f"  🟡 ATENÇÃO (8–30 dias): {qtd_atencao} processo(s)")
    linhas.append("")

    linhas.append("💰 HONORÁRIOS")
    linhas.append("─" * 40)
    total_geral = sum(r.total_contratado or 0 for r in financeiro)
    total_aberto = sum(r.total_em_aberto or 0 for r in financeiro)
    icones_pag = {"atrasado": "🔴", "em_dia": "🟡", "quitado": "✅"}

    for r in financeiro:
        icone = icones_pag.get(r.status_pagamento or "", "⚪")
        linhas.append(
            f"  {icone} {r.status_pagamento or 'indefinido':<12} "
            f"{r.quantidade:>3} processo(s) | "
            f"Em aberto: R$ {r.total_em_aberto or 0:,.2f}"
        )

    linhas.append(f"\n  Total contratado : R$ {total_geral:,.2f}")
    linhas.append(f"  Total em aberto  : R$ {total_aberto:,.2f}")
    linhas.append("")
    linhas.append("=" * 60)

    return "\n".join(linhas)