from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from fase1_engenharia.api.models.enums import StatusProcesso
from fase1_engenharia.db.database import get_db
from fase1_engenharia.db.models import Processo, ProcessoOut

router = APIRouter(prefix="/processos", tags=["processos"])


# /prazos deve vir antes de / para o FastAPI não confundir a rota
@router.get("/prazos")
def processos_por_prazo(
    dias: int = Query(30, description="Número de dias a partir de hoje"),
    db: Session = Depends(get_db),
):
    try:
        hoje = date.today()
        limite = hoje + timedelta(days=dias)
        processos = (
            db.query(Processo)
            .filter(Processo.prazo_proximo >= hoje, Processo.prazo_proximo <= limite)
            .all()
        )
        dados = [ProcessoOut.model_validate(p).model_dump() for p in processos]
        return {"dados": dados, "total": len(dados), "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
def listar_processos(
    status: Optional[StatusProcesso] = Query(None),
    cliente_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Processo)
        if status:
            query = query.filter(Processo.status == status.value)
        if cliente_id:
            query = query.filter(Processo.cliente_id == cliente_id)
        processos = query.all()
        dados = [ProcessoOut.model_validate(p).model_dump() for p in processos]
        return {"dados": dados, "total": len(dados), "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
