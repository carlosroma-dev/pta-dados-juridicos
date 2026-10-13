"""Nó LangGraph: classificar_pergunta

Classifica a pergunta do usuário em quatro categorias:
- "relacional" → consulta SQL no banco (prazos, clientes, honorários)
- "vetorial"   → busca em documentos via pgvector (contratos, acordos, petições)
- "hibrido"    → precisa dos dois: dados estruturados + conteúdo de documentos
- "reformular" → pergunta vaga ou sem contexto suficiente
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from fase2_agente.grafo.estado import AgentState
from fase2_agente.memoria.janela import formatar_historico

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
)
log = logging.getLogger(__name__)


class Classificacao(BaseModel):
    tipo: Literal["vetorial", "relacional", "hibrido", "reformular"]
    confianca: Literal["alta", "baixa"]  


SYSTEM_PROMPT = """\
Você é um classificador de perguntas jurídicas. Sua única tarefa é decidir \
para qual fonte de dados a pergunta deve ser enviada, e avaliar sua confiança.

Quando houver histórico da conversa antes da pergunta, use-o APENAS para resolver
referências (\"ele\", \"esse processo\", \"o contrato dela\"). Classifique sempre
com base na intenção da PERGUNTA ATUAL, não do histórico.

Responda com dois campos:
- tipo: uma das quatro opções abaixo
- confianca: "alta" (categoria inequívoca) ou "baixa" (qualquer dúvida)

---

TIPOS:
- "relacional": pergunta ESTRITAMENTE sobre métricas e dados cadastrais simples do banco (prazos, status, clientes, honorários, pagamentos, CPF, contato, email).
- "vetorial": pergunta sobre o conteúdo de documentos (contratos, petições, acordos, intimações, notificações, laudos, atas).
- "hibrido": pergunta que precisa TANTO de dados do banco QUANTO de conteúdo de documentos. OBRIGATÓRIO PARA: perguntas sobre VÍNCULOS DE REPRESENTAÇÃO (ex: "quem é o advogado de X?", "quais clientes o advogado Y atende?"), pois o banco localiza a pessoa e as procurações/contratos confirmam o vínculo jurídico real.
- "reformular": pergunta vaga, sem sentido ou sem contexto suficiente para saber onde buscar.

---

Exemplos RELACIONAL (dados estruturados — banco):
1. "Quais processos vencem nos próximos 7 dias?"
2. "Liste os clientes com processos ativos"
3. "Quais honorários estão em atraso?"
4. "Qual o valor total dos honorários do processo 0001234?"
5. "Quantos processos estão suspensos?"
6. "Quais processos do cliente João da Silva estão em recurso?"
7. "Mostre os pagamentos quitados do mês"
8. "Qual o prazo mais próximo entre os processos trabalhistas?"
9. "Quantos clientes temos cadastrados em Recife?"
10. "Qual o status do processo 0009876?"
11. "Qual o CPF da Ana Lima?"
12. "Qual o contato da Fernanda Costa?"
13. "Qual advogado tem mais processos ativos numericamente?"
14. "Liste os processos abertos nos últimos 30 dias"
15. "Qual o valor da causa do processo 0007654?"
16. "Como está a carteira de processos do escritório?"
17. "Mostre um panorama geral dos processos"
18. "Como está a distribuição de processos por status?"
19. "Quantos processos temos no total?"
20. "Como está a situação financeira dos honorários?"
21. "Me dá um resumo geral do escritório"
22. "Qual o panorama da carteira?"
23. "Quais honorários estão em aberto ou atrasados?"
24. "Liste os honorários atrasados"
25. "Quais processos têm honorários em atraso?"
26. "Mostre os honorários em aberto"
27. "Quais clientes estão com pagamento atrasado?"
28. "Qual o total de honorários em aberto?"
29. "Quais processos têm prazo nos próximos 7 dias?"
30. "Tem algum prazo vencendo essa semana?"

---

Exemplos VETORIAL (conteúdo de documentos — PDFs):
1. "O que diz o contrato de honorários da Ana Lima?"
2. "Qual a cláusula de rescisão do contrato do processo 0001234?"
3. "Quais são os termos do acordo extrajudicial do processo 0005678?"
4. "O que foi decidido na intimação de sentença do processo 0009876?"
5. "Quais são as obrigações das partes no contrato da Maria Silva?"
6. "O que a petição inicial do processo 0002345 alega?"
7. "Qual o valor acordado no acordo trabalhista do processo 0003456?"
8. "O que diz a notificação enviada a Marcos Carvalho?"
9. "Qual foi o fundamento jurídico da decisão do processo 0001111?"
10. "O que diz o laudo pericial do processo 0006543?"
11. "O que está descrito na ata de audiência do processo 0003333?"
12. "O que foi acordado na petição do processo 0008765?"
13. "O que consta nos contratos e petições cadastrados?"
14. "Mostre o conteúdo dos documentos do escritório"
15. "O que dizem os contratos cadastrados?"

---

Exemplos HÍBRIDO (banco + documentos):
1. "Quais processos da Fernanda Costa vencem essa semana e o que diz o contrato dela?"
2. "Me dá um resumo do processo 0001234 com os dados financeiros e o que diz o acordo"
3. "Qual o status e os honorários do processo 0005678 e o que diz a petição inicial?"
4. "Mostre os processos atrasados da carteira e o que dizem os contratos desses clientes"
5. "Qual o prazo do processo da Ana Lima e o que está no contrato de honorários dela?"
6. "Liste os honorários em aberto e o que diz o acordo extrajudicial de cada um"
7. "Quais processos trabalhistas estão ativos e o que dizem as petições iniciais?"
8. "Quem são os advogados da Fernanda Costa?"
9. "Quem representa a cliente Ana Lima nos processos dela?"
10. "Quais clientes o Dr. Barros atende e quais são as procurações?"
11. "Quem é o advogado responsável pelo processo 0007654?"
12. "Qual é o conteúdo do acordo extrajudicial da Fernanda Costa?"
13. "O que diz o contrato da Ana Lima e quais são os processos dela?"
14. "Quero saber sobre o acordo extrajudicial da Fernanda Costa"

---

Exemplos REFORMULAR (vagos ou sem contexto):
1. "Qual o valor do processo?" (qual processo?)
2. "O que foi decidido?" (em qual documento ou processo?)
3. "Quais são os honorários?" (de quem? de qual processo?)
4. "Me fala sobre o contrato" (qual contrato?)
5. "Qual o prazo?" (de qual processo?)
6. "O que diz o documento?" (qual documento?)
7. "Quem é o advogado?" (de qual processo ou de quem?)
8. "Qual o status?" (de qual processo?)
9. "aaabbbccc"
10. "o que aconteceu?" (sem nenhum contexto)

---

REGRA DE DESEMPATE:
- Pergunta sobre visão geral, panorama, carteira, resumo do escritório → RELACIONAL (use status_carteira)
- Pergunta sobre honorários em aberto, atrasados, em dia, quitados → RELACIONAL
- Pergunta sobre prazos, vencimentos, processos urgentes → RELACIONAL
- Pergunta sobre VÍNCULOS DE REPRESENTAÇÃO → HÍBRIDO
- Menciona tipo de documento E métricas estruturadas → HÍBRIDO
- Menciona APENAS tipo de documento → VETORIAL
- Pergunta EXCLUSIVAMENTE sobre dados de contato simples ou contagens → RELACIONAL
- Pergunta sobre o que diz/consta em um documento específico → VETORIAL
- Sem contexto suficiente → REFORMULAR

---

CONFIANÇA DA CLASSIFICAÇÃO:                                        
Use confianca="baixa" quando houver QUALQUER uma destas situações:
- A pergunta mistura dados financeiros (valores, pagamentos) sem deixar claro
  se quer o dado do banco ou o que está escrito no contrato/acordo
- A pergunta menciona nome de pessoa sem especificar se quer cadastro ou documento
- Você ficou em dúvida entre relacional e vetorial antes de decidir
- A resposta pode ser mais completa combinando os dois stores, mesmo que
  a classificação principal seja uma só
- Qualquer caso de fronteira não coberto pelos exemplos acima

Use confianca="alta" apenas quando a categoria é inequívoca:
- "Qual o CPF / email / contato de X?" → relacional, alta
- "O que diz o contrato / petição / acordo de X?" → vetorial, alta
- "Quantos processos ativos temos?" → relacional, alta
- Pergunta sem contexto suficiente → reformular, alta
- Explicitamente pede banco E documento → híbrido, alta

Quando confianca="baixa" com tipo != "reformular", o sistema fará busca
híbrida automaticamente para cobrir as duas fontes.
"""

_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        model = os.getenv("LLM_MODEL", "gpt-5.4-mini-2026-03-17")
        log.info("Inicializando LLM classificador (%s)...", model)
        _llm = ChatOpenAI(model="gpt-5.4-mini-2026-03-17", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
        log.info("LLM classificador pronto!")
    return _llm


def classificar_pergunta(state: AgentState) -> AgentState:
    """Classifica a pergunta e registra o tipo e a confiança no estado."""
    try:
        # Injeta apenas as últimas 2 trocas para não poluir o contexto
        historico = state.get("historico", [])
        contexto_historico = formatar_historico(historico[-4:]) if historico else ""  # <<< NOVO

        conteudo_usuario = (                                                           # <<< NOVO
            f"{contexto_historico}"
            f"Pergunta a classificar: {state['pergunta']}"
        )

        resultado: Classificacao = _get_llm().with_structured_output(Classificacao).invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=conteudo_usuario),
        ])
        log.info(
            "Classificação: '%s' → %s (confiança: %s)",
            state["pergunta"], resultado.tipo, resultado.confianca,
        )
        return {
            **state,
            "tipo_consulta": resultado.tipo,
            "confianca_classificacao": resultado.confianca,
        }

    except Exception as e:
        log.warning("Falha na classificação (%s) → reformular", e)
        return {**state, "tipo_consulta": "reformular", "confianca_classificacao": "alta"}