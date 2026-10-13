"""Sidebar de histórico de conversas, compartilhada entre as páginas.

Centraliza o "Nova conversa" + lista de "Recentes" para que tanto o Agente
quanto o Painel exibam a mesma barra lateral. A diferença é o comportamento ao
clicar:

- Na página do Agente (`destino_agente=False`): aplica a ação no próprio estado
  da sessão (inicia/abre conversa) e dá rerun, como antes.
- Em outras páginas (`destino_agente=True`): a ação prepara o estado e redireciona
  para a página do Agente via `st.switch_page`, já que conversa só existe lá.

Toda a persistência continua em `services.historico`.
"""

from __future__ import annotations

import streamlit as st

from services import historico

_PAGINA_AGENTE = "app/pages/agente.py"


def _garantir_estado() -> None:
    """Inicializa as chaves de sessão usadas pela conversa, se faltarem."""
    st.session_state.setdefault("mensagens", [])
    st.session_state.setdefault("pergunta_pendente", None)
    st.session_state.setdefault("conversa_id", None)
    st.session_state.setdefault("conversa_titulo", None)


def iniciar_nova_conversa() -> None:
    """Limpa a tela para uma conversa nova (a anterior já está salva em disco)."""
    st.session_state.mensagens = []
    st.session_state.pergunta_pendente = None
    st.session_state.conversa_id = None
    st.session_state.conversa_titulo = None


def abrir_conversa(conversa: dict) -> None:
    """Carrega uma conversa salva para continuar de onde parou."""
    st.session_state.mensagens = list(conversa.get("mensagens", []))
    st.session_state.conversa_id = conversa.get("id")
    st.session_state.conversa_titulo = conversa.get("titulo")
    st.session_state.pergunta_pendente = None


def render_sidebar_conversas(destino_agente: bool = False) -> None:
    """Desenha 'Nova conversa' + lista de 'Recentes' na sidebar.

    Se `destino_agente=True`, cada ação redireciona para a página do Agente
    depois de ajustar o estado — usado nas páginas que não são o Agente.
    """
    _garantir_estado()

    with st.sidebar:
        nova = st.button(
            "Nova conversa",
            icon=":material/add:",
            use_container_width=True,
            type="primary",
            key="btn_nova_conversa",
        )
        if nova:
            iniciar_nova_conversa()
            if destino_agente:
                st.switch_page(_PAGINA_AGENTE)
            else:
                st.rerun()

        conversas = historico.carregar()
        if conversas:
            st.markdown(
                '<div class="rotulo-recentes">Recentes</div>', unsafe_allow_html=True
            )
            for conversa in conversas:
                clicado = st.button(
                    f"{conversa.get('titulo', 'Conversa')}",
                    icon=":material/chat_bubble:",
                    key=f"recente_{conversa['id']}",
                    use_container_width=True,
                )
                if clicado:
                    abrir_conversa(conversa)
                    if destino_agente:
                        st.switch_page(_PAGINA_AGENTE)
                    else:
                        st.rerun()