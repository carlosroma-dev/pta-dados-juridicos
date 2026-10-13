"""Ferramenta: verificar_prazos

Lista processos com prazo próximo dentro de uma janela de dias configurável,
consultando diretamente o banco relacional.

Dor resolvida: perder prazo processual é uma das falhas mais graves que um
escritório de advocacia pode cometer — gera nulidade, multa e até
responsabilidade civil do advogado. O escritório relatou dificuldade em
acompanhar os prazos de uma carteira de 200+ processos ativos.
Essa ferramenta entrega a lista de alerta em segundos, com contexto suficiente
para o advogado agir imediatamente.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from langchain_core.tools import tool
from sqlalchemy import text

from fase1_engenharia.db.database import SessionLocal

log = logging.getLogger(__name__)


@tool
def verificar_prazos(dias: Optional[int] = 7, tipo: Optional[str] = None) -> str:
    """Lista processos com prazo vencendo nos próximos N dias.

    Consulta a tabela `processos` e retorna aqueles cujo `prazo_proximo`
    cai dentro da janela [hoje, hoje + dias]. Útil para montar a agenda
    diária de urgências do escritório.

    Args:
        dias: Janela de alerta em dias corridos (padrão 7, máximo 90).
              Exemplo: 7 → mostra tudo que vence até a próxima semana.
        tipo: Filtro opcional pelo tipo de processo.
              Valores aceitos: "civel", "trabalhista", "criminal", "tributario".
              Se omitido, retorna todos os tipos.

    Returns:
        Tabela formatada com os processos em alerta, ou mensagem indicando
        que não há prazos no período.
    """
    if dias is None:
        dias = 7
    dias = max(1, min(dias, 90))

    hoje = date.today()
    limite = hoje + timedelta(days=dias)

    log.info(
        "verificar_prazos | janela=%d dias (%s → %s) tipo=%s",
        dias, hoje, limite, tipo or "todos",
    )

    sql_base = """
        SELECT
            p.numero_processo,
            p.tipo,
            p.status,
            p.fase,
            p.prazo_proximo,
            p.vara,
            c.nome AS cliente,
            a.nome AS advogado,
            (p.prazo_proximo - CURRENT_DATE) AS dias_restantes
        FROM processos p
        LEFT JOIN clientes c ON c.id_cliente = p.cliente_id
        LEFT JOIN advogados a ON a.id_advogado = p.advogado_id
        WHERE
            p.prazo_proximo IS NOT NULL
            AND p.prazo_proximo BETWEEN :hoje AND :limite
            AND p.status NOT IN ('encerrado', 'acordo')
    """

    params: dict = {"hoje": hoje, "limite": limite}

    if tipo:
        sql_base += " AND LOWER(p.tipo) = :tipo"
        params["tipo"] = tipo.lower()

    sql_base += " ORDER BY p.prazo_proximo ASC"

    try:
        with SessionLocal() as session:
            rows = session.execute(text(sql_base), params).fetchall()
    except Exception as exc:
        log.error("Erro ao consultar prazos: %s", exc)
        return f"Erro ao acessar o banco de dados: {exc}"

    if not rows:
        filtro_msg = f" ({tipo})" if tipo else ""
        return (
            f"Nenhum prazo{filtro_msg} vencendo nos próximos {dias} dia(s). "
            f"Janela: {hoje} → {limite}."
        )

    urgentes = [r for r in rows if r.dias_restantes is not None and r.dias_restantes <= 3]
    outros = [r for r in rows if r not in urgentes]

    linhas: list[str] = [
        f"⚠️  {len(rows)} processo(s) com prazo nos próximos {dias} dia(s) "
        f"(de {hoje} até {limite}):\n"
    ]

    def formatar_bloco(titulo: str, registros: list) -> None:
        if not registros:
            return
        linhas.append(f"{titulo}")
        linhas.append("─" * 60)
        for r in registros:
            dias_restantes = r.dias_restantes if r.dias_restantes is not None else "?"
            linhas.append(
                f"• Processo : {r.numero_processo}\n"
                f"  Cliente  : {r.cliente or 'N/A'}\n"
                f"  Advogado : {r.advogado or 'N/A'}\n"
                f"  Tipo     : {r.tipo or 'N/A'} | Status: {r.status or 'N/A'}\n"
                f"  Fase     : {r.fase or 'N/A'} | Vara: {r.vara or 'N/A'}\n"
                f"  Prazo    : {r.prazo_proximo} ({dias_restantes} dia(s) restante(s))\n"
            )
        linhas.append("")

    if urgentes:
        formatar_bloco("🔴 URGENTE — vence em até 3 dias", urgentes)
    if outros:
        formatar_bloco("🟡 ATENÇÃO — vence em breve", outros)

    return "\n".join(linhas)