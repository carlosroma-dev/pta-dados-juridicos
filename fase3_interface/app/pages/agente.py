"""Aba de Chat com o Agente Jurídico (Fase 3).

Canal principal de uso do sistema pelo cliente. A proposta é a de um
"estagiário gênio": simples, direto e confiável. A página tem dois estados:

1. Tela inicial (sem mensagens): saudação centralizada + campo de pergunta +
   atalhos de perguntas frequentes (Opção A das referências).
2. Conversa: histórico de bolhas acumulando na sessão, indicador de
   carregamento enquanto o agente pensa, e a citação da fonte (documento ou
   tabela) em cada resposta.

Toda a comunicação passa pelo `ApiClient` (POST /agente/perguntar) — a página
nunca toca no banco nem no LangGraph diretamente.
"""

from __future__ import annotations

import html
import re

import streamlit as st

from components.connection_status import render_status_conexao
from components.sidebar_conversas import (
    abrir_conversa,
    iniciar_nova_conversa,
    render_sidebar_conversas,
)
from services import historico
from services.api_client import ApiError, get_client

# ── Conteúdo da interface (linguagem simples, sem jargão técnico) ──────────────

# Avatar do assistente. ":material/gavel:" no st.chat_message (que entende
# Material symbols nativamente); o SVG inline em avatar_svg() para os trechos
# em HTML cru, onde o atalho :material/...: sairia como texto literal.
AVATAR_ASSISTENTE = ":material/gavel:"

_GAVEL_PATH = (
    "M200-200h400q17 0 28.5 11.5T640-160q0 17-11.5 28.5T600-120H200q-17 0-28.5-11.5"
    "T160-160q0-17 11.5-28.5T200-200Zm129-171L216-484q-23-23-23.5-56.5T215-597l29-29"
    " 228 226-29 29q-23 23-57 23t-57-23Zm311-197L414-796l29-29q23-23 56.5-22.5T556-824"
    "l113 113q23 23 23 57t-23 57l-29 29Zm156 380L302-682l56-56 494 494q11 11 11 28t-11"
    " 28q-11 11-28 11t-28-11Z"
)


def avatar_svg(tamanho: int = 36, cor: str = "#D85A30") -> str:
    """Ícone do assistente (martelo) como SVG inline, para uso em HTML cru."""
    return (
        f'<svg viewBox="0 -960 960 960" width="{tamanho}" height="{tamanho}" '
        f'fill="{cor}" xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{_GAVEL_PATH}"/></svg>'
    )


SAUDACAO = "Em que posso ajudar hoje?"
SUBTITULO = "Pergunte sobre prazos, honorários, processos ou documentos do escritório."

# (ícone Material, rótulo curto no atalho, pergunta completa enviada ao agente)
SUGESTOES: list[tuple[str, str, str]] = [
    (":material/schedule:", "Prazos", "Quais processos têm prazo nos próximos 7 dias?"),
    (":material/payments:", "Honorários", "Liste os 5 maiores honorários atrasados."),
    (":material/folder:", "Carteira", "Como está a carteira de processos do escritório?"),
    (":material/search:", "Documentos", "O que consta nos contratos e petições cadastrados?"),
]

DISCLAIMER = "Respostas geradas por IA — confira sempre os documentos oficiais."

# Mensagens de erro amigáveis — nunca expõem stack trace ou detalhe técnico.
MSG_ERRO_CONEXAO = (
    "Não consegui falar com o sistema do escritório agora. "
    "Verifique a conexão e tente novamente em instantes."
)
MSG_ERRO_GENERICO = (
    "Tive um problema inesperado ao processar sua pergunta. "
    "Tente reformular ou pergunte de novo daqui a pouco."
)
MSG_SEM_RESPOSTA = (
    "Não encontrei essa informação nos documentos e registros do escritório. "
    "Tente reformular a pergunta ou ser mais específico."
)


# ── Estilos (paleta creme/coral; o tema base é light, fixado no config.toml) ───

def aplicar_estilos() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2.5rem; }

        /* Esconde a barra de desenvolvedor (Deploy / menu) — o cliente vê só o app.
           Reforça o config.toml caso o toolbarMode não pegue em algum ambiente. */
        [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

        /* Saudação centralizada da tela inicial */
        .hero { text-align: center; }
        .hero-icone {
            width: 68px; height: 68px; border-radius: 50%;
            background: #FAECE7;
            display: flex; align-items: center; justify-content: center;
            margin: 0 auto 20px;
        }
        .hero-titulo {
            font-family: Georgia, "Iowan Old Style", "Times New Roman", serif;
            font-size: 42px; font-weight: 500; color: #2B2B28; margin-bottom: 10px;
        }
        .hero-sub {
            font-size: 17px; color: #6B6A64; line-height: 1.55;
            max-width: 560px; margin: 0 auto;
        }

        /* Campo de pergunta da tela inicial em formato pílula */
        div[data-testid="stTextInput"] input {
            border-radius: 28px !important;
            padding: 16px 24px !important;
            font-size: 17px !important;
        }
        /* Atalhos e botão de envio mais arredondados e maiores */
        .stButton button, .stFormSubmitButton button {
            border-radius: 26px !important;
            padding: 12px 18px !important;
            font-size: 15px !important;
        }
        /* Chips de sugestão: equaliza todos os botões. */
        .block-container [data-testid="column"] {
            display: flex !important;
            flex-direction: column !important;
        }
        .block-container [data-testid="column"] .stButton {
            flex: 1 !important;
            width: 100% !important;
        }
        .block-container [data-testid="column"] .stButton > div {
            width: 100% !important;
        }
        .block-container [data-testid="column"] .stButton button {
            width: 100% !important;
            min-height: 56px !important;
            padding: 12px 20px !important;
            line-height: 1.25 !important;
            justify-content: center !important;
            box-sizing: border-box !important;
        }
        /* Rótulos curtos: nunca quebram no meio da palavra. */
        .block-container [data-testid="column"] .stButton button * {
            white-space: nowrap !important;
            word-break: normal !important;
            overflow-wrap: normal !important;
        }
        .block-container [data-testid="column"] .stButton button [data-testid="stIconMaterial"] {
            font-size: 20px !important;
        }

        .disclaimer {
            text-align: center; font-size: 13px; color: #9A998F; margin-top: 22px;
        }

        /* Cabeçalho discreto do modo conversa */
        .cabecalho-conversa {
            display: flex; align-items: center; gap: 10px; margin-bottom: 6px;
            font-family: Georgia, "Times New Roman", serif;
            font-size: 20px; color: #2B2B28;
        }

        /* Citação de fonte abaixo da resposta */
        .linha-fontes { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 2px; }
        .chip-fonte, .chip-origem {
            display: inline-flex; align-items: center; gap: 5px;
            font-size: 12px; padding: 3px 10px; border-radius: 999px; line-height: 1.4;
        }
        .chip-fonte { background: #F0EEE6; color: #5F5E5A; border: 0.5px solid rgba(0,0,0,.08); }
        .chip-doc   { background: #FAECE7; color: #993C1D; }   /* origem: documento */
        .chip-banco { background: #E6F1FB; color: #0C447C; }   /* origem: banco       */

        /* Barra lateral no estilo "Recentes" */
        /* Sobe o conteúdo (menos espaço vazio no topo) */
        section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
            padding-top: 0.5rem !important; padding-bottom: 0 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] { padding-top: 0 !important; }
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 0.5rem !important; }
        /* Aperta o espaço vertical entre os itens */
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.3rem !important; }

        .rotulo-recentes {
            font-size: 12px; color: #9A998F; margin: 2px 0 12px; padding-left: 4px;
        }
        section[data-testid="stSidebar"] .stButton button {
            border: none !important; background: transparent !important;
            text-align: left !important; justify-content: flex-start !important;
            padding: 6px 12px !important; border-radius: 8px !important;
            font-size: 14px !important; font-weight: 400 !important; color: #2B2B28 !important;
            /* Deixa o título quebrar linha em vez de cortar */
            white-space: normal !important; line-height: 1.3 !important;
            height: auto !important; min-height: 0 !important;
        }
        section[data-testid="stSidebar"] .stButton button:hover { background: #E8E6DD !important; }
        section[data-testid="stSidebar"] .stButton button[kind="primary"] {
            background: #D85A30 !important; color: #fff !important;
        }
        section[data-testid="stSidebar"] .stButton button[kind="primary"]:hover {
            background: #C24E28 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── Extração da citação de fonte ───────────────────────────────────────────────
# O agente embute a fonte no texto, ex.: "(Fonte: contrato.pdf)". Tiramos esse
# trecho do corpo e mostramos num chip à parte, mais legível para o cliente.

_PADRAO_FONTE = re.compile(r"\(\s*fontes?\s*:\s*([^)]+?)\s*\)", re.IGNORECASE)


def extrair_fontes(texto: str) -> tuple[str, list[str]]:
    """Devolve (texto_sem_marcacao, lista_de_fontes_unicas)."""
    fontes: list[str] = []
    for achado in _PADRAO_FONTE.finditer(texto):
        # Uma marcação pode listar várias fontes separadas por vírgula.
        for parte in achado.group(1).split(","):
            nome = parte.strip()
            if nome and nome.lower() not in {f.lower() for f in fontes}:
                fontes.append(nome)

    limpo = _PADRAO_FONTE.sub("", texto)
    limpo = re.sub(r"[ \t]{2,}", " ", limpo)
    limpo = re.sub(r"\n{3,}", "\n\n", limpo).strip()
    return limpo, fontes


# Ícones de fonte como SVG inline (os chips são montados em HTML cru, onde o
# atalho :material/...: não é interpretado). Cor herda do texto do chip.
_ICONE_TABELA_SVG = (
    '<svg viewBox="0 -960 960 960" width="14" height="14" fill="currentColor" '
    'style="vertical-align:-2px" xmlns="http://www.w3.org/2000/svg"><path d="M480-120q'
    "-151 0-255.5-46.5T120-280v-400q0-66 105.5-113T480-840q149 0 254.5 47T840-680v400q0 "
    "67-104.5 113.5T480-120Zm0-479q89 0 179-25.5T760-679q-11-29-100.5-55T480-760q-91 0-178.5 "
    "25.5T200-679q14 30 101.5 55T480-599Zm0 199q42 0 81-4t74.5-11.5q35.5-7.5 67-18.5t57.5-25"
    "v-120q-26 14-57.5 25t-67 18.5Q600-528 561-524t-81 4q-42 0-82-4t-75.5-11.5Q287-543 256-554"
    "t-56-25v120q25 14 56 25t66.5 18.5Q358-408 398-404t82 4Zm0 200q46 0 93.5-7t87.5-18.5q40"
    "-11.5 67-26t32-29.5v-98q-26 14-57.5 25t-67 18.5Q600-328 561-324t-81 4q-42 0-82-4t-75.5"
    '-11.5Q287-343 256-354t-56-25v99q5 15 31.5 29t66.5 25.5q40 11.5 88 18.5t94 7Z"/></svg>'
)
_ICONE_DOC_SVG = (
    '<svg viewBox="0 -960 960 960" width="14" height="14" fill="currentColor" '
    'style="vertical-align:-2px" xmlns="http://www.w3.org/2000/svg"><path d="M360-240h240q17 '
    "0 28.5-11.5T640-280q0-17-11.5-28.5T600-320H360q-17 0-28.5 11.5T320-280q0 17 11.5 28.5T360"
    "-240Zm0-160h240q17 0 28.5-11.5T640-440q0-17-11.5-28.5T600-480H360q-17 0-28.5 11.5T320-440q0 "
    "17 11.5 28.5T360-400ZM240-80q-33 0-56.5-23.5T160-160v-640q0-33 23.5-56.5T240-880h287q16 0 "
    "30.5 6t25.5 17l194 194q11 11 17 25.5t6 30.5v447q0 33-23.5 56.5T720-80H240Zm280-560v-160H240"
    'v640h480v-440H560q-17 0-28.5-11.5T520-640ZM240-800v200-200 640-640Z"/></svg>'
)


def _icone_fonte(nome: str) -> str:
    n = nome.lower()
    if n.endswith(".csv") or "tabela" in n or n.endswith(".xlsx"):
        return _ICONE_TABELA_SVG
    return _ICONE_DOC_SVG


def _badge_origem(rota: str | None) -> tuple[str, str] | None:
    """Mapeia a rota do grafo para um rótulo amigável + classe de cor."""
    if rota == "vetorial":
        return "Documento", "chip-doc"
    if rota == "relacional":
        return "Banco de dados", "chip-banco"
    return None


def render_fontes(fontes: list[str], rota: str | None) -> None:
    """Desenha os chips de fonte (arquivo/tabela) + o selo de origem."""
    chips: list[str] = []
    for nome in fontes:
        chips.append(
            f'<span class="chip-fonte">{_icone_fonte(nome)} {html.escape(nome)}</span>'
        )

    badge = _badge_origem(rota)
    if badge:
        rotulo, classe = badge
        chips.append(f'<span class="chip-origem {classe}">{html.escape(rotulo)}</span>')

    if chips:
        st.markdown(
            '<div class="linha-fontes">' + "".join(chips) + "</div>",
            unsafe_allow_html=True,
        )


# ── Comunicação com o agente ───────────────────────────────────────────────────

def _resposta(conteudo: str, fontes: list[str], rota: str | None) -> dict:
    return {"papel": "assistant", "conteudo": conteudo, "fontes": fontes, "rota": rota}


def obter_resposta(client, pergunta: str) -> dict:
    """Chama o agente e devolve a mensagem do assistente já tratada.

    Qualquer falha vira uma mensagem amigável — o cliente nunca vê erro técnico.
    """
    try:
        dados = client.perguntar_agente(pergunta, session_id=st.session_state.conversa_id)
    except ApiError:
        return _resposta(MSG_ERRO_CONEXAO, [], None)
    except Exception:  # rede instável, timeout, resposta inesperada, etc.
        return _resposta(MSG_ERRO_GENERICO, [], None)

    if not isinstance(dados, dict):
        return _resposta(MSG_ERRO_GENERICO, [], None)

    if sid := dados.get("session_id"):
        st.session_state.conversa_id = sid

    resposta = (dados.get("resposta") or "").strip()
    rota = dados.get("rota") or ""
    validado = bool(dados.get("validado", False))

    if not resposta:
        return _resposta(MSG_SEM_RESPOSTA, [], None)

    # Resposta que não passou na validação (nó de falha / sem contexto):
    # mostramos o texto, mas sem chip de fonte — não há origem confiável a citar.
    if not validado:
        return _resposta(resposta, [], None)

    texto_limpo, fontes = extrair_fontes(resposta)
    return _resposta(texto_limpo or resposta, fontes, rota)


# ── Ações de estado ────────────────────────────────────────────────────────────

def enfileirar(pergunta: str) -> None:
    """Registra a pergunta do usuário e a deixa pendente de resposta."""
    st.session_state.mensagens.append({"papel": "user", "conteudo": pergunta})
    st.session_state.pergunta_pendente = pergunta


# ── Estados da página ──────────────────────────────────────────────────────────

def render_tela_inicial() -> None:
    """Saudação centralizada + campo de pergunta + atalhos (Opção A)."""
    # Bloco central mais largo (~71% da área útil) — colunas laterais finas.
    _, meio, _ = st.columns([1, 5, 1])
    with meio:
        st.markdown('<div style="height: 6vh"></div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="hero">
                <div class="hero-icone">{avatar_svg(36)}</div>
                <div class="hero-titulo">{html.escape(SAUDACAO)}</div>
                <div class="hero-sub">{html.escape(SUBTITULO)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")

        with st.form("form_pergunta_inicial", clear_on_submit=True, border=False):
            campo, envio = st.columns([9, 1])
            pergunta = campo.text_input(
                "Sua pergunta",
                placeholder="Pergunte ao assistente…",
                label_visibility="collapsed",
            )
            enviado = envio.form_submit_button(
                ":material/send:", type="primary", use_container_width=True
            )
        if enviado and pergunta.strip():
            enfileirar(pergunta.strip())
            st.rerun()

        # Atalhos de perguntas frequentes numa linha só.
        linhas = st.columns(len(SUGESTOES))
        for (icone, rotulo, pergunta_completa), celula in zip(SUGESTOES, linhas):
            celula.button(
                rotulo,
                icon=icone,
                key=f"sugestao_{rotulo}",
                on_click=enfileirar,
                args=(pergunta_completa,),
                use_container_width=True,
            )

        st.markdown(
            f'<div class="disclaimer">{html.escape(DISCLAIMER)}</div>',
            unsafe_allow_html=True,
        )


def render_conversa(client) -> None:
    """Histórico de bolhas + processamento da pergunta pendente + campo do rodapé."""
    st.markdown(
        f'<div class="cabecalho-conversa">{avatar_svg(22)} '
        f"<span>Assistente Jurídico Mezzalira</span></div>",
        unsafe_allow_html=True,
    )

# Histórico acumulado na sessão.
    for msg in st.session_state.mensagens:
        avatar = AVATAR_ASSISTENTE if msg["papel"] == "assistant" else None
        
        with st.chat_message(msg["papel"], avatar=avatar):
            # Substitui o $ por \$ para impedir que o Streamlit transforme em equação
            conteudo_seguro = msg["conteudo"].replace("$", r"\$")
            st.markdown(conteudo_seguro)
            
            if msg["papel"] == "assistant":
                render_fontes(msg.get("fontes", []), msg.get("rota"))

    # Há uma pergunta aguardando resposta? Mostra o spinner e consulta o agente.
    if st.session_state.pergunta_pendente:
        with st.chat_message("assistant", avatar=AVATAR_ASSISTENTE):
            with st.spinner("Consultando as informações do escritório…"):
                msg = obter_resposta(client, st.session_state.pergunta_pendente)
        st.session_state.mensagens.append(msg)
        st.session_state.pergunta_pendente = None
        persistir_conversa()
        st.rerun()

    # Campo de digitação fixo no rodapé.
    pergunta = st.chat_input("Pergunte ao assistente…")
    if pergunta and pergunta.strip():
        enfileirar(pergunta.strip())
        st.rerun()


# ── Histórico de conversas (persistido em disco) ───────────────────────────────

def _titulo_de(mensagens: list[dict]) -> str:
    """Usa a 1ª pergunta do usuário como título da conversa (truncado)."""
    texto = next((m["conteudo"] for m in mensagens if m["papel"] == "user"), "Conversa")
    texto = " ".join(texto.split())
    return texto if len(texto) <= 60 else texto[:59].rstrip() + "…"


def persistir_conversa() -> None:
    """Salva (ou atualiza) a conversa ativa no histórico em disco."""
    if not st.session_state.mensagens:
        return
    conversa = historico.salvar(
        {
            "id": st.session_state.conversa_id,
            "titulo": st.session_state.conversa_titulo or _titulo_de(st.session_state.mensagens),
            "mensagens": st.session_state.mensagens,
        }
    )
    st.session_state.conversa_id = conversa["id"]
    st.session_state.conversa_titulo = conversa["titulo"]


# ── Execução da página ─────────────────────────────────────────────────────────

if "mensagens" not in st.session_state:
    st.session_state.mensagens = []
if "pergunta_pendente" not in st.session_state:
    st.session_state.pergunta_pendente = None
if "conversa_id" not in st.session_state:
    st.session_state.conversa_id = None
if "conversa_titulo" not in st.session_state:
    st.session_state.conversa_titulo = None

render_sidebar_conversas(destino_agente=False)
render_status_conexao()
aplicar_estilos()

client = get_client()

em_branco = not st.session_state.mensagens and st.session_state.pergunta_pendente is None
if em_branco:
    render_tela_inicial()
else:
    render_conversa(client)