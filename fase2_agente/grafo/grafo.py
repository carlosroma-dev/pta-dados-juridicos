import os
import re
import logging
from typing import TypedDict, Literal
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from fase2_agente.rag.retriever import PgVectorRetriever
from fase2_agente.memoria.janela import formatar_historico

from fase2_agente.ferramentas import (
    buscar_documento,
    verificar_prazos,
    checar_honorarios,
    status_carteira,
    consultar_banco,
)
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
log = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-5.4-mini-2026-03-17", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

class Estado(TypedDict):
    pergunta_original: str
    pergunta_reformulada: str
    rota: Literal["relacional", "vetorial", "hibrido", "ambigua"]
    ferramenta_relacional: str
    contexto: str
    contexto_relacional: str   # usado internamente pelo buscar_hibrido
    contexto_vetorial: str     # usado internamente pelo buscar_hibrido
    resposta: str
    validado: bool
    tentativas_ambigua: int
    tentativas_validacao: int
    historico: list[dict]


# Regex de número de processo no padrão CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO
# (ex.: 1234567-89.2024.5.06.0001). Usado pelo híbrido para escopar a busca.
_CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")


# ---------------------------------------------------------------------------
# Nós auxiliares
# ---------------------------------------------------------------------------

def formular(estado: Estado) -> Estado:
    """Reformula a pergunta para deixá-la clara e objetiva."""
    log.info("Nó: formular")
    pergunta = estado.get("pergunta_reformulada") or estado["pergunta_original"]

    contexto_historico = formatar_historico(estado.get("historico", []))
    resposta = llm.invoke([
        SystemMessage(content="""Você é um assistente jurídico.
Reformule a pergunta do usuário para que fique clara e objetiva, usando o histórico para resolver referências.
REGRAS OBRIGATÓRIAS:
- Use o histórico para resolver pronomes e referências implícitas: "ela", "o dele", "a do acordo", "esse processo" etc. devem ser substituídos pelo nome/entidade real identificada no histórico.
- Preserve dados já presentes na pergunta (CPF, ID, número de processo, datas, nomes).
- NUNCA adicione informações que não estavam na pergunta original ou no histórico.
- NUNCA invente ou adicione placeholders como [inserir CPF], [inserir ID], [inserir processo].
- Se a pergunta não tiver identificadores específicos e o histórico também não ajudar, apenas reescreva de forma clara mantendo o caráter geral.
Retorne APENAS a pergunta reformulada, sem explicações."""),
        HumanMessage(content=f"{contexto_historico}Pergunta atual: {pergunta}")
    ])

    return {**estado, "pergunta_reformulada": resposta.content.strip()}


def rotear(estado: Estado) -> Estado:
    log.info("Nó: rotear")
    from fase2_agente.grafo.nos.classificar_pergunta import classificar_pergunta

    resultado = classificar_pergunta({
        "pergunta": estado["pergunta_reformulada"],
        "tipo_consulta": "",
        "confianca_classificacao": "",
        "historico": estado.get("historico", []),
        "chunks_recuperados": [],
        "resposta": "",
    })

    tipo = resultado["tipo_consulta"]
    confianca = resultado.get("confianca_classificacao", "alta")  

    if tipo == "reformular":
        rota = "ambigua"
    elif confianca == "baixa":
        rota = "hibrido"
        log.info("Confiança baixa → forçando busca híbrida")
    else:
        rota = tipo

    tentativas_ambigua = estado.get("tentativas_ambigua", 0)
    if rota == "ambigua":
        tentativas_ambigua += 1

    log.info("Rota escolhida: %s", rota)
    return {**estado, "rota": rota, "tentativas_ambigua": tentativas_ambigua}

def _extrair_dias(pergunta: str) -> int:
    """Extrai número de dias da pergunta (fallback: 7)."""
    resposta = llm.invoke([
        SystemMessage(content=(
            "Extraia o número de dias mencionado na pergunta. "
            "Se não houver número explícito, responda 7. "
            "Responda APENAS com o número inteiro, sem texto."
        )),
        HumanMessage(content=pergunta),
    ])
    try:
        return int(resposta.content.strip())
    except ValueError:
        return 7


def _extrair_params_honorarios(pergunta: str) -> tuple[str | None, str | None]:
    """Extrai (numero_processo, status_pagamento) da pergunta. None quando ausente."""
    resposta = llm.invoke([
        SystemMessage(content=(
            "Extraia da pergunta o número do processo (formato CNJ) e o status de pagamento. "
            "Status válidos APENAS: atrasado, em_dia, quitado. "
            "'em aberto', 'pendente', 'em atraso', 'inadimplente' NÃO são status válidos — use null. "
            "Se a pergunta mencionar 'em aberto E atrasado' ou 'em aberto ou atrasado', use null (retorna todos). "
            'Responda APENAS no formato: processo=VALOR status=VALOR. '
            'Use "null" quando não houver.'
        )),
        HumanMessage(content=pergunta),
    ])
    numero, status = None, None
    for parte in resposta.content.strip().split():
        if parte.startswith("processo="):
            v = parte.split("=", 1)[1]
            numero = v if v != "null" else None
        elif parte.startswith("status="):
            v = parte.split("=", 1)[1]
            status = v if v != "null" else None
    return numero, status


def _extrair_processos(texto: str) -> list[str]:
    """Extrai os números de processo (CNJ) presentes num texto, sem duplicar
    e preservando a ordem de aparição."""
    vistos: list[str] = []
    for cnj in _CNJ_RE.findall(texto):
        if cnj not in vistos:
            vistos.append(cnj)
    return vistos


# ---------------------------------------------------------------------------
# Lógica de busca compartilhada (usada pelos nós relacional/vetorial/híbrido)
# ---------------------------------------------------------------------------

def _executar_relacional(estado: Estado) -> tuple[str, str]:
    """Sub-roteador relacional: escolhe a ferramenta, invoca e devolve
    (contexto_com_marcador_de_fonte, ferramenta_escolhida)."""
    pergunta = estado["pergunta_reformulada"]

    resposta = llm.invoke([
        SystemMessage(content="""Você escolhe qual ferramenta usar para responder uma pergunta sobre dados jurídicos estruturados.

- "verificar_prazos"  : prazos processuais, vencimentos, processos urgentes.
  Exemplos: "Quais processos vencem essa semana?", "Tem prazo nos próximos 10 dias?",
            "Quais processos têm prazo nos próximos 7 dias?", "Mostre os prazos urgentes.",
            "Tem algum processo vencendo essa semana?"

- "checar_honorarios" : situação financeira de honorários — use quando a pergunta mencionar
  status de pagamento (atrasado, em dia, quitado, em aberto) OU número de processo (CNJ).
  Exemplos: "Quanto o processo 1234567-89.2024.5.06.0001 tem em aberto?",
            "Quais honorários estão atrasados?",
            "Quais honorários estão em aberto ou atrasados?",
            "Mostre os honorários em atraso.",
            "Qual o total de honorários em aberto?"

- "status_carteira"   : visão geral da carteira, contagens, distribuição de processos, painel.
  Exemplos: "Como está a carteira?", "Quantos processos ativos temos?"

- "consultar_banco"   : qualquer outra consulta livre — use SEMPRE que a pergunta mencionar
  nome de cliente ou advogado, mesmo que o assunto seja financeiro (honorários, valores,
  pagamentos). Também cobre: busca por CPF, ranking, listagens por tipo/data.
  Exemplos: "Qual o CPF da Fernanda Costa?", "Qual advogado tem mais processos ativos?",
            "Liste os processos abertos nos últimos 30 dias.",
            "Qual o valor dos honorários da Ana Lima?",
            "Quanto a Maria Oliveira deve em honorários?"

Responda APENAS com: verificar_prazos, checar_honorarios, status_carteira ou consultar_banco"""),
        HumanMessage(content=pergunta),
    ])

    escolha = resposta.content.strip().lower()
    if escolha not in {"verificar_prazos", "checar_honorarios", "status_carteira", "consultar_banco"}:
        log.warning("Sub-rota inválida '%s' → consultar_banco (fallback)", escolha)
        escolha = "consultar_banco"
    
    _STATUS_HONORARIOS = ("atrasado", "em_dia", "quitado", "em aberto", "em atraso", "inadimplente")
    tem_status = any(s in pergunta.lower() for s in _STATUS_HONORARIOS)
    if escolha == "checar_honorarios" and not _CNJ_RE.search(pergunta) and not tem_status:
        log.info("checar_honorarios sem CNJ nem status → redirecionando para consultar_banco")
        escolha = "consultar_banco"

    log.info("Ferramenta relacional escolhida: %s", escolha)

    _TABELAS_POR_FERRAMENTA = {
        "verificar_prazos":  ["processos.csv", "clientes.csv", "advogados.csv"],
        "checar_honorarios": ["honorarios.csv", "processos.csv", "clientes.csv"],
        "status_carteira":   ["processos.csv", "honorarios.csv", "clientes.csv", "advogados.csv"],
        "consultar_banco":   ["processos.csv", "clientes.csv", "advogados.csv", "honorarios.csv"],
    }

    if escolha == "verificar_prazos":
        dados_brutos = verificar_prazos.invoke({"dias": _extrair_dias(pergunta)})
    elif escolha == "checar_honorarios":
        numero, status = _extrair_params_honorarios(pergunta)
        dados_brutos = checar_honorarios.invoke({
            "processo_numero": numero,
            "status_pagamento": status,
        })
    elif escolha == "consultar_banco":
        # Usa a pergunta original para não perder ID/CPF que a reformulação pode parafrasear.
        dados_brutos = consultar_banco.invoke({"pergunta": pergunta})
    else:  # status_carteira
        dados_brutos = status_carteira.invoke({})

    tabelas = ", ".join(_TABELAS_POR_FERRAMENTA.get(escolha, ["banco de dados"]))
    contexto = f"[FONTE: {tabelas}]\n\n{dados_brutos}"
    return contexto, escolha


def _executar_vetorial(estado: Estado, processos: list[str] | None = None) -> str:
    """Busca documentos via tool buscar_documento. Quando `processos` é
    informado, a busca é escopada a esses processos (usado pelo híbrido)."""
    pergunta = estado["pergunta_reformulada"]
    return buscar_documento.invoke({
        "pergunta": pergunta,
        "top_k": 5,
        "processos": processos,
    })

# ---------------------------------------------------------------------------
# Helper: detecta resultado sem dados úteis
# ---------------------------------------------------------------------------

_MARCADORES_VAZIO = (
    "nenhum resultado",
    "nenhum trecho",
    "não encontrei",
    "não há registros",
    "nenhum processo",
)

def _esta_vazio(contexto: str) -> bool:
    """Retorna True quando o contexto não contém dados recuperados."""
    ctx_lower = contexto.lower()
    return any(marcador in ctx_lower for marcador in _MARCADORES_VAZIO)

# ---------------------------------------------------------------------------
# Nós de busca
# ---------------------------------------------------------------------------

def buscar_relacional(estado: Estado) -> Estado:
    """Busca no banco relacional. Se vazio, tenta documentos como fallback."""
    log.info("Nó: buscar_relacional")
    contexto, escolha = _executar_relacional(estado)

    if _esta_vazio(contexto):
        log.info("Relacional vazio → tentando fallback vetorial")
        ctx_fallback = _executar_vetorial(estado)
        if not _esta_vazio(ctx_fallback):
            log.info("Fallback vetorial retornou dados")
            return {**estado, "ferramenta_relacional": escolha, "contexto": ctx_fallback}
        log.info("Fallback vetorial também vazio — seguindo com resultado original")

    return {**estado, "ferramenta_relacional": escolha, "contexto": contexto}

def buscar_vetorial(estado: Estado) -> Estado:
    """Busca em documentos via pgvector. Se vazio, tenta banco como fallback."""
    log.info("Nó: buscar_vetorial")
    ctx_vetorial = _executar_vetorial(estado)

    if _esta_vazio(ctx_vetorial):
        log.info("Vetorial vazio → tentando fallback relacional")
        ctx_fallback, escolha = _executar_relacional(estado)
        if not _esta_vazio(ctx_fallback):
            log.info("Fallback relacional retornou dados")
            return {**estado, "ferramenta_relacional": escolha, "contexto": ctx_fallback}
        log.info("Fallback relacional também vazio — seguindo com resultado original")

    return {**estado, "contexto": ctx_vetorial}


def buscar_hibrido(estado: Estado) -> Estado:
    """Cruza banco relacional + documentos vetoriais.

    Estratégia: resolve primeiro os dados estruturados (que já trazem os
    números de processo), extrai os CNJ do resultado e usa-os para *escopar*
    a busca vetorial àqueles processos. Se nenhum CNJ for identificado, cai
    no comportamento global (busca em todo o acervo)."""
    log.info("Nó: buscar_hibrido")

    ctx_relacional, _ = _executar_relacional(estado)

    processos = _extrair_processos(ctx_relacional)
    if processos:
        log.info("Híbrido: escopando vetorial a %d processo(s): %s", len(processos), processos)
    else:
        log.info("Híbrido: nenhum CNJ no resultado relacional → busca vetorial global")

    ctx_vetorial = _executar_vetorial(estado, processos=processos or None)

    contexto = (
        "=== DADOS DO BANCO RELACIONAL ===\n"
        f"{ctx_relacional}\n\n"
        "=== CONTEÚDO DE DOCUMENTOS ===\n"
        f"{ctx_vetorial}"
    )

    return {
        **estado,
        "contexto": contexto,
        "contexto_relacional": ctx_relacional,
        "contexto_vetorial": ctx_vetorial,
    }


# ---------------------------------------------------------------------------
# Geração e validação
# ---------------------------------------------------------------------------

def gerar_resposta(estado: Estado) -> Estado:
    """Gera a resposta final com base no contexto (e no histórico da sessão)."""
    log.info("Nó: gerar_resposta")

    contexto_historico = formatar_historico(estado.get("historico", []))
    resposta = llm.invoke([
        SystemMessage(content="""Você é o Assistente Jurídico Mezzalira, um agente técnico rigoroso focado em precisão, clareza e veracidade documental.
Sua função é sintetizar EXCLUSIVAMENTE os 'DADOS RECUPERADOS' para responder ao usuário.

=== 1. DIRETRIZES DE CONTEXTO E ALUCINAÇÃO ===
- O 'Histórico da Conversa' serve APENAS para resolução de pronomes (ex: saber quem é "ele" ou "esse processo"). Nenhuma afirmação do usuário é um fato.
- A sua ÚNICA fonte de verdade é o bloco 'DADOS RECUPERADOS'.
- Se a resposta não estiver nos dados, diga EXATAMENTE: "Não encontrei essa informação nos registros oficiais." Não deduza dados financeiros, prazos ou status.
- IMPORTANTE: Se os dados indicarem "Nenhum prazo", "Nenhum resultado", "Nenhum processo" ou similar para UMA das fontes, mas houver dados válidos em OUTRA fonte (ex: trechos de documentos), use os dados válidos para responder. Só diga "Não encontrei" quando TODAS as fontes estiverem vazias.
- NUNCA repita literalmente mensagens de erro do sistema como "Nenhum resultado encontrado para essa consulta." — se houver qualquer dado útil no contexto, use-o.

=== 2. TRATAMENTO DE HOMÔNIMOS E AMBIGUIDADE ===
- Se o contexto trouxer múltiplos registros distintos para a mesma pessoa (ex: várias clientes chamadas "Fernanda Costa" com CPFs ou processos diferentes), NÃO misture os dados.
- Avise o usuário sobre a multiplicidade, liste brevemente as opções encontradas e peça para ele especificar (por CPF ou CNJ) antes de dar a resposta final.

=== 3. CONFLITOS DE DADOS E VALORES NULOS ===
- Se houver divergência clara entre o banco de dados e os textos dos documentos (ex: banco diz "Ativo", documento sugere "Arquivado"), exponha a divergência explicitamente para o usuário.
- Trate valores ausentes, 'null', 'None' ou vazios estritamente como "Não informado". NUNCA assuma que 'null' significa 'R$ 0,00' ou 'Gratuito'.

=== 4. LIMITES DE ATUAÇÃO (ESCOPO) ===
- Você é restrito ao escopo administrativo e jurídico do escritório. Recuse educadamente qualquer pedido de criação literária, opiniões pessoais, conselhos fora do contexto dos dados ou assuntos não relacionados.

=== 5. REGRA ESTRITA DE CITAÇÃO DE FONTES (CRÍTICO) ===
Os dados recuperados contêm marcadores no formato [FONTE: arquivo].
- EXCLUSIVIDADE: Cite APENAS as fontes das quais você efetivamente extraiu dados para compor a resposta. Ignore solenemente arquivos que vieram no contexto mas não foram úteis.
- UNIFICAÇÃO: Em buscas híbridas, combine CSVs e PDFs na mesma citação.
- FORMATO EXATO OBRIGATÓRIO: (Fonte: processos.csv, contrato_honorarios.pdf)
- POSIÇÃO: A citação deve ser OBRIGATORIAMENTE a última linha da sua resposta. Nenhuma palavra ou ponto final deve existir depois do parêntese de fechamento."""),
        HumanMessage(content=(
            "=== HISTÓRICO DA CONVERSA (MEMÓRIA) ===\n"
            f"{contexto_historico}\n"
            "--------------------------------------------------\n\n"
            
            "=== PERGUNTA ATUAL DO USUÁRIO ===\n"
            f"Original: {estado['pergunta_original']}\n"
            f"Reformulada: {estado['pergunta_reformulada']}\n"
            "--------------------------------------------------\n\n"
            
            "=== DADOS RECUPERADOS (BASE OFICIAL DO ESCRITÓRIO) ===\n"
            f"{estado['contexto']}"
        ))
    ])

    return {**estado, "resposta": resposta.content.strip()}


def validar(estado: Estado) -> Estado:
    log.info("Nó: validar")

    resposta_llm = llm.invoke([
        SystemMessage(content="""Você é um validador de respostas jurídicas.
Avalie se a resposta tenta responder a pergunta com base nas informações disponíveis.
Responda "passou" se a resposta:
- Contém dados concretos (números, nomes, datas, valores), OU
- Explica claramente o que foi encontrado no banco/documentos, OU
- Informa que não há registros para aquela consulta específica.
Responda "nao_passou" SOMENTE se a resposta for completamente vaga, sem nenhuma informação útil.
Responda APENAS com: passou ou nao_passou"""),
        HumanMessage(content=f"Pergunta: {estado['pergunta_reformulada']}\nResposta: {estado['resposta']}")
    ])

    validado = "passou" in resposta_llm.content.strip().lower()
    tentativas_validacao = estado.get("tentativas_validacao", 0) + 1

    log.info("Validação: %s (tentativa %d)", "passou" if validado else "não passou", tentativas_validacao)
    return {**estado, "validado": validado, "tentativas_validacao": tentativas_validacao}


def responder(estado: Estado) -> Estado:
    """Nó final — apenas loga e passa a resposta adiante."""
    log.info("Nó: responder")
    return estado


def falha(estado: Estado) -> Estado:
    """Retorna mensagem construtiva quando a resposta gerada não passou na validação."""
    log.info("Nó: falha")
    return {**estado, "resposta": (
        "Não consegui montar uma resposta confiável com os dados disponíveis. "
        "Algumas sugestões:\n"
        "- Inclua o número do processo (formato CNJ) ou o CPF do cliente\n"
        "- Especifique o período se for uma busca por prazo ou pagamento\n"
        "- Se quiser o conteúdo de um documento, mencione o tipo "
        "(ex.: \"contrato\", \"petição\", \"acordo\")\n\n"
        "Exemplo: \"Qual o status e os honorários do processo "
        "1234567-89.2024.5.06.0001?\""
    )}

def pedir_esclarecimento(estado: Estado) -> Estado:
    """Gera uma pergunta de esclarecimento quando a intenção é ambígua.
    Vai direto ao END — não passa por gerar_resposta nem validar.
    """
    log.info("Nó: pedir_esclarecimento")

    contexto_historico = formatar_historico(estado.get("historico", []))
    pergunta_original = estado["pergunta_original"]

    try:
        resposta = llm.invoke([
            SystemMessage(content="""Você é o Assistente Jurídico Mezzalira.
O usuário fez uma pergunta que não ficou clara o suficiente para saber onde buscar.
Peça um esclarecimento educado e útil seguindo estas regras:

1. Explique em UMA frase o que não ficou claro.
2. Ofereça as duas direções de busca em linguagem simples:
   - "dados do sistema" → prazos, status, valores, contatos, honorários
   - "conteúdo de documentos" → o que está escrito em contratos, petições, acordos
3. Se faltar um identificador (nome do cliente, número do processo, CPF), peça explicitamente.
4. Dê 1 ou 2 exemplos concretos de como reformular.
5. Seja breve. Sem listas longas, sem jargão técnico."""),
            HumanMessage(content=(
                f"{contexto_historico}"
                f"Pergunta do usuário: {pergunta_original}"
            )),
        ])
        mensagem = resposta.content.strip()
    except Exception as exc:
        log.error("Erro ao gerar esclarecimento: %s", exc)
        mensagem = (
            "Sua pergunta ficou um pouco vaga para eu saber onde buscar. "
            "Poderia especificar:\n"
            "- De qual cliente ou processo você quer a informação?\n"
            "- Você quer dados do sistema (prazos, valores, status) "
            "ou o conteúdo de um documento (contrato, petição, acordo)?\n\n"
            "Exemplo: \"Qual o prazo do processo 1234567-89.2024.5.06.0001?\" "
            "ou \"O que diz o contrato da Ana Lima?\""
        )

    return {**estado, "resposta": mensagem, "validado": True}

# ---------------------------------------------------------------------------
# Condicionais
# ---------------------------------------------------------------------------

def decidir_rota(estado: Estado) -> str:
    rota = estado.get("rota", "ambigua")

    if rota == "relacional":
        return "buscar_relacional"
    elif rota == "vetorial":
        return "buscar_vetorial"
    elif rota == "hibrido":
        return "buscar_hibrido"
    else:
        return "pedir_esclarecimento"


def decidir_validacao(estado: Estado) -> str:
    if estado.get("validado"):
        return "responder"
    log.warning("Validação não passou — encerrando com falha.")
    return "falha"


# ---------------------------------------------------------------------------
# Construção do grafo
# ---------------------------------------------------------------------------

def construir_grafo():
    grafo = StateGraph(Estado)

    grafo.add_node("formular",              formular)
    grafo.add_node("rotear",                rotear)
    grafo.add_node("buscar_relacional",     buscar_relacional)
    grafo.add_node("buscar_vetorial",       buscar_vetorial)
    grafo.add_node("buscar_hibrido",        buscar_hibrido)
    grafo.add_node("gerar_resposta",        gerar_resposta)
    grafo.add_node("validar",               validar)
    grafo.add_node("responder",             responder)
    grafo.add_node("falha",                 falha)
    grafo.add_node("pedir_esclarecimento",  pedir_esclarecimento)   

    grafo.set_entry_point("formular")
    grafo.add_edge("formular", "rotear")
    grafo.add_conditional_edges("rotear", decidir_rota, {
        "buscar_relacional":    "buscar_relacional",
        "buscar_vetorial":      "buscar_vetorial",
        "buscar_hibrido":       "buscar_hibrido",
        "pedir_esclarecimento": "pedir_esclarecimento",   
    })
    grafo.add_edge("buscar_relacional",     "gerar_resposta")
    grafo.add_edge("buscar_vetorial",       "gerar_resposta")
    grafo.add_edge("buscar_hibrido",        "gerar_resposta")
    grafo.add_edge("gerar_resposta",        "validar")
    grafo.add_conditional_edges("validar", decidir_validacao, {
        "responder": "responder",
        "falha":     "falha",
    })
    grafo.add_edge("pedir_esclarecimento",  END)  
    grafo.add_edge("falha",                 END)
    grafo.add_edge("responder",             END)

    return grafo.compile()


app = construir_grafo()


def perguntar(pergunta: str, historico: list[dict] | None = None) -> Estado:
    """Executa o grafo do agente para uma pergunta e devolve o estado final.

    Centraliza a inicialização do estado para que a API (rota /agente) e os
    scripts de teste invoquem o agente da mesma forma, sem duplicar o dict."""
    return app.invoke({
        "pergunta_original":    pergunta,
        "pergunta_reformulada": "",
        "rota":                 "",
        "ferramenta_relacional": "",
        "contexto":             "",
        "contexto_relacional":  "",
        "contexto_vetorial":    "",
        "resposta":             "",
        "validado":             False,
        "tentativas_ambigua":   0,
        "tentativas_validacao": 0,
        "historico":            historico if historico is not None else [],
    })