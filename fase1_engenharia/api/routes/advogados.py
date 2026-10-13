from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from fase1_engenharia.db.database import get_db
from fase1_engenharia.db.models import Advogado

router = APIRouter(prefix="/advogados", tags=["advogados"])


class AdvogadoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_advogado: int
    nome: str


@router.get("/")
def listar_advogados(db: Session = Depends(get_db)):
    try:
        advogados = db.query(Advogado).order_by(Advogado.nome).all()
        dados = [AdvogadoOut.model_validate(a).model_dump() for a in advogados]
        return {"dados": dados, "total": len(dados), "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))