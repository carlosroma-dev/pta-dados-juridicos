from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from fase1_engenharia.api.models.painel import (
    ItemCarteira,
    ItemDocumento,
    ItemInadimplencia,
    ItemPrazo,
)
from fase1_engenharia.db.database import get_db
from fase1_engenharia.db.models import Processo

router = APIRouter(prefix="/painel", tags=["painel"])


@router.get("/prazos", response_model=list[ItemPrazo])
def painel_prazos(
    dias: int = Query(30, description="Horizonte em dias a partir de hoje"),
    db: Session = Depends(get_db),
):
    try:
        hoje = date.today()
        limite = hoje + timedelta(days=dias)
        processos: List[Processo] = (
            db.query(Processo)
            .filter(
                Processo.prazo_proximo >= hoje,
                Processo.prazo_proximo <= limite,
            )
            .order_by(Processo.prazo_proximo)
            .all()
        )
        dados = [
            ItemPrazo(
                numero_processo=p.numero_processo, # type: ignore
                dias_restantes=(p.prazo_proximo - hoje).days, # type: ignore
                prazo_proximo=p.prazo_proximo, # type: ignore
                status=p.status, # type: ignore
                vara=p.vara, # type: ignore
            )
            for p in processos 
        ]
        return dados
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/inadimplencia", response_model=list[ItemInadimplencia])
def painel_inadimplencia(db: Session = Depends(get_db)):
    try:
        from sqlalchemy import func
        from fase1_engenharia.db.models import Cliente, Honorario, Processo

        resultados = (
            db.query(
                Cliente.nome.label("nome_cliente"),
                func.sum(Honorario.valor_em_aberto).label("valor_em_aberto"),
                func.count(Honorario.id_honorarios).label("quantidade_honorarios"),
            )
            .join(Processo, Processo.numero_processo == Honorario.processo_numero)
            .join(Cliente, Cliente.id_cliente == Processo.cliente_id)
            .filter(Honorario.status_pagamento == "atrasado")
            .group_by(Cliente.nome)
            .order_by(func.sum(Honorario.valor_em_aberto).desc())
            .all()
        )
        return [
            ItemInadimplencia(
                nome_cliente=r.nome_cliente,
                valor_em_aberto=r.valor_em_aberto or 0.0,
                quantidade_honorarios=r.quantidade_honorarios,
            )
            for r in resultados
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/documentos", response_model=list[ItemDocumento])
def painel_documentos(db: Session = Depends(get_db)):
    try:
        from sqlalchemy import func
        from fase1_engenharia.db.models import DocumentoChunk

        resultados = (
            db.query(
                DocumentoChunk.tipo_documento.label("tipo_documento"),
                func.count(DocumentoChunk.id_chunk).label("quantidade"),
            )
            .filter(DocumentoChunk.tipo_documento.isnot(None))
            .group_by(DocumentoChunk.tipo_documento)
            .order_by(func.count(DocumentoChunk.id_chunk).desc())
            .all()
        )
        return [
            ItemDocumento(
                tipo_documento=r.tipo_documento,
                quantidade=r.quantidade,
            )
            for r in resultados
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/carteira", response_model=list[ItemCarteira])
def painel_carteira(db: Session = Depends(get_db)):
    try:
        from sqlalchemy import func
        from fase1_engenharia.db.models import Advogado, Processo

        resultados = (
            db.query(
                Advogado.nome.label("advogado"),
                Processo.status.label("status"),
                func.count(Processo.numero_processo).label("quantidade"),
            )
            .join(Advogado, Advogado.id_advogado == Processo.advogado_id)
            .filter(Processo.status.isnot(None))
            .group_by(Advogado.nome, Processo.status)
            .order_by(Advogado.nome, Processo.status)
            .all()
        )
        return [
            ItemCarteira(
                advogado=r.advogado,
                status=r.status,
                quantidade=r.quantidade,
            )
            for r in resultados
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))