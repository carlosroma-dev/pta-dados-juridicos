"""Nó LangGraph: gerar_resposta

Recebe os chunks recuperados pelo retriever e usa o LLM (Groq) para
produzir uma resposta fundamentada SOMENTE no contexto fornecido.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from fase2_agente.grafo.estado import AgentState

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Instrução ao modelo — simples e direta
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Você é um assistente jurídico.
Responda SOMENTE com base no contexto fornecido.
Se a resposta não estiver no contexto, diga: "Não encontrei essa informação nos documentos."

REGRA OBRIGATÓRIA: Você deve indicar explicitamente de onde tirou a informação.
- Se a informação veio de um PDF, cite: "(Fonte: nome_do_arquivo.pdf)".
- Se veio do banco, cite: "(Fonte: Banco de Dados Relacional)".

Seja objetivo e claro.\
"""

# ---------------------------------------------------------------------------
# Lazy loading — o LLM só é criado na primeira chamada, não no import.
# Mesmo padrão usado em fase2_agente/rag/retriever.py (_get_modelo).
# ---------------------------------------------------------------------------

_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        model = os.getenv("LLM_MODEL", "gpt-5.4-mini-2026-03-17")
        log.info("Inicializando LLM (%s)...", model)
        _llm = ChatOpenAI(
            model=model,
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        log.info("LLM pronto!")
    return _llm


# ---------------------------------------------------------------------------
# Nó
# ---------------------------------------------------------------------------


def gerar_resposta(state: AgentState) -> AgentState:
    """Gera a resposta final a partir dos chunks recuperados.

    Fluxo:
        1. Concatena o conteúdo dos chunks num bloco de contexto.
        2. Monta as mensagens (system + human) para o LLM.
        3. Chama o LLM e retorna o estado atualizado com a resposta.
    """
    contexto = "\n\n---\n\n".join(
        doc.page_content for doc in state["chunks_recuperados"]
    )

    mensagens = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Contexto:\n{contexto}\n\nPergunta: {state['pergunta']}"),
    ]

    resposta = _get_llm().invoke(mensagens)

    # {**state, ...} copia tudo do estado anterior e sobrescreve só "resposta"
    return {**state, "resposta": resposta.content}