from pydantic import BaseModel, Field


class BuscaRequest(BaseModel):
    pergunta: str = Field(..., description="Texto da consulta em linguagem natural")
    top_k: int = Field(5, ge=1, le=20, description="Número de chunks a retornar (1-20)")


class ChunkOut(BaseModel):
    conteudo: str
    # Distância cosseno do pgvector: 0 = idêntico, 2 = oposto
    distancia: float
