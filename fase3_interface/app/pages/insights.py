from __future__ import annotations

import os
import time
from typing import Any

import streamlit as st
from openai import OpenAI

from components.connection_status import render_status_conexao
from components.sidebar_conversas import render_sidebar_conversas
from services.api_client import get_client

# ── Configuração ──────────────────────────────────────────────────────────────

_MODELO_LLM = os.getenv("LLM_MODEL", "gpt-5.4-mini-2026-03-17")

_PROMPT_SISTEMA = """Você é um analista jurídico sênior especializado em identificar padrões
em grandes volumes de documentos legais. Você recebe trechos de documentos jurídicos
de um escritório de advocacia e deve produzir insights estratégicos.

Seu objetivo NÃO é resumir os documentos. É identificar:
- Padrões que aparecem em múltiplos documentos
- Tendências preocupantes ou positivas
- Inconsistências ou riscos sistêmicos
- Oportunidades de atenção que um advogado deveria notar
- Qualquer observação que surpreenda ou mereça destaque

Responda APENAS com JSON válido, sem markdown, sem texto fora do JSON.
O formato deve ser exatamente:
{
  "insights": [
    {
      "titulo": "título curto e direto",
      "icone": "nome de um ícone do Google Material Symbols (ex: lightbulb, warning, trending_up, gavel, policy, balance)",
      "descricao": "observação detalhada em 2-3 frases, com exemplos concretos dos documentos",
      "relevancia": "alta" | "media" | "baixa"
    }
  ],
  "resumo_geral": "Uma frase sintetizando o estado geral da base de documentos."
}

Gere entre 4 e 7 insights. Priorize qualidade e especificidade — evite generalidades."""


# ── SVGs Inline ───────────────────────────────────────────────────────────────

def _icone_insights_svg() -> str:
    # Lâmpada vazada (FILL 0)
    return '''<svg xmlns="http://www.w3.org/2000/svg" height="24px" viewBox="0 -960 960 960" width="24px" fill="currentColor"><path d="M480-120q-33 0-56.5-23.5T400-200h160q0 33-23.5 56.5T480-120Zm-80-120v-80h160v80H400Zm80-120q-76 0-134.5-51T280-554q0-42 19.5-79t53.5-62q25-20 40.5-47t15.5-58q0-41 29-70t70-29q41 0 70 29t29 70q0 31 15.5 58t40.5 47q34 25 53.5 62t19.5 79q0 62-58.5 113T480-360Zm0-80q50-46 75-86t25-78q0-42-29-71t-71-29q-42 0-71 29t-29 71q0 38 25 78t75 86Zm0-174Z"/></svg>'''

def _icone_quote_svg() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" height="20px" viewBox="0 -960 960 960" width="20px" fill="#D85A30" style="vertical-align: text-bottom; margin-right: 8px;"><path d="M240-400h320v-80H240v80Zm0-120h480v-80H240v80Zm0-120h480v-80H240v80ZM80-80v-720q0-33 23.5-56.5T160-880h640q33 0 56.5 23.5T880-800v480q0 33-23.5 56.5T800-240H240L80-80Zm126-240h594v-480H160v525l46-45Zm-46 0v-480 480Z"/></svg>'''


# ── Estilos ───────────────────────────────────────────────────────────────────

def aplicar_estilos() -> None:
    st.markdown(
        """
        <style>
        /* Importando a fonte Material Symbols do Google com FILL 0 (vazado) */
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0');

        .block-container { padding-top: 2rem; max-width: 900px; }

        [data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

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

        /* Card de insight */
        .insight-card {
            background: #FFFFFF;
            border: 1px solid #F0EEE6;
            border-radius: 16px;
            padding: 24px 28px;
            margin-bottom: 16px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
            transition: box-shadow 0.2s;
        }
        .insight-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.10); }

        .insight-header {
            display: flex; align-items: center; gap: 12px; margin-bottom: 10px;
        }
        .insight-icone {
            font-family: 'Material Symbols Rounded', sans-serif;
            font-size: 26px; line-height: 1;
            color: #D85A30; 
            font-variation-settings: 'FILL' 0; /* Ícones vazados */
        }
        .insight-titulo {
            font-family: Georgia, "Times New Roman", serif;
            font-size: 18px; font-weight: 500; color: #2B2B28;
        }
        .insight-descricao {
            font-size: 15px; color: #4A4A45; line-height: 1.6; margin: 0;
        }

        /* Badge de relevância */
        .badge-relevancia {
            display: inline-block;
            padding: 2px 10px; border-radius: 99px;
            font-size: 11px; font-weight: 600;
            text-transform: uppercase; letter-spacing: 0.05em;
            margin-top: 12px;
        }
        .badge-alta    { background: #FFEBEE; color: #C62828; }
        .badge-media   { background: #FFF3E0; color: #E65100; }
        .badge-baixa   { background: #F3F4F6; color: #6B7280; }

        /* Resumo geral */
        .resumo-card {
            background: #F5F3EC;
            border-left: 4px solid #D85A30;
            border-radius: 0 12px 12px 0;
            padding: 16px 20px;
            margin-bottom: 28px;
            font-size: 15px; color: #2B2B28; font-style: italic;
        }

        /* Barra lateral */
        section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {
            padding-top: 0.5rem !important; padding-bottom: 0 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"]  { padding-top: 0 !important; }
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
            <div class="hero-icone">{_icone_insights_svg()}</div>
            <div class="hero-titulo">Insights do Agente</div>
            <div class="hero-sub">
                Padrões e tendências identificados automaticamente nos documentos indexados.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Coleta de contexto ────────────────────────────────────────────────────────

def _coletar_contexto(client) -> str:
    """Busca todos os chunks indexados para análise autônoma completa."""
    resposta = client.todos_chunks()
    chunks = resposta.get("chunks", []) if isinstance(resposta, dict) else []
    trechos = [item["conteudo"].strip() for item in chunks if item.get("conteudo")]
    return "\n\n---\n\n".join(trechos)


# ── Geração de insights ───────────────────────────────────────────────────────

def _gerar_insights(contexto: str) -> dict[str, Any]:
    """Chama o LLM via OpenAI e devolve o JSON de insights parseado."""
    import json

    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY não encontrada no ambiente.")

    client = OpenAI(api_key=openai_key)

    mensagem_usuario = (
        f"Analise os seguintes trechos de documentos jurídicos indexados "
        f"e gere insights estratégicos conforme as instruções.\n\n"
        f"DOCUMENTOS:\n{contexto[:12000]}"  # limita para não estourar contexto
    )

    resposta = client.chat.completions.create(
        model=_MODELO_LLM,
        messages=[
            {"role": "system", "content": _PROMPT_SISTEMA},
            {"role": "user", "content": mensagem_usuario},
        ],
        temperature=0.4,
        max_completion_tokens=2000,
    )

    texto = resposta.choices[0].message.content.strip()

    # Remove possíveis cercas de markdown que o modelo possa ter incluído
    if texto.startswith("```"):
        texto = texto.split("```")[1]
        if texto.startswith("json"):
            texto = texto[4:]
    texto = texto.strip()

    return json.loads(texto)


# ── Renderização dos cards ────────────────────────────────────────────────────

def _badge(relevancia: str) -> str:
    cls = f"badge-{relevancia}" if relevancia in ("alta", "media", "baixa") else "badge-baixa"
    labels = {"alta": "Alta relevância", "media": "Média relevância", "baixa": "Baixa relevância"}
    return f'<span class="badge-relevancia {cls}">{labels.get(relevancia, relevancia)}</span>'


def render_insights(dados: dict[str, Any]) -> None:
    """Renderiza o resumo geral e os cards de insight."""
    resumo = dados.get("resumo_geral", "")
    if resumo:
        st.markdown(
            f'<div class="resumo-card">{_icone_quote_svg()}{resumo}</div>',
            unsafe_allow_html=True,
        )

    insights = dados.get("insights", [])
    for insight in insights:
        titulo = insight.get("titulo", "—")
        # Se a IA não trouxer o ícone, o fallback é uma lâmpada (lightbulb)
        icone = insight.get("icone", "lightbulb")
        descricao = insight.get("descricao", "")
        relevancia = insight.get("relevancia", "baixa")

        st.markdown(
            f"""
            <div class="insight-card">
                <div class="insight-header">
                    <span class="insight-icone">{icone}</span>
                    <span class="insight-titulo">{titulo}</span>
                </div>
                <p class="insight-descricao">{descricao}</p>
                {_badge(relevancia)}
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── Execução ──────────────────────────────────────────────────────────────────

render_sidebar_conversas(destino_agente=True)
render_status_conexao()
aplicar_estilos()
render_hero()

# Cache de sessão: evita regenerar a cada rerun trivial (ex: sidebar click).
# O botão "Atualizar" limpa o cache e força nova geração.
if "insights_dados" not in st.session_state:
    st.session_state["insights_dados"] = None
if "insights_erro" not in st.session_state:
    st.session_state["insights_erro"] = None

col_info, col_btn = st.columns([5, 1])
with col_info:
    st.caption("Os insights são gerados automaticamente a partir dos documentos indexados no banco vetorial.")
with col_btn:
    if st.button("Atualizar", icon=":material/refresh:", use_container_width=True):
        st.session_state["insights_dados"] = None
        st.session_state["insights_erro"] = None

# Gera na primeira vez (ou após atualizar)
if st.session_state["insights_dados"] is None and st.session_state["insights_erro"] is None:
    client = get_client()

    with st.status("Analisando documentos indexados...", expanded=True) as status:
        st.write(":material/search: Coletando amostra representativa dos documentos...")
        try:
            contexto = _coletar_contexto(client)
            if not contexto.strip():
                status.update(label="Nenhum documento encontrado.", state="error")
                st.session_state["insights_erro"] = (
                    "Não há documentos indexados no banco vetorial. "
                    "Adicione documentos pela aba **Adicionar Documento** primeiro."
                )
            else:
                st.write(f":material/library_books: {len(contexto.split('---'))} trechos coletados. Identificando padrões...")
                try:
                    dados = _gerar_insights(contexto)
                    st.session_state["insights_dados"] = dados
                    status.update(
                        label=f"{len(dados.get('insights', []))} insights identificados.",
                        state="complete",
                    )
                except Exception as e:
                    status.update(label="Erro ao gerar insights.", state="error")
                    st.session_state["insights_erro"] = f"Erro ao chamar o LLM: {e}"
        except Exception as e:
            status.update(label="Erro ao conectar à API.", state="error")
            st.session_state["insights_erro"] = str(e)

# Renderiza resultado ou erro
if st.session_state["insights_dados"]:
    render_insights(st.session_state["insights_dados"])
elif st.session_state["insights_erro"]:
    st.error(st.session_state["insights_erro"], icon=":material/error:")