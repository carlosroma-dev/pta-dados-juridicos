from typing import TypedDict, List

from langchain_core.documents import Document


class AgentState(TypedDict):
    """Estado que circula entre os nós do grafo LangGraph.

    Cada nó recebe esse dicionário, lê o que precisa,
    e devolve uma versão atualizada.
    """

    pergunta: str                      # Pergunta original do usuário
    tipo_consulta: str                 # "vetorial" | "relacional" | "reformular"
    chunks_recuperados: List[Document] # Chunks retornados pelo retriever (pgvector)
    confianca_classificacao: str         # "alta" | "baixa"
    historico: List[dict]             # Histórico de ações e respostas do agente
    resposta: str                      # Resposta gerada pelo LLM
