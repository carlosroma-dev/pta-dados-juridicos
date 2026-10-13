"""Cliente HTTP único para falar com a FastAPI.

Princípio da arquitetura: **nenhuma aba acessa o banco diretamente**. Toda
leitura de dados passa por aqui, que por sua vez chama os endpoints REST da
Fase 1/Fase 2. Assim a interface fica desacoplada do banco e do ORM.

A autenticação é feita pelo header `X-API-Key`, exatamente como a FastAPI
espera em `fase1_engenharia/api/main.py`.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx
import streamlit as st

from config import Settings, get_settings


class ApiError(Exception):
    """Erro de comunicação ou de resposta da API, com mensagem amigável."""


class ApiClient:
    """Wrapper fino sobre `httpx` com um método por endpoint da API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        settings = settings or get_settings()
        self.base_url = (base_url or settings.api_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.api_key
        self.timeout = timeout if timeout is not None else settings.api_timeout

    # ── infra ─────────────────────────────────────────────────────────────
    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        # Só envia a chave se ela existir — em dev a API pode rodar sem auth.
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.request(method, url, headers=self._headers(), **kwargs)
        except httpx.RequestError as exc:
            raise ApiError(
                f"Não foi possível conectar à API em {self.base_url}. "
                f"Confirme que a FastAPI está rodando (uvicorn). Detalhe: {exc}"
            ) from exc

        if resp.status_code == 401:
            raise ApiError(
                "Autenticação falhou (401). Verifique se a API_KEY no .env "
                "é a mesma usada pela FastAPI."
            )
        if resp.status_code >= 400:
            raise ApiError(f"A API respondeu com erro {resp.status_code}: {resp.text}")

        try:
            return resp.json()
        except ValueError:
            return resp.text

    # ── health / conexão ──────────────────────────────────────────────────
    def health(self) -> Any:
        return self._request("GET", "/health")

    def verificar_conexao(self) -> tuple[bool, str]:
        """Testa conexão + autenticação chamando `/health` com a chave.

        `/health` está atrás da verificação global de X-API-Key na FastAPI,
        então um 200 aqui prova que o cliente conectou **e** autenticou.
        """
        try:
            self.health()
            return True, "Conectado e autenticado na API."
        except ApiError as exc:
            return False, str(exc)

    # ── Fase 1: dados do escritório ─────────────────────────────────────────
    def listar_clientes(self) -> Any:
        return self._request("GET", "/clientes/")

    def listar_processos(
        self, status: Optional[str] = None, cliente_id: Optional[int] = None
    ) -> Any:
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if cliente_id is not None:
            params["cliente_id"] = cliente_id
        return self._request("GET", "/processos/", params=params)

    def processos_por_prazo(self, dias: int = 30) -> Any:
        return self._request("GET", "/processos/prazos", params={"dias": dias})
    
    def painel_prazos(self, dias: int = 30) -> Any:
        return self._request("GET", "/painel/prazos", params={"dias": dias})

    def painel_inadimplencia(self) -> Any:
        return self._request("GET", "/painel/inadimplencia")

    def painel_documentos(self) -> Any:
        return self._request("GET", "/painel/documentos")

    def painel_carteira(self) -> Any:
        return self._request("GET", "/painel/carteira")

    def listar_honorarios(self, status_pagamento: Optional[str] = None) -> Any:
        params: dict[str, Any] = {}
        if status_pagamento:
            params["status_pagamento"] = status_pagamento
        return self._request("GET", "/honorarios/", params=params)

    def busca_semantica(self, pergunta: str, top_k: int = 5) -> Any:
        return self._request(
            "POST", "/busca/", json={"pergunta": pergunta, "top_k": top_k}
        )

    def todos_chunks(self, limite: int = 200) -> Any:
        return self._request("GET", "/busca/chunks", params={"limite": limite})

    # ── Fase 2: agente conversacional ───────────────────────────────────────
    def perguntar_agente(self, pergunta: str, session_id: str | None = None) -> Any:
        payload: dict[str, Any] = {"pergunta": pergunta}
        if session_id:
            payload["session_id"] = session_id
        return self._request("POST", "/agente/perguntar", json=payload)

    # ── Ingestão de documentos ───────────────────────────────────────────────
    def ingerir_documento(self, arquivo_bytes: bytes, nome_arquivo: str) -> Any:
        """Envia um PDF para ingestão.

        Devolve o registro criado com `id_ingestao` e `status='recebido'`.
        O processamento é assíncrono: use `status_ingestao(id)` para acompanhar.
        """
        return self._request(
            "POST",
            "/documentos/ingerir",
            files={"arquivo": (nome_arquivo, arquivo_bytes, "application/pdf")},
        )

    def status_ingestao(self, id_ingestao: int) -> Any:
        """Status atual de uma ingestão — usado pela interface no polling."""
        return self._request("GET", f"/documentos/{id_ingestao}")

    def listar_ingestoes(self, limite: int = 10) -> Any:
        """Últimas ingestões, da mais recente para a mais antiga."""
        return self._request("GET", "/documentos/", params={"limite": limite})

    # ── Alertas ──────────────────────────────────────────────────────────────────
    def disparar_alertas(
        self,
        n_dias: int = 7,
        dry_run: bool = False,
        emails_advogados: dict | None = None, 
    ) -> Any:
        payload: dict[str, Any] = {"n_dias": n_dias, "dry_run": dry_run}
        if emails_advogados:
            payload["emails_advogados"] = emails_advogados
        return self._request("POST", "/alertas/disparar", json=payload)

    def get_emails_advogados(self) -> Any:
        """Retorna a configuração atual de emails dos advogados."""
        return self._request("GET", "/alertas/emails")

    def salvar_emails_advogados(self, emails: dict[str, str]) -> Any:
        """Salva a configuração de emails dos advogados."""
        return self._request("PUT", "/alertas/emails", json=emails)


    def historico_alertas(self) -> Any:
        """Retorna as últimas execuções do workflow de alertas."""
        return self._request("GET", "/alertas/historico")

@st.cache_resource
def get_client() -> ApiClient:
    """Instância única do cliente, reaproveitada entre os reruns do Streamlit."""
    return ApiClient()