"""Componente de status da conexão com a API, exibido na barra lateral.

Serve como prova viva de que o cliente HTTP consegue conectar e autenticar
na FastAPI — visível em todas as abas.
"""

from __future__ import annotations

import streamlit as st

from services.api_client import get_client

_STATE_KEY = "_status_conexao"


def render_status_conexao() -> None:
    """Desenha, na sidebar, o status da conexão e um botão para retestar."""
    client = get_client()

    with st.sidebar:
        st.divider()
        st.caption("Status da API")

        # Testa uma vez por sessão; o botão força um novo teste.
        if st.button("Testar conexão", use_container_width=True):
            st.session_state[_STATE_KEY] = client.verificar_conexao()
        if _STATE_KEY not in st.session_state:
            st.session_state[_STATE_KEY] = client.verificar_conexao()

        ok, mensagem = st.session_state[_STATE_KEY]
        if ok:
            st.success(mensagem, icon=":material/check_circle:")
        else:
            st.error(mensagem, icon=":material/error:")

        st.caption(f"Base URL: `{client.base_url}`")
        st.caption("Autenticação: " + ("ativa" if client.api_key else "desativada (dev)"))