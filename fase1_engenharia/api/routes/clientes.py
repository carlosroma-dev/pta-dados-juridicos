from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fase1_engenharia.db.database import get_db
from fase1_engenharia.db.models import Cliente, ClienteOut

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.get("/")
def listar_clientes(db: Session = Depends(get_db)):
    try:
        clientes = db.query(Cliente).all()
        dados = [ClienteOut.model_validate(c).model_dump() for c in clientes]
        return {"dados": dados, "total": len(dados), "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
