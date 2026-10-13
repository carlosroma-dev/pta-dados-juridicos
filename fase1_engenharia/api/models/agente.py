from typing import Literal
from pydantic import BaseModel, Field


class Mensagem(BaseModel):
    papel: Literal["user", "assistant"]
    conteudo: str


class AgenteRequest(BaseModel):
    pergunta: str = Field(
        ...,
        min_length=1,
        description="Pergunta em linguagem natural para o agente jurídico",
    )
    session_id: str | None = Field(
        default=None,
        description="ID da sessão para manter histórico. Omita para iniciar nova sessão.",
    )


class AgenteResponse(BaseModel):
    pergunta: str = Field(..., description="Pergunta original enviada ao agente")
    resposta: str = Field(..., description="Resposta gerada pelo agente")
    rota: str = Field(..., description="Rota escolhida pelo grafo: relacional, vetorial ou ambigua")
    validado: bool = Field(..., description="Se a resposta passou pelo nó de validação")
    status: str = Field("ok", description="Status da requisição")
    session_id: str = Field(..., description="ID da sessão — reenvie nas próximas requisições")
