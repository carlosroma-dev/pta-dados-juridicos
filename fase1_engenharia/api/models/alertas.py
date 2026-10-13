from pydantic import BaseModel
from typing import Optional


class AlertaDisparoRequest(BaseModel):
    n_dias: int = 7
    dry_run: bool = False   # True = preview sem enviar emails
    emails_advogados: dict[str, str] = {}

class AlertaDisparoResponse(BaseModel):
    executado_em: str
    n_dias: int
    dry_run: bool
    processos_encontrados: int
    emails_enviados: int
    grupos: dict            # advogado → lista de processos