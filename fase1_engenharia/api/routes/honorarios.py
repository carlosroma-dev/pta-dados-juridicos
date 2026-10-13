from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from fase1_engenharia.api.models.enums import StatusPagamento
from fase1_engenharia.db.database import get_db
from fase1_engenharia.db.models import Honorario, HonorarioOut

router = APIRouter(prefix="/honorarios", tags=["honorarios"])


@router.get("/")
def listar_honorarios(
    status_pagamento: Optional[StatusPagamento] = Query(None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(Honorario)
        if status_pagamento:
            query = query.filter(Honorario.status_pagamento == status_pagamento.value)
        honorarios = query.all()
        dados = [HonorarioOut.model_validate(h).model_dump() for h in honorarios]
        return {"dados": dados, "total": len(dados), "status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
