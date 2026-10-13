"""Ferramenta: buscar_documento

Busca trechos de documentos jurídicos (contratos, petições, acordos,
intimações, etc.) usando similaridade semântica via pgvector.

Dor resolvida: advogados perdem tempo vasculhando PDFs manualmente para
encontrar uma cláusula, um valor ou uma decisão específica.
Com essa ferramenta, a pergunta em linguagem natural retorna os trechos
mais relevantes do acervo em segundos.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from langchain_core.tools import tool

from fase2_agente.rag.retriever import PgVectorRetriever

log = logging.getLogger(__name__)


@tool
def buscar_documento(
    pergunta: str,
    top_k: Optional[int] = 5,
    processos: Optional[List[str]] = None,
) -> str:
    """Busca trechos de documentos jurídicos por similaridade semântica.

    Use esta ferramenta quando a pergunta for sobre o *conteúdo* de documentos:
    contratos de honorários, petições iniciais, acordos extrajudiciais,
    intimações, notificações ou recursos. Retorna os trechos mais relevantes
    encontrados no acervo, com o número do processo e o tipo de documento de
    onde cada trecho veio.

    Args:
        pergunta:  Pergunta ou trecho que você quer encontrar nos documentos.
                   Pode ser em linguagem natural.
                   Exemplo: "cláusula de rescisão do contrato da Ana Lima"
        top_k:     Quantidade de trechos a retornar (padrão 5, máximo 20).
        processos: Lista opcional de números de processo (CNJ) para restringir
                   a busca apenas aos documentos desses processos. Usada pela
                   rota híbrida para cruzar o resultado relacional com os
                   documentos. None/vazio → busca em todo o acervo (padrão).

    Returns:
        String formatada com um marcador [FONTE: ...] e os trechos encontrados,
        ou mensagem de aviso caso nenhum chunk seja recuperado.
    """
    if top_k is None:
        top_k = 5
    top_k = max(1, min(top_k, 20))  # garante intervalo [1, 20]

    log.info(
        "buscar_documento | pergunta='%s' top_k=%d processos=%s",
        pergunta, top_k, processos or "—",
    )

    try:
        # Retriever é leve (o modelo de embedding é um singleton global no
        # retriever.py), então instanciamos a cada chamada — assim o filtro
        # por processo nunca "vaza" de uma chamada para outra via cache.
        retriever = PgVectorRetriever(k=top_k, processos_filtro=processos)
        documentos = retriever.invoke(pergunta)
    except Exception as exc:
        log.error("Erro ao buscar documentos: %s", exc)
        return f"Erro ao acessar o acervo de documentos: {exc}"

    if not documentos:
        return (
            "Nenhum trecho relevante encontrado para essa pergunta. "
            "Tente reformular ou usar termos mais específicos."
        )

    # Marcador de fonte no mesmo padrão da rota relacional ([FONTE: ...]),
    # para o nó gerar_resposta conseguir citar a origem. Lista os arquivos
    # distintos de onde vieram os trechos, preservando a ordem de relevância.
    fontes: list[str] = []
    for doc in documentos:
        arquivo = doc.metadata.get("documento_fonte")
        if arquivo and arquivo not in fontes:
            fontes.append(arquivo)
    marcador_fonte = f"[FONTE: {', '.join(fontes) if fontes else 'documentos'}]"

    linhas: list[str] = [
        marcador_fonte,
        "",
        f"Encontrei {len(documentos)} trecho(s) relevante(s):\n",
    ]
    for i, doc in enumerate(documentos, start=1):
        meta = doc.metadata
        linhas.append(
            f"── Trecho {i} ──────────────────────────────────────────\n"
            f"Documento : {meta.get('tipo_documento', 'N/A')}\n"
            f"Processo  : {meta.get('processo_numero', 'N/A')}\n"
            f"Arquivo   : {meta.get('documento_fonte', 'N/A')}\n"
            f"Relevância: {1 - meta.get('distancia', 1):.1%}\n"
            f"\n{doc.page_content.strip()}\n"
        )

    return "\n".join(linhas)