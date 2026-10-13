from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from components.connection_status import render_status_conexao
from services.api_client import ApiError, get_client
from components.sidebar_conversas import (
    abrir_conversa,
    iniciar_nova_conversa,
    render_sidebar_conversas,
)

def _icone_dashboard_svg() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px" fill="currentColor"><path d="M120-120v-80h720v80H120Zm0-160v-240h200v240H120Zm260 0v-480h200v480H380Zm260 0v-320h200v320H640Z"/></svg>'''

def aplicar_estilos() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2rem; max-width: 1400px; }

        [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

        .hero { text-align: center; margin-bottom: 2rem; }
        .hero-icone {
            width: 68px; height: 68px; border-radius: 50%;
            background: #FAECE7; color: #D85A30;
            display: flex; align-items: center; justify-content: center;
            margin: 0 auto 16px;
        }
        .hero-icone svg {
            width: 34px; height: 34px;
        }
        .hero-titulo {
            font-family: Georgia, "Times New Roman", serif;
            font-size: 36px; font-weight: 500; color: #2B2B28; margin-bottom: 8px;
        }
        .hero-sub { font-size: 16px; color: #9A998F; }

        [data-testid="stMetric"] {
            background: #FFFFFF;
            border-radius: 16px;
            padding: 20px 24px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.07);
            border: 1px solid #F0EEE6;
            min-height: 110px;
        }
        [data-testid="stMetricLabel"] { color: #9A998F !important; font-size: 13px !important; }
        [data-testid="stMetricValue"] { color: #2B2B28 !important; font-size: 30px !important; }
        [data-testid="stMetricDelta"] { font-size: 13px !important; }

        /* Expanders como cards */
        [data-testid="stExpander"] {
            background: #FFFFFF;
            border-radius: 16px !important;
            border: 1px solid #F0EEE6 !important;
            box-shadow: 0 1px 4px rgba(0,0,0,0.07);
            margin-bottom: 12px;
        }

        section.main .stPlotlyChart {
            background: #FFFFFF !important;
            border-radius: 12px !important;
        }
        .js-plotly-plot, .plot-container { background: #FFFFFF !important; }

        /* Barra lateral no estilo "Recentes" */
        section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
            padding-top: 0.5rem !important; padding-bottom: 0 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] { padding-top: 0 !important; }
        section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 0.5rem !important; }
        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.3rem !important; }

        .rotulo-recentes {
            font-size: 12px; color: #9A998F; margin: 2px 0 12px; padding-left: 4px;
        }
        section[data-testid="stSidebar"] .stButton button {
            border: none !important; background: transparent !important;
            text-align: left !important; justify-content: flex-start !important;
            padding: 6px 12px !important; border-radius: 8px !important;
            font-size: 14px !important; font-weight: 400 !important; color: #2B2B28 !important;
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

def render_hero() -> None:
    st.markdown('<div style="height: 6vh"></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-icone">{_icone_dashboard_svg()}</div>
            <div class="hero-titulo">Painel Analítico</div>
            <div class="hero-sub">Visão consolidada do escritório Cavalcante & Melo</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

PLOTLY_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="#FFFFFF",
    plot_bgcolor="#FFFFFF",
    font={"color": "#2B2B28", "family": "Georgia, serif"},
    margin={"t": 20, "b": 20, "l": 20, "r": 20},
    height=360,
)

def render_dashboard(client) -> None:

    # ── Métricas ─────────────────────────────────────────────────────────────
    try:
        prazos_geral = client.painel_prazos(dias=90)
        inadimplencia = client.painel_inadimplencia()
        documentos = client.painel_documentos()

        urgentes = sum(1 for p in prazos_geral if p["dias_restantes"] <= 7)
        total_em_aberto = sum(i["valor_em_aberto"] for i in inadimplencia)
        total_docs = sum(d["quantidade"] for d in documentos)

        c1, c2, c3 = st.columns(3)
        c1.metric(
            ":material/schedule: Prazos nos próximos 90 dias",
            len(prazos_geral),
            delta=f"{urgentes} urgentes" if urgentes else "Nenhum urgente",
            delta_color="inverse",
        )
        c2.metric(":material/payments: Total em aberto", f"R$ {total_em_aberto:,.2f}")
        c3.metric(":material/description: Documentos indexados", total_docs)

    except ApiError as e:
        st.error(f"Erro ao carregar métricas: {e}", icon=":material/error:")
        return

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Vis-1: Prazos ─────────────────────────────────────────────────────────
    with st.expander("Prazos por processo", expanded=True, icon=":material/schedule:"):
        c_sub, c_filtro = st.columns([3, 1])
        with c_sub:
            st.caption("Processos ordenados por urgência no período selecionado.")
        with c_filtro:
            dias = st.selectbox(
                "Período",
                options=[30, 60, 90],
                format_func=lambda d: f"Próximos {d} dias",
                key="filtro_prazos",
            )
        try:
            prazos = client.painel_prazos(dias=dias)
            if not prazos:
                st.info("Nenhum processo com prazo no período.", icon=":material/info:")
            else:
                df = pd.DataFrame(prazos)
                df["cor"] = df["dias_restantes"].apply(
                    lambda d: "Urgente (≤7d)" if d <= 7
                    else "Atenção (8–15d)" if d <= 15
                    else "Planejamento (16–30d)" if d <= 30
                    else "Monitoramento (31d+)"
                )
                fig = px.bar(
                    df,
                    x="dias_restantes",
                    y="numero_processo",
                    color="cor",
                    orientation="h",
                    color_discrete_map={
                        "Urgente (≤7d)": "#C24E28",        # Coral escuro/Telha
                        "Atenção (8–15d)": "#D49A44",      # Ocre/Mostarda
                        "Planejamento (16–30d)": "#CDB47A", # Areia
                        "Monitoramento (31d+)": "#62826C",  # Verde Sálvia
                    },
                    labels={"dias_restantes": "Dias restantes", "numero_processo": "Processo", "cor": "Urgência"},
                )
                fig.update_layout(**PLOTLY_LAYOUT)
                fig.update_yaxes(categoryorder="total ascending")
                st.plotly_chart(fig, use_container_width=True, theme=None)
        except ApiError as e:
            st.error(f"Erro: {e}", icon=":material/error:")

    # ── Vis-2: Inadimplência ──────────────────────────────────────────────────
    with st.expander("Inadimplência por cliente", expanded=True, icon=":material/payments:"):
        c_sub, c_filtro = st.columns([3, 1])
        with c_sub:
            st.caption("Valor total em aberto por cliente, ordenado do mais crítico.")
        with c_filtro:
            top_n = st.selectbox(
                "Exibir",
                options=[5, 10, 20],
                format_func=lambda n: f"Top {n} clientes",
                key="filtro_inadimplencia",
            )
        try:
            if not inadimplencia:
                st.info("Nenhum honorário em atraso.", icon=":material/info:")
            else:
                df = pd.DataFrame(inadimplencia).head(top_n)
                fig = px.bar(
                    df,
                    x="nome_cliente",
                    y="valor_em_aberto",
                    color_discrete_sequence=["#D85A30"], # Coral da marca
                    labels={"nome_cliente": "Cliente", "valor_em_aberto": "Valor em aberto (R$)"},
                    custom_data=["quantidade_honorarios"],
                )
                fig.update_traces(
                    hovertemplate="<b>%{x}</b><br>R$ %{y:,.2f}<br>Parcelas em atraso: %{customdata[0]}<extra></extra>"
                )
                fig.update_layout(**PLOTLY_LAYOUT)
                fig.update_xaxes(categoryorder="total descending")
                st.plotly_chart(fig, use_container_width=True, theme=None)
        except ApiError as e:
            st.error(f"Erro: {e}", icon=":material/error:")

    # ── Vis-3: Documentos ─────────────────────────────────────────────────────
    with st.expander("Documentos por tipo", expanded=True, icon=":material/description:"):
        st.caption("Cobertura da base de conhecimento do escritório.")
        try:
            if not documentos:
                st.info("Nenhum documento indexado.", icon=":material/info:")
            else:
                df = pd.DataFrame(documentos)
                df["tipo_documento"] = df["tipo_documento"].str.strip().str.title()
                fig = px.bar(
                    df,
                    x="tipo_documento",
                    y="quantidade",
                    color_discrete_sequence=["#807E75"], # Cinza quente elegante
                    labels={"tipo_documento": "Tipo", "quantidade": "Chunks indexados"},
                )
                fig.update_layout(**PLOTLY_LAYOUT)
                fig.update_xaxes(categoryorder="total descending")
                st.plotly_chart(fig, use_container_width=True, theme=None)
        except ApiError as e:
            st.error(f"Erro: {e}", icon=":material/error:")

    # ── Vis-4: Carteira ───────────────────────────────────────────────────────
    with st.expander("Carteira por advogado", expanded=True, icon=":material/badge:"):
        c_sub, c_filtro = st.columns([3, 1])
        with c_sub:
            st.caption("Distribuição de processos por advogado e status.")
        with c_filtro:
            status_opcoes = ["Todos", "ativo", "suspenso", "em_recurso", "encerrado", "acordo"]
            status_sel = st.selectbox(
                "Status",
                options=status_opcoes,
                format_func=lambda s: "Todos" if s == "Todos" else s.replace("_", " ").capitalize(),
                key="filtro_carteira",
            )
        try:
            carteira = client.painel_carteira()
            if not carteira:
                st.info("Nenhum processo encontrado.", icon=":material/info:")
            else:
                df = pd.DataFrame(carteira)
                if status_sel != "Todos":
                    df = df[df["status"] == status_sel]
                fig = px.bar(
                    df,
                    x="advogado",
                    y="quantidade",
                    color="status",
                    barmode="stack",
                    color_discrete_map={
                        "ativo": "#62826C",        # Verde Sálvia
                        "suspenso": "#D49A44",     # Ocre
                        "em_recurso": "#C24E28",   # Coral escuro
                        "encerrado": "#9A998F",    # Cinza Muted
                        "acordo": "#50727B",       # Azul Ardósia
                    },
                    labels={"advogado": "Advogado", "quantidade": "Processos", "status": "Status"},
                )
                fig.update_layout(**PLOTLY_LAYOUT)
                st.plotly_chart(fig, use_container_width=True, theme=None)
        except ApiError as e:
            st.error(f"Erro: {e}", icon=":material/error:")

# ── Execução ──────────────────────────────────────────────────────────────────
render_sidebar_conversas(destino_agente=True)
render_status_conexao()
aplicar_estilos()
render_hero()
render_dashboard(get_client())