"""Aba de upload e ingestão de novos documentos PDF (Fase 3).

Permite ao operador (Antônio) enviar um PDF pela interface sem precisar de
terminal ou intervenção técnica. O pipeline completo (extrair → estruturar →
indexar) roda em background na FastAPI; a interface acompanha o progresso em
tempo real via polling e exibe o resultado ou o erro em linguagem simples.

Fluxo:
    1. Operador seleciona um PDF e clica em "Enviar documento".
    2. A FastAPI registra o documento e dispara o pipeline em background (202).
    3. A interface faz polling em GET /documentos/{id} a cada 1,5s, atualizando
       o st.status com a etapa corrente.
    4. Ao concluir, exibe confirmação. Em caso de erro, exibe mensagem amigável.
    5. A seção "Últimos envios" lista o histórico de ingestões.

Toda comunicação passa pelo ApiClient — a página nunca toca no banco diretamente.
"""

from __future__ import annotations

import time

import streamlit as st

from components.connection_status import render_status_conexao
from components.sidebar_conversas import render_sidebar_conversas
from services.api_client import ApiError, get_client

# ── Constantes ────────────────────────────────────────────────────────────────

# O que o operador vê na tela para cada status vindo da API.
_ROTULOS: dict[str, str] = {
    "recebido":     "Aguardando processamento...",
    "extraindo":    "Extraindo texto do PDF...",
    "estruturando": "Interpretando o documento com IA...",
    "indexando":    "Indexando documento para consulta...",
    "concluido":    "Pronto — documento disponível para consulta!",
    "erro":         "Não foi possível processar o documento.",
}

# Substituído por Material Symbols
_ICONES: dict[str, str] = {
    "recebido":     ":material/schedule:",
    "extraindo":    ":material/description:",
    "estruturando": ":material/psychology:",
    "indexando":    ":material/database:",
    "concluido":    ":material/check_circle:",
    "erro":         ":material/error:",
}

INTERVALO_POLLING = 1.5   # segundos entre consultas de status
MAX_ITERACOES = 120       # ~3 min de timeout — segurança contra loop infinito


# ── SVGs Inline ───────────────────────────────────────────────────────────────

def _icone_upload_svg() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px" fill="currentColor"><path d="M260-160q-91 0-155.5-63T40-377q0-78 47-139t123-78q25-92 100-149t170-57q117 0 198.5 81.5T760-520q69 8 114.5 59.5T920-340q0 75-52.5 127.5T740-160H520q-33 0-56.5-23.5T440-240v-206l-64 62-56-56 160-160 160 160-56 56-64-62v206h220q42 0 71-29t29-71q0-42-29-71t-71-29h-60v-80q0-83-58.5-141.5T480-720q-83 0-141.5 58.5T280-520h-20q-58 0-99 41t-41 99q0 58 41 99t99 41h100v80H260Z"/></svg>'''

def _icone_doc_svg() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" height="16px" viewBox="0 -960 960 960" width="16px" fill="#9A998F" style="vertical-align: text-bottom; margin-right: 4px;"><path d="M320-240h320v-80H320v80Zm0-160h320v-80H320v80ZM240-80q-33 0-56.5-23.5T160-160v-640q0-33 23.5-56.5T240-880h320l240 240v480q0 33-23.5 56.5T760-80H240Zm280-520v-200H240v640h520v-440H520ZM240-800v200-200 640-640Z"/></svg>'''


# ── Estilos ───────────────────────────────────────────────────────────────────

def aplicar_estilos() -> None:
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2rem; max-width: 860px; }

        [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

        .hero { text-align: center; margin-bottom: 2rem; }
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

        /* Card de upload */
        .upload-card {
            background: #FFFFFF;
            border: 1px solid #F0EEE6;
            border-radius: 16px;
            padding: 32px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.07);
            margin-bottom: 24px;
        }

        /* Badge de status no histórico - Sem emojis */
        .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 99px;
            font-size: 12px;
            font-weight: 500;
        }
        .badge-concluido  { background: #E8F5E9; color: #2E7D32; }
        .badge-erro       { background: #FFEBEE; color: #C62828; }
        .badge-processando { background: #FFF3E0; color: #E65100; }
        .badge-recebido   { background: #F3F4F6; color: #6B7280; }

        /* Linha do histórico */
        .hist-row {
            background: #FFFFFF;
            border: 1px solid #F0EEE6;
            border-radius: 12px;
            padding: 14px 20px;
            margin-bottom: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .hist-nome  { font-size: 14px; font-weight: 500; color: #2B2B28; }
        .hist-meta  { font-size: 12px; color: #9A998F; margin-top: 2px; }

        /* Barra lateral (igual às outras abas) */
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
            <div class="hero-icone">{_icone_upload_svg()}</div>
            <div class="hero-titulo">Adicionar Documento</div>
            <div class="hero-sub">Envie um PDF para que ele fique disponível para consulta no chat.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Polling ───────────────────────────────────────────────────────────────────

def _polling(client, id_ingestao: int) -> dict:
    """Faz polling de GET /documentos/{id} até concluido ou erro.

    Atualiza um `st.status` a cada etapa e devolve o registro final.
    Limita a MAX_ITERACOES iterações para não travar a interface indefinidamente.
    """
    with st.status(_ROTULOS["recebido"], expanded=True) as s:
        etapa_anterior = ""
        for _ in range(MAX_ITERACOES):
            try:
                dados = client.status_ingestao(id_ingestao)
            except ApiError as e:
                s.update(label="Erro ao verificar o status.", state="error")
                st.error(str(e), icon=":material/error:")
                return {}

            status = dados.get("status", "recebido")
            rotulo = _ROTULOS.get(status, "Processando...")

            if status != etapa_anterior:
                s.update(label=rotulo)
                if status not in ("concluido", "erro"):
                    icone = _ICONES.get(status, ":material/hourglass_empty:")
                    st.write(f"{icone} {rotulo}")
                etapa_anterior = status

            if status == "concluido":
                s.update(label=rotulo, state="complete")
                return dados

            if status == "erro":
                s.update(label=rotulo, state="error")
                st.error(
                    dados.get("mensagem_erro")
                    or "Erro inesperado. Tente novamente em instantes.",
                    icon=":material/error:"
                )
                return dados

            time.sleep(INTERVALO_POLLING)

        # Timeout de segurança
        s.update(label="O processamento está demorando mais que o esperado.", state="error")
        return {}


# ── Upload ────────────────────────────────────────────────────────────────────

def render_upload(client) -> None:
    """Formulário de upload + ciclo de polling."""
    arquivo = st.file_uploader(
        "Selecione um arquivo PDF",
        type=["pdf"],
        help="Máximo de 25 MB. Apenas arquivos PDF com texto selecionável.",
        label_visibility="collapsed",
    )

    if arquivo:
        st.caption(f":material/description: **{arquivo.name}** — {arquivo.size / 1024:.1f} KB")
        if st.button("Enviar documento", type="primary", use_container_width=True, icon=":material/upload_file:"):
            try:
                with st.spinner("Enviando..."):
                    resultado = client.ingerir_documento(arquivo.read(), arquivo.name)
                id_ingestao = resultado.get("id_ingestao")
                if id_ingestao is None:
                    st.error("Resposta inesperada da API. Tente novamente.", icon=":material/error:")
                else:
                    dados_finais = _polling(client, id_ingestao)
                    if dados_finais.get("status") == "concluido":
                        chunks = dados_finais.get("num_chunks", 0)
                        tipo = dados_finais.get("tipo_documento") or "—"
                        if chunks == 0:
                            chunk_msg = "Documento já estava indexado — continua disponível para consulta."
                        else:
                            chunk_msg = f"{chunks} trecho(s) novos indexados para consulta."
                        st.success(
                            f"**{arquivo.name}** foi processado com sucesso. "
                            f"{chunk_msg} "
                            f"Tipo identificado: *{tipo}*.",
                            icon=":material/check_circle:"
                        )
            except ApiError as e:
                st.error(str(e), icon=":material/error:")


# ── Histórico ─────────────────────────────────────────────────────────────────

def _badge(status: str) -> str:
    if status == "concluido":
        return '<span class="badge badge-concluido">concluído</span>'
    if status == "erro":
        return '<span class="badge badge-erro">erro</span>'
    if status == "recebido":
        return '<span class="badge badge-recebido">recebido</span>'
    return f'<span class="badge badge-processando">{status}</span>'


def render_historico(client) -> None:
    """Últimos documentos enviados — do mais recente ao mais antigo."""
    st.markdown("---")
    st.markdown("##### Últimos envios")

    try:
        ingestoes = client.listar_ingestoes(limite=10)
    except ApiError as e:
        st.warning(f"Não foi possível carregar o histórico: {e}", icon=":material/warning:")
        return

    if not ingestoes:
        st.caption("Nenhum documento enviado ainda.")
        return

    for item in ingestoes:
        nome = item.get("nome_original") or item.get("nome_arquivo") or "—"
        status = item.get("status", "—")
        data = (item.get("data_ingestao") or "")[:16].replace("T", " ")
        tipo = item.get("tipo_documento") or "—"
        chunks = item.get("num_chunks")
        if chunks is None:
            chunks_str = "—"
        elif chunks == 0:
            chunks_str = "já indexado"
        else:
            chunks_str = f"{chunks} trecho(s)"

        st.markdown(
            f"""
            <div class="hist-row">
                <div class="hist-nome">{_icone_doc_svg()}{nome} &nbsp; {_badge(status)}</div>
                <div class="hist-meta">
                    {data} &nbsp;·&nbsp; Tipo: {tipo} &nbsp;·&nbsp; {chunks_str}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── Execução ──────────────────────────────────────────────────────────────────

render_sidebar_conversas(destino_agente=True)
render_status_conexao()
aplicar_estilos()
render_hero()

client = get_client()
render_upload(client)
render_historico(client)