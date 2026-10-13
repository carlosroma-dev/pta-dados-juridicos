import os
import logging
from datetime import date, datetime
from typing import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from sqlalchemy import text
from fase1_engenharia.db.database import SessionLocal
from fase2_agente.automacoes.email_sender import enviar_email

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
log = logging.getLogger(__name__)

EMAILS_ADVOGADOS = {
    "Dr. Barros":      os.getenv("EMAIL_DR_BARROS",      "barros@escritorio.com"),
    "Dra. Cavalcante": os.getenv("EMAIL_DRA_CAVALCANTE", "cavalcante@escritorio.com"),
    "Dr. Melo":        os.getenv("EMAIL_DR_MELO",        "melo@escritorio.com"),
    "Dra. Fontes":     os.getenv("EMAIL_DRA_FONTES",     "fontes@escritorio.com"),
}

_llm = ChatOpenAI(
    model=os.getenv("LLM_MODEL", "gpt-5.4-mini-2026-03-17"),
    temperature=0,
    api_key=os.getenv("OPENAI_API_KEY"),
)


# ── Estado ────────────────────────────────────────────────────────────────────
class PrazosState(TypedDict):
    n_dias:           int
    processos:        list[dict]
    grupos:           dict[str, list]
    emails_enviados:  int
    emails_advogados: dict   # override do .env quando preenchido


# ── Helpers ───────────────────────────────────────────────────────────────────
def _formatar_valor(valor) -> str:
    if valor is None:
        return "Não informado"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _urgencia(dias: int) -> tuple[str, str, str]:
    """Retorna (label, cor_fundo, cor_texto) conforme urgência."""
    if dias <= 3:
        return "🔴 CRÍTICO",  "#FEE2E2", "#991B1B"
    if dias <= 7:
        return "🟡 ATENÇÃO",  "#FEF9C3", "#854D0E"
    return     "🟢 AVISO",    "#DCFCE7", "#166534"


# ── Template HTML ─────────────────────────────────────────────────────────────
def _linha_processo(p: dict) -> str:
    dias = p["dias_restantes"]
    _, bg, fg = _urgencia(dias)
    dias_txt = f"{dias} dia{'s' if dias != 1 else ''}"

    resumo_html = ""
    if p.get("resumo_llm"):
        resumo_html = f"""
    <tr>
      <td colspan="6" style="padding: 4px 8px 12px; background: #F8F7F3;
                              font-size: 12px; color: #4B4A42; font-style: italic;
                              border-bottom: 2px solid #E8E6DD;">
        💡 {p['resumo_llm']}
      </td>
    </tr>"""

    return f"""
    <tr style="border-bottom: 1px solid #E8E6DD;">
      <td style="padding: 10px 8px; font-size: 13px; color: #2B2B28;">
        <strong style="font-family: monospace; font-size: 12px;">{p['numero_processo']}</strong><br>
        <span style="color: #6B6A62; font-size: 12px;">{p['tipo'] or '—'} · {p['fase'] or '—'}</span>
      </td>
      <td style="padding: 10px 8px; font-size: 13px; color: #2B2B28;">{p['nome_cliente'] or '—'}</td>
      <td style="padding: 10px 8px; font-size: 13px; color: #2B2B28;">{p['vara'] or '—'}</td>
      <td style="padding: 10px 8px; font-size: 13px; color: #2B2B28;">
        {p['prazo_proximo']}<br>
        <span style="background:{bg}; color:{fg}; padding: 2px 6px; border-radius: 4px;
                     font-size: 11px; font-weight: bold;">{dias_txt}</span>
      </td>
      <td style="padding: 10px 8px; font-size: 13px; color: #2B2B28;">
        {_formatar_valor(p['valor_causa'])}<br>
        <span style="font-size: 11px; color: #6B6A62;">
          Hon.: {p['status_honorarios'] or '—'} · Em aberto: {_formatar_valor(p['valor_em_aberto'])}
        </span>
      </td>
      <td style="padding: 10px 8px; font-size: 12px; color: #6B6A62; max-width: 180px;">
        {p['ultima_movimentacao'] or '—'}
      </td>
    </tr>{resumo_html}"""


def _secao_urgencia(label: str, bg: str, fg: str, processos: list[dict]) -> str:
    if not processos:
        return ""
    linhas = "".join(_linha_processo(p) for p in processos)
    return f"""
    <div style="margin: 0 32px 20px;">
      <div style="background:{bg}; color:{fg}; padding: 8px 12px; border-radius: 6px 6px 0 0;
                  font-size: 13px; font-weight: bold;">{label} — {len(processos)} processo(s)</div>
      <table style="width: 100%; border-collapse: collapse; border: 1px solid #E8E6DD;
                    border-top: none; border-radius: 0 0 6px 6px; overflow: hidden;">
        <thead>
          <tr style="background: #FAF9F5;">
            <th style="padding: 8px; font-size: 12px; color: #6B6A62; text-align: left;">Processo / Tipo</th>
            <th style="padding: 8px; font-size: 12px; color: #6B6A62; text-align: left;">Cliente</th>
            <th style="padding: 8px; font-size: 12px; color: #6B6A62; text-align: left;">Vara</th>
            <th style="padding: 8px; font-size: 12px; color: #6B6A62; text-align: left;">Prazo</th>
            <th style="padding: 8px; font-size: 12px; color: #6B6A62; text-align: left;">Financeiro</th>
            <th style="padding: 8px; font-size: 12px; color: #6B6A62; text-align: left;">Última movimentação</th>
          </tr>
        </thead>
        <tbody>{linhas}</tbody>
      </table>
    </div>"""


def _montar_html(advogado: str, processos: list[dict], n_dias: int) -> str:
    hoje = datetime.now().strftime("%d/%m/%Y")
    total = len(processos)

    criticos = [p for p in processos if p["dias_restantes"] <= 3]
    atencao  = [p for p in processos if 4 <= p["dias_restantes"] <= 7]
    avisos   = [p for p in processos if p["dias_restantes"] >= 8]

    criticos_msg = ""
    if criticos:
        n = len(criticos)
        criticos_msg = (
            f'<br><span style="color:#991B1B; font-weight:bold;">'
            f'⚠️ {n} processo(s) com prazo crítico (≤ 3 dias)!</span>'
        )

    secoes = (
        _secao_urgencia("🔴 CRÍTICO (≤ 3 dias)",  "#FEE2E2", "#991B1B", criticos) +
        _secao_urgencia("🟡 ATENÇÃO (4–7 dias)",   "#FEF9C3", "#854D0E", atencao)  +
        _secao_urgencia("🟢 AVISO (8+ dias)",       "#DCFCE7", "#166534", avisos)
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; background: #f5f5f0; padding: 20px; margin: 0;">
<div style="max-width: 760px; margin: 0 auto; background: white; border-radius: 8px;
            overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">

  <!-- Cabeçalho -->
  <div style="background: #2B2B28; padding: 24px 32px;">
    <h1 style="color: white; margin: 0; font-size: 20px; font-family: Georgia, serif;">
      ⚖️ Escritório Cavalcante &amp; Melo
    </h1>
    <p style="color: #9A998F; margin: 4px 0 0; font-size: 13px;">
      Alerta de Prazos Processuais — {hoje}
    </p>
  </div>

  <!-- Saudação -->
  <div style="padding: 24px 32px 16px; border-bottom: 1px solid #E8E6DD;">
    <p style="font-size: 15px; color: #2B2B28; margin: 0;">
      Olá, <strong>{advogado}</strong>!
    </p>
    <p style="font-size: 14px; color: #6B6A62; margin: 8px 0 0;">
      Você tem <strong>{total} processo(s)</strong> com prazo
      nos próximos {n_dias} dias.{criticos_msg}
    </p>
  </div>

  <!-- Seções por urgência -->
  <div style="padding: 20px 0 8px;">
    {secoes}
  </div>

  <!-- Rodapé -->
  <div style="padding: 16px 32px; background: #FAF9F5; border-top: 1px solid #E8E6DD;">
    <p style="font-size: 12px; color: #9A998F; margin: 0; text-align: center;">
      Sistema PTA Dados — Escritório Mezzalira &nbsp;·&nbsp;
      Este é um email automático, não responda.
    </p>
  </div>

</div>
</body></html>"""


# ── Nós ───────────────────────────────────────────────────────────────────────
def buscar_prazos(estado: PrazosState) -> PrazosState:
    """Busca processos com prazo próximo, com dados de cliente, vara, honorários e movimentação."""
    log.info("Nó: buscar_prazos (próximos %d dias)", estado["n_dias"])

    sql = text("""
        SELECT
            p.numero_processo,
            p.prazo_proximo,
            p.status,
            p.tipo,
            p.fase,
            p.vara,
            p.valor_causa,
            c.nome           AS nome_cliente,
            a.nome           AS advogado_responsavel,
            h.status_pagamento AS status_honorarios,
            h.valor_em_aberto,
            m.descricao      AS ultima_movimentacao
        FROM processos p
        LEFT JOIN clientes c
               ON c.id_cliente = p.cliente_id
        LEFT JOIN processo_advogados pa
               ON pa.numero_processo = p.numero_processo
        LEFT JOIN advogados a
               ON a.id_advogado = pa.advogado_id
        LEFT JOIN LATERAL (
            SELECT status_pagamento, valor_em_aberto
            FROM honorarios
            WHERE processo_numero = p.numero_processo
            ORDER BY data_vencimento DESC
            LIMIT 1
        ) h ON true
        LEFT JOIN LATERAL (
            SELECT descricao
            FROM movimentacoes
            WHERE processo_numero = p.numero_processo
            ORDER BY data_evento DESC
            LIMIT 1
        ) m ON true
        WHERE p.prazo_proximo BETWEEN NOW() AND NOW() + (:n_dias * INTERVAL '1 day')
          AND p.status NOT IN ('encerrado', 'acordo', 'suspenso', 'arquivado', 'em_recurso')
        ORDER BY p.prazo_proximo ASC
    """)

    hoje = date.today()
    try:
        with SessionLocal() as session:
            resultado = session.execute(sql, {"n_dias": estado["n_dias"]}).fetchall()

        processos = [
            {
                "numero_processo":    row.numero_processo,
                "prazo_proximo":      str(row.prazo_proximo),
                "dias_restantes":     (row.prazo_proximo - hoje).days,
                "status":             row.status,
                "tipo":               row.tipo,
                "fase":               row.fase,
                "vara":               row.vara,
                "valor_causa":        row.valor_causa,
                "nome_cliente":       row.nome_cliente,
                "advogado_responsavel": row.advogado_responsavel,
                "status_honorarios":  row.status_honorarios,
                "valor_em_aberto":    row.valor_em_aberto,
                "ultima_movimentacao": row.ultima_movimentacao,
                "resumo_llm":           "", 
            }
            for row in resultado
        ]
        log.info("%d processos com prazo próximo encontrados.", len(processos))

    except Exception as e:
        log.error("Erro ao buscar prazos: %s", e)
        processos = []

    return {**estado, "processos": processos}

def resumir_processos(estado: PrazosState) -> PrazosState:
    """Gera um resumo executivo de uma frase por processo via LLM (chamada em lote)."""
    log.info("Nó: resumir_processos (%d processo(s))", len(estado["processos"]))

    if not estado["processos"]:
        return estado

    # Monta contexto de todos os processos em uma única mensagem
    blocos = []
    for i, p in enumerate(estado["processos"], start=1):
        blocos.append(
            f"Processo {i}: {p['numero_processo']}\n"
            f"  Cliente: {p['nome_cliente'] or '—'}\n"
            f"  Tipo: {p['tipo'] or '—'} | Fase: {p['fase'] or '—'}\n"
            f"  Vara: {p['vara'] or '—'}\n"
            f"  Prazo: {p['prazo_proximo']} ({p['dias_restantes']} dia(s))\n"
            f"  Valor da causa: {_formatar_valor(p['valor_causa'])}\n"
            f"  Honorários: {p['status_honorarios'] or '—'} | "
            f"Em aberto: {_formatar_valor(p['valor_em_aberto'])}\n"
            f"  Última movimentação: {p['ultima_movimentacao'] or '—'}"
        )

    try:
        resposta = _llm.invoke([
            SystemMessage(content=(
                "Você é um assistente jurídico. Para cada processo listado, gere UM resumo "
                "executivo de UMA frase (máximo 30 palavras) destacando: do que se trata o caso, "
                "o momento processual atual e o que o advogado precisa saber agora.\n"
                "Responda APENAS neste formato, sem texto adicional:\n"
                "Processo 1: [resumo]\n"
                "Processo 2: [resumo]\n"
                "..."
            )),
            HumanMessage(content="\n\n---\n\n".join(blocos)),
        ])

        # Faz o parse linha por linha
        resumos: dict[int, str] = {}
        for linha in resposta.content.strip().splitlines():
            if linha.startswith("Processo "):
                partes = linha.split(":", 1)
                if len(partes) == 2:
                    try:
                        idx = int(partes[0].replace("Processo ", "").strip()) - 1
                        resumos[idx] = partes[1].strip()
                    except ValueError:
                        pass

    except Exception as exc:
        log.warning("Falha ao gerar resumos LLM (%s) — email segue sem resumos.", exc)
        resumos = {}

    processos_atualizados = [
        {**p, "resumo_llm": resumos.get(i, "")}
        for i, p in enumerate(estado["processos"])
    ]

    return {**estado, "processos": processos_atualizados}

def agrupar_por_advogado(estado: PrazosState) -> PrazosState:
    """Agrupa os processos por advogado responsável."""
    log.info("Nó: agrupar_por_advogado")

    grupos: dict[str, list] = {}
    for processo in estado["processos"]:
        advogado = processo["advogado_responsavel"] or "Sem responsável"
        if advogado not in grupos:
            grupos[advogado] = []
        grupos[advogado].append(processo)

    log.info("%d advogados com prazos próximos.", len(grupos))
    return {**estado, "grupos": grupos}


def enviar_emails(estado: PrazosState) -> PrazosState:
    log.info("Nó: enviar_emails")

    emails_mapa = estado.get("emails_advogados") or EMAILS_ADVOGADOS
    emails_enviados = 0

    for advogado, processos in estado["grupos"].items():
        email_dest = emails_mapa.get(advogado, os.getenv("EMAIL_FALLBACK"))
        if not email_dest:
            log.warning("Email não configurado para advogado: %s", advogado)
            continue

        n_dias  = estado["n_dias"]
        assunto = (
            f"⚠️ Alerta de Prazos — {len(processos)} processo(s) "
            f"vencendo em {n_dias} dias"
        )
        html    = _montar_html(advogado, processos, n_dias)

        if enviar_email(email_dest, assunto, html=html):
            emails_enviados += 1

    log.info("%d emails enviados.", emails_enviados)
    return {**estado, "emails_enviados": emails_enviados}


def registrar_log(estado: PrazosState) -> PrazosState:
    log.info(
        "Nó: registrar_log | processos=%d | grupos=%d | emails_enviados=%d",
        len(estado["processos"]),
        len(estado["grupos"]),
        estado["emails_enviados"],
    )
    return estado


# ── Grafo ─────────────────────────────────────────────────────────────────────
def construir_grafo():
    grafo = StateGraph(PrazosState)

    grafo.add_node("buscar_prazos",        buscar_prazos)
    grafo.add_node("resumir_processos",    resumir_processos)
    grafo.add_node("agrupar_por_advogado", agrupar_por_advogado)
    grafo.add_node("enviar_emails",        enviar_emails)
    grafo.add_node("registrar_log",        registrar_log)

    grafo.set_entry_point("buscar_prazos")
    grafo.add_edge("buscar_prazos",        "resumir_processos")
    grafo.add_edge("resumir_processos",    "agrupar_por_advogado")
    grafo.add_edge("buscar_prazos",        "agrupar_por_advogado")
    grafo.add_edge("agrupar_por_advogado", "enviar_emails")
    grafo.add_edge("enviar_emails",        "registrar_log")
    grafo.add_edge("registrar_log",        END)

    return grafo.compile()


app = construir_grafo()


if __name__ == "__main__":
    resultado = app.invoke({
        "n_dias": 7, "processos": [], "grupos": {}, "emails_enviados": 0, "emails_advogados": {},
    })
    print(f"\nResumo: {resultado['emails_enviados']} emails para {len(resultado['grupos'])} advogados.")