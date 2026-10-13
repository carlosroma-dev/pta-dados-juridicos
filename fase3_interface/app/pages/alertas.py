"""Aba de Alertas — configuração e disparo de alertas por email.

Permite pré-visualizar quais processos seriam alertados (dry_run),
disparar o envio de emails e consultar o histórico de execuções.
"""

from datetime import datetime

import streamlit as st

from services.api_client import ApiError, get_client
from components.sidebar_conversas import render_sidebar_conversas
from components.connection_status import render_status_conexao

# ── SVGs Inline ───────────────────────────────────────────────────────────────

def _icone_alertas_svg() -> str:
    # Sino de notificação (FILL 0)
    return '''<svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px" fill="currentColor"><path d="M480-120q-33 0-56.5-23.5T400-200h160q0 33-23.5 56.5T480-120Zm-120-120v-80h240v80H360Zm-80-120v-224q0-68 44-118t106-62v-26q0-13 8.5-21.5T480-800q13 0 21.5 8.5T510-770v26q62 12 106 62t44 118v224h80v80H200v-80h80Zm80-80h400v-144q0-84-58-142t-142-58q-84 0-142 58t-58 142v144Zm200 0Z"/></svg>'''

def _icone_person_svg() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 -960 960 960" width="18px" fill="#2B2B28" style="vertical-align: text-bottom; margin-right: 6px;"><path d="M480-480q-66 0-113-47t-47-113q0-66 47-113t113-47q66 0 113 47t47 113q0 66-47 113t-113 47ZM160-160v-112q0-34 17.5-62.5T224-378q62-31 126-46.5T480-440q66 0 130 15.5T736-378q29 15 46.5 43.5T800-272v112H160Zm80-80h480v-32q0-11-5.5-20T700-306q-54-27-109-40.5T480-360q-56 0-111 13.5T260-306q-9 5-14.5 14t-5.5 20v32Zm240-320q33 0 56.5-23.5T560-640q0-33-23.5-56.5T480-720q-33 0-56.5 23.5T400-640q0 33 23.5 56.5T480-560Zm0-80Zm0 400Z"/></svg>'''

def _icone_visibility_svg() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" height="16px" viewBox="0 -960 960 960" width="16px" fill="#9A998F" style="vertical-align: text-bottom; margin-right: 6px;"><path d="M480-320q75 0 127.5-52.5T660-500q0-75-52.5-127.5T480-680q-75 0-127.5 52.5T300-500q0 75 52.5 127.5T480-320Zm0-72q-45 0-76.5-31.5T372-500q0-45 31.5-76.5T480-608q45 0 76.5 31.5T588-500q0 45-31.5 76.5T480-392Zm0 192q-146 0-266-81.5T40-500q54-137 174-218.5T480-800q146 0 266 81.5T920-500q-54 137-174 218.5T480-200Zm0-300Zm0 220q113 0 207.5-59.5T832-500q-50-101-144.5-160.5T480-720q-113 0-207.5 59.5T128-500q50 101 144.5 160.5T480-280Z"/></svg>'''

def _icone_mail_svg() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" height="16px" viewBox="0 -960 960 960" width="16px" fill="#D85A30" style="vertical-align: text-bottom; margin-right: 6px;"><path d="M160-160q-33 0-56.5-23.5T80-240v-480q0-33 23.5-56.5T160-800h640q33 0 56.5 23.5T880-720v480q0 33-23.5 56.5T800-160H160Zm320-280L160-640v400h640v-400L480-440Zm0-80 320-200H160l320 200ZM160-640v-80 480-400Z"/></svg>'''


# ── Estilos ───────────────────────────────────────────────────────────────────

def _aplicar_estilos() -> None:
    st.markdown("""
    <style>
    .block-container { padding-top: 2rem; max-width: 900px; }
    
    [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

    /* Estilo Hero padronizado */
    .hero { text-align: center; margin-bottom: 2.5rem; }
    .hero-icone {
        width: 68px; height: 68px; border-radius: 50%;
        background: #FAECE7; color: #D85A30;
        display: flex; align-items: center; justify-content: center;
        margin: 0 auto 16px;
    }
    .hero-icone svg { width: 34px; height: 34px; }
    .hero-titulo {
        font-family: Georgia, "Times New Roman", serif;
        font-size: 36px; font-weight: 500; color: #2B2B28; margin-bottom: 8px;
    }
    .hero-sub { font-size: 16px; color: #9A998F; }

    /* Métricas */
    .stat-box {
        background: #FAF9F5; border-radius: 8px;
        padding: 0.8rem 1.2rem; text-align: center;
        border: 1px solid #E8E6DD;
    }
    .stat-box .valor {
        font-size: 1.8rem; font-weight: bold;
        color: #D85A30; font-family: Georgia, serif;
    }
    .stat-box .label { font-size: 0.8rem; color: #6B6A62; }

    /* Outros componentes */
    .advogado-titulo {
        font-family: Georgia, serif; font-size: 1.1rem;
        font-weight: bold; color: #2B2B28; margin: 1.5rem 0 0.5rem;
    }
    .historico-linha {
        background: #FFFFFF;
        border: 1px solid #F0EEE6;
        border-radius: 12px;
        padding: 14px 20px;
        margin-bottom: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        font-size: 0.95rem; color: #2B2B28;
    }
    
    /* Expanders */
    [data-testid="stExpander"] {
        background: #FFFFFF;
        border-radius: 12px !important;
        border: 1px solid #F0EEE6 !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }
    </style>
    """, unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _formatar_data(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return iso


def _renderizar_grupos(grupos: dict) -> None:
    """Tabela de processos agrupados por advogado."""
    if not grupos:
        st.info("Nenhum processo com prazo no período selecionado.", icon=":material/info:")
        return

    for advogado, processos in grupos.items():
        st.markdown(
            f"<div class='advogado-titulo'>{_icone_person_svg()}{advogado} — {len(processos)} processo(s)</div>",
            unsafe_allow_html=True,
        )
        st.dataframe(
            [
                {
                    "Processo": p.get("numero_processo", "—"),
                    "Prazo":    p.get("prazo_proximo", "—"),
                    "Status":   p.get("status", "—"),
                }
                for p in processos
            ],
            use_container_width=True,
            hide_index=True,
        )


def _renderizar_metricas(resultado: dict) -> None:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class='stat-box'>
            <div class='valor'>{resultado['processos_encontrados']}</div>
            <div class='label'>Processos encontrados</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class='stat-box'>
            <div class='valor'>{len(resultado.get('grupos', {}))}</div>
            <div class='label'>Advogados notificados</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class='stat-box'>
            <div class='valor'>{resultado['emails_enviados']}</div>
            <div class='label'>Emails enviados</div>
        </div>""", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)


# ── Página ────────────────────────────────────────────────────────────────────

def main() -> None:
    # Adicionando a sidebar consistente com o resto do app
    render_sidebar_conversas(destino_agente=True)
    render_status_conexao()
    _aplicar_estilos()

    # Novo Hero alinhado com as demais páginas
    st.markdown('<div style="height: 6vh"></div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-icone">{_icone_alertas_svg()}</div>
            <div class="hero-titulo">Central de Alertas</div>
            <div class="hero-sub">Configure e dispare alertas de prazos processuais por email para os advogados do escritório.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    client = get_client()

    # ── Configuração ──────────────────────────────────────────────────────────
    st.markdown("### Configuração")

    col_slider, col_info = st.columns([2, 1])
    with col_slider:
        n_dias = st.slider(
            "Janela de antecedência (dias)",
            min_value=1, max_value=90, value=7, step=1,
            help="Alertar sobre processos com prazo vencendo nos próximos N dias.",
        )
    with col_info:
        st.markdown("<br>", unsafe_allow_html=True)
        st.info(f"Prazos que vencem nos **próximos {n_dias} dias**.", icon=":material/date_range:")

    # ── Emails dos advogados ──────────────────────────────────────────────────
    try:
        emails_config = client.get_emails_advogados()
    except ApiError:
        emails_config = {}

    with st.expander("Configurar emails dos advogados", expanded=False, icon=":material/mail:"):
        emails_editados: dict[str, str | None] = {}

        if not emails_config:
            st.caption("Nenhum advogado encontrado na configuração.")
        else:
            for advogado, email_atual in emails_config.items():
                emails_editados[advogado] = st.text_input(
                    label=advogado,
                    value=email_atual,
                    key=f"email_{advogado}",
                )

        if st.button("Salvar emails", disabled=not emails_editados, icon=":material/save:"):
            try:
                client.salvar_emails_advogados(emails_editados)
                emails_config = emails_editados
                st.success("Emails salvos com sucesso.", icon=":material/check_circle:")
            except ApiError as e:
                st.error(f"Erro ao salvar: {e}", icon=":material/error:")

    # ── Botões ────────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    col_a, col_b, _ = st.columns([1, 1, 2])
    with col_a:
        preview_clicado = st.button(
            "Pré-visualizar",
            use_container_width=True,
            icon=":material/visibility:",
            help="Mostra os processos que seriam alertados, sem enviar emails.",
        )
    with col_b:
        disparar_clicado = st.button(
            "Disparar alertas",
            use_container_width=True,
            type="primary",
            icon=":material/send:",
            help="Envia os emails de alerta para os advogados responsáveis.",
        )

    # ── Ações ─────────────────────────────────────────────────────────────────
    if preview_clicado:
        with st.spinner("Buscando processos com prazo próximo..."):
            try:
                resultado = client.disparar_alertas(
                    n_dias=n_dias,
                    dry_run=True,
                    emails_advogados=emails_config,
                )
            except ApiError as e:
                st.error(f"Erro ao consultar a API: {e}", icon=":material/error:")
                resultado = None

        if resultado:
            st.success(
                f"**{resultado['processos_encontrados']} processo(s)** encontrado(s). "
                "Nenhum email foi enviado.",
                icon=":material/info:"
            )
            _renderizar_grupos(resultado.get("grupos", {}))

    elif disparar_clicado:
        with st.spinner("Enviando alertas por email..."):
            try:
                resultado = client.disparar_alertas(
                    n_dias=n_dias,
                    dry_run=False,
                    emails_advogados=emails_config,
                )
            except ApiError as e:
                st.error(f"Erro ao disparar alertas: {e}", icon=":material/error:")
                resultado = None

        if resultado:
            _renderizar_metricas(resultado)
            st.success(f"Alertas disparados em {_formatar_data(resultado['executado_em'])}.", icon=":material/check_circle:")
            _renderizar_grupos(resultado.get("grupos", {}))

    # ── Histórico ─────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Histórico de execuções")

    cols = st.columns([4, 1])
    cols[1].button("Atualizar", use_container_width=True, icon=":material/refresh:")

    try:
        historico = client.historico_alertas()
    except ApiError as e:
        st.error(f"Erro ao carregar histórico: {e}", icon=":material/error:")
        historico = []

    if not historico:
        st.caption("Nenhuma execução registrada ainda.")
    else:
        for entrada in historico[:10]:
            dry = entrada.get("dry_run", False)
            icone_html = _icone_visibility_svg() if dry else _icone_mail_svg()
            tipo_texto = 'Pré-visualização' if dry else 'Disparo real'
            
            st.markdown(
                f"<div class='historico-linha'>"
                f"{icone_html} "
                f"<strong>{tipo_texto}</strong>"
                f" — {_formatar_data(entrada.get('executado_em', ''))} &nbsp;|&nbsp; "
                f"Janela: {entrada.get('n_dias', '?')} dias &nbsp;|&nbsp; "
                f"{entrada.get('processos_encontrados', 0)} processo(s) &nbsp;|&nbsp; "
                f"{entrada.get('emails_enviados', 0)} email(s)"
                f"</div>",
                unsafe_allow_html=True,
            )

main()