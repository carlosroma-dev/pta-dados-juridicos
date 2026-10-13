from pydantic import BaseModel, Field
from typing import Optional, List

class DocumentoEstruturado(BaseModel):
    """
    Modelo para extração de informações fundamentais dos documentos
    """
    numero_processo: Optional[str] = Field(
        description="Número do processo no padrão CNJ (ex: 0000000-00.0000.0.00.0000)"
    )
    tipo_documento: str = Field(
        description="Classificação do documento (ex: Petição Inicial, Contrato de Honorários, Acordo, Intimação)"
    )
    data_documento: Optional[str] = Field(
        description="Data principal identificada no documento no formato YYYY-MM-DD"
    )
    partes: List[str] = Field(
        description="Lista com os nomes completos das partes envolvidas (Autor, Réu, Contratante, etc)"
    )
    valor: Optional[float] = Field(
        description="Valor monetário principal mencionado (valor da causa ou honorários)"
    )
    conteudo: str = Field(
        description="Retorna o conteúdo integral do documento"
    )