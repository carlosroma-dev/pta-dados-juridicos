from __future__ import annotations

import logging
import os

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import text

from fase1_engenharia.db.database import SessionLocal

log = logging.getLogger(__name__)

_llm = ChatOpenAI(
    model="gpt-5.4-mini-2026-03-17",
    temperature=0,
    api_key=os.getenv("OPENAI_API_KEY"),
)

_SCHEMA = """
Banco PostgreSQL. Use os nomes de coluna EXATAMENTE como estão:

clientes      → id_cliente, nome, "CPF", email, contato, data_cadastro, cidade
advogados     → id_advogado, nome
processos     → id_processos, numero_processo (PK), tipo, cliente_id, advogado_id, status, fase, prazo_proximo, valor_causa, data_abertura, vara, observacoes
honorarios    → id_honorarios, processo_numero, status_pagamento, data_contrato, data_vencimento, numero_parcelas, parcelas_pagas, valor_total_contratado, valor_pago, valor_em_aberto, forma_pagamento, honorario_exito, percentual_exito
movimentacoes → id_movimentacao, processo_numero, tipo_ato, data_evento, descricao, prazo_gerado, concluido
processo_advogados → numero_processo, advogado_id  (tabela N:N processos↔advogados)

ATENÇÃO: a coluna CPF se chama "CPF" (maiúsculo) — use SEMPRE aspas duplas: "CPF"

MAPEAMENTO OBRIGATÓRIO de status_pagamento (use EXATAMENTE esses valores):
- "atrasado"  → pagamento atrasado / inadimplente / em atraso
- "em_dia"    → pagamento em dia / não vencido / pendente mas dentro do prazo
- "quitado"   → pago integralmente
- "em aberto" no contexto financeiro = status_pagamento IN ('atrasado', 'em_dia')
"""

_EXEMPLOS = """
Pergunta: Qual o CPF da Ana Lima?
SQL: SELECT id_cliente, nome, "CPF" FROM clientes WHERE nome ILIKE '%Ana Lima%' LIMIT 50

Pergunta: Qual o contato da Fernanda Costa?
SQL: SELECT id_cliente, nome, contato FROM clientes WHERE nome ILIKE '%Fernanda Costa%' LIMIT 50

Pergunta: Qual o email do João Silva?
SQL: SELECT id_cliente, nome, email FROM clientes WHERE nome ILIKE '%João Silva%' LIMIT 50

Pergunta: Quais dados da cliente Maria Oliveira?
SQL: SELECT id_cliente, nome, "CPF", email, contato, cidade FROM clientes WHERE nome ILIKE '%Maria Oliveira%' LIMIT 50

Pergunta: Qual o id do cliente com CPF 570.649.227-58?
SQL: SELECT id_cliente, nome, "CPF" FROM clientes WHERE "CPF" = '570.649.227-58' LIMIT 50

Pergunta: Qual advogado tem mais processos ativos?
SQL: SELECT a.nome, COUNT(*) AS total FROM advogados a JOIN processo_advogados pa ON pa.advogado_id = a.id_advogado JOIN processos p ON p.numero_processo = pa.numero_processo WHERE p.status = 'ativo' GROUP BY a.nome ORDER BY total DESC LIMIT 10

Pergunta: Liste os processos abertos nos últimos 30 dias.
SQL: SELECT numero_processo, tipo, status, data_abertura FROM processos WHERE data_abertura >= NOW() - INTERVAL '30 days' ORDER BY data_abertura DESC LIMIT 50

Pergunta: Quem são os advogados da Fernanda Costa?
SQL: SELECT c.nome AS cliente, c."CPF", p.numero_processo, a.nome AS advogado FROM clientes c JOIN processos p ON c.id_cliente = p.cliente_id JOIN processo_advogados pa ON p.numero_processo = pa.numero_processo JOIN advogados a ON pa.advogado_id = a.id_advogado WHERE c.nome ILIKE '%Fernanda Costa%' LIMIT 50

Pergunta: Qual o status do processo do João Silva e valor contratado?
SQL: SELECT c.nome, p.numero_processo, p.status, h.valor_total_contratado FROM clientes c JOIN processos p ON c.id_cliente = p.cliente_id JOIN honorarios h ON p.numero_processo = h.processo_numero WHERE c.nome ILIKE '%João Silva%' LIMIT 50
"""
_SYSTEM_SQL = f"""Você é um gerador de SQL para PostgreSQL.
Dado o schema e os exemplos abaixo, gere APENAS a query SQL SELECT para responder a pergunta.
Sem explicações, sem markdown, sem ponto e vírgula no final.

REGRAS:
1. SEMPRE use "CPF" com aspas duplas quando referenciar essa coluna.
2. SEMPRE filtre pelo nome usando ILIKE quando a pergunta mencionar uma pessoa.
3. SEMPRE inclua as colunas id_cliente e nome nas queries de clientes.
4. Se a pergunta envolver CPF, inclua também "CPF" no SELECT.
5. OBRIGATÓRIO (CRÍTICO): Sempre que a consulta buscar processos, honorários ou advogados vinculados a um cliente, você DEVE incluir a coluna `numero_processo` no SELECT. O sistema necessita deste CNJ para funcionar.
6. ROTA DE JOIN ADVOGADOS: Para relacionar clientes e advogados, SEMPRE faça o caminho completo: clientes (id_cliente) -> processos (cliente_id) -> processo_advogados (numero_processo) -> advogados (id_advogado).
7. Selecione as colunas necessárias para responder a pergunta.
8. LIMIT 50 em toda query.
9. Nunca gere INSERT, UPDATE, DELETE, DROP, ALTER ou TRUNCATE.

SCHEMA:
{_SCHEMA}

EXEMPLOS (siga este padrão):
{_EXEMPLOS}
"""


@tool
def consultar_banco(pergunta: str) -> str:
    """Responde perguntas livres sobre os dados do escritório gerando SQL dinamicamente.

    Use para perguntas que não se encaixam nas ferramentas específicas:
    buscar CPF/contato/email de cliente pelo nome, ranking de advogados,
    listar processos por tipo ou data, dados específicos de qualquer registro.

    Args:
        pergunta: Pergunta em linguagem natural sobre os dados do escritório.

    Returns:
        Resultado da consulta formatado em texto, ou mensagem de erro.
    """
    log.info("consultar_banco | pergunta: %s", pergunta)

    resposta_sql = _llm.invoke([
        SystemMessage(content=_SYSTEM_SQL),
        HumanMessage(content=f"Pergunta: {pergunta}\nSQL:"),
    ])
    sql = resposta_sql.content.strip().strip(";").strip()

    # Remove blocos markdown caso o LLM insira mesmo assim
    if "```" in sql:
        sql = "\n".join(
            line for line in sql.splitlines()
            if not line.strip().startswith("```")
        ).strip()

    log.info("SQL gerado: %s", sql)

    # Valida que não é DDL/DML destrutivo
    sql_upper = sql.upper()
    for palavra in ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER"):
        if palavra in sql_upper:
            log.warning("SQL recusado: '%s'", palavra)
            return "Consulta não permitida: apenas SELECT é autorizado."

    try:
        with SessionLocal() as session:
            result = session.execute(text(sql))
            colunas = list(result.keys())
            rows = result.fetchall()
    except Exception as exc:
        log.error("Erro ao executar SQL: %s | SQL: %s", exc, sql)
        return f"Erro ao executar a consulta: {exc}"

    if not rows:
        return "Nenhum resultado encontrado para essa consulta."

    linhas = [" | ".join(colunas)]
    linhas.append("─" * 60)
    for row in rows:
        linhas.append(" | ".join(str(v) if v is not None else "N/A" for v in row))

    return "\n".join(linhas)