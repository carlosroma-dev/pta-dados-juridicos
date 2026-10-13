"""Ponto de entrada da interface Streamlit (Fase 3).

Funciona como roteador: define as abas com `st.navigation`/`st.Page` e delega a
renderização para os arquivos em `app/pages/`. Toda a configuração (URL e chave
da API) vem do ambiente via `app/config.py` — nada hardcoded.

O entrypoint fica fora de `app/` de propósito: assim a pasta `app/pages/` não é
adjacente a ele e o Streamlit não dispara a auto-descoberta de páginas (que
conflitaria com o st.navigation).

Como rodar (de dentro de fase3_interface/):
    streamlit run app.py
ou, a partir da raiz do projeto:
    streamlit run fase3_interface/app.py
"""

import os
import sys

# Coloca a pasta `app/` no path para que as páginas possam importar
# `services`, `components` e `config` como módulos de topo.
_APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import streamlit as st  # noqa: E402


def _estilos_globais() -> None:
    """CSS compartilhado injetado antes de qualquer página renderizar.

    Ao ficar em app.py (que roda em todo rerun), esses estilos nunca somem
    durante a transição entre páginas — eliminando o flash visível ao navegar.
    Estilos específicos de cada página (hero, cards, etc.) continuam em
    aplicar_estilos() de cada arquivo.
    """
    st.markdown(
        """
        <style>
        /* ── Layout base ─────────────────────────────────────────────────── */
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] { display: none !important; }

        .stApp { background-color: #FAF9F5; }

        /* ── Barra lateral ───────────────────────────────────────────────── */
        section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
            padding-top: 0.5rem !important; padding-bottom: 0 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"]  { padding-top: 0 !important; }
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 0.5rem !important; }
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.15rem !important; }

        .rotulo-recentes {
            font-size: 12px; color: #9A998F; margin: 2px 0 12px; padding-left: 4px;
        }
        /* Base comum aos botões da sidebar */
        section[data-testid="stSidebar"] .stButton button {
            border: none !important; background: transparent !important;
            text-align: left !important; justify-content: flex-start !important;
            padding: 6px 12px !important; border-radius: 8px !important;
            font-weight: 400 !important;
            white-space: normal !important; line-height: 1.25 !important;
            height: auto !important; min-height: 0 !important;
        }
        /* Itens de "Recentes" (secundários): fonte menor, cor suave, ícone menor */
        section[data-testid="stSidebar"] .stButton button[kind="secondary"] {
            font-size: 12.5px !important; color: #6F6D64 !important;
            padding: 5px 10px !important;
        }
        section[data-testid="stSidebar"] .stButton button[kind="secondary"] [data-testid="stIconMaterial"] {
            font-size: 17px !important;
        }
        section[data-testid="stSidebar"] .stButton button:hover { background: #E8E6DD !important; }
        /* Botão primário "Nova conversa": mantém o destaque */
        section[data-testid="stSidebar"] .stButton button[kind="primary"] {
            background: #D85A30 !important; color: #fff !important;
            font-size: 14px !important; font-weight: 600 !important;
        }
        section[data-testid="stSidebar"] .stButton button[kind="primary"]:hover {
            background: #C24E28 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# set_page_config precisa ser a primeira chamada Streamlit e roda só aqui,
st.set_page_config(
    page_title="PTA Dados — Escritório Mezzalira",
    page_icon=":material/gavel:",
    layout="wide",
)

# As duas abas da navegação. Os caminhos são relativos a este arquivo.
painel = st.Page(
    "app/pages/dashboard.py",
    title="Painel de Consultas",
    icon=":material/dashboard:",
    default=True,
)
agente = st.Page(
    "app/pages/agente.py",
    title="Agente Jurídico",
    icon=":material/forum:",
)
adicionar = st.Page(
    "app/pages/adicionar_documento.py",
    title="Adicionar Documento",
    icon=":material/upload_file:",
)

insights = st.Page(
    "app/pages/insights.py",
    title="Insights do Agente",
    icon=":material/lightbulb:",
)

alertas = st.Page(
    "app/pages/alertas.py",
    title="Central de Alertas",
    icon=":material/notifications:",
)

navegacao = st.navigation([painel, agente, adicionar, insights, alertas])
_estilos_globais()
navegacao.run()