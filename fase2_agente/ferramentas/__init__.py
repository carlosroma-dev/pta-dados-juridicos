"""Ferramentas do agente jurídico (Fase 2).

Cada ferramenta tem uma responsabilidade única e é registrada
como LangChain Tool para ser invocada pelo grafo LangGraph.
"""

from fase2_agente.ferramentas.buscar_documento import buscar_documento
from fase2_agente.ferramentas.verificar_prazos import verificar_prazos
from fase2_agente.ferramentas.checar_honorarios import checar_honorarios
from fase2_agente.ferramentas.status_carteira import status_carteira
from fase2_agente.ferramentas.consultar_banco import consultar_banco

__all__ = [
    "buscar_documento",
    "verificar_prazos",
    "checar_honorarios",
    "status_carteira",
    "consultar_banco",
]