# fase1_engenharia/api/models/painel.py

from pydantic import BaseModel
from datetime import date

class ItemPrazo(BaseModel):
    numero_processo: str
    dias_restantes: int
    prazo_proximo: date 
    status: str | None
    vara: str | None


class ItemInadimplencia(BaseModel):
    nome_cliente: str
    valor_em_aberto: float
    quantidade_honorarios: int


class ItemDocumento(BaseModel):
    tipo_documento: str
    quantidade: int


class ItemCarteira(BaseModel):
    advogado: str
    status: str
    quantidade: int