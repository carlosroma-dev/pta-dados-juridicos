"""Rotas de ingestão de documentos pela interface.

POST /documentos/ingerir  — recebe PDF, valida, salva em disco, registra como
                            `recebido` e dispara o pipeline em background.
GET  /documentos/         — lista as últimas ingestões (para o painel da aba).
GET  /documentos/{id}     — status atual de uma ingestão (polling da interface).

Ciclo de status:
    recebido → extraindo → estruturando → indexando → concluido
                                                    ↘ erro
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from fase1_engenharia.api.models.documentos import IngestaoOut
from fase1_engenharia.db.database import SessionLocal, get_db
from fase1_engenharia.db.models import DocumentoIngestao
from fase1_engenharia.ingestao.armazenamento import salvar_pdf
from fase1_engenharia.ingestao.drive_client import enviar_para_drive
from fase1_engenharia.ingestao.orquestrador import IngestaoError, ingerir_pdf

log = logging.getLogger(__name__)

router = APIRouter(prefix="/documentos", tags=["documentos"])

TAMANHO_MAX_MB = 25


# ── Validação ──────────────────────────────────────────────────────────────────

def _validar_pdf(arquivo: UploadFile, conteudo: bytes) -> None:
    nome = (arquivo.filename or "").lower()
    eh_pdf = nome.endswith(".pdf") or arquivo.content_type == "application/pdf"
    if not eh_pdf:
        raise HTTPException(status_code=400, detail="Envie um arquivo em formato PDF.")
    if not conteudo:
        raise HTTPException(status_code=400, detail="O arquivo enviado está vazio.")
    if len(conteudo) > TAMANHO_MAX_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"O arquivo excede o limite de {TAMANHO_MAX_MB} MB.",
        )


# ── Background task ────────────────────────────────────────────────────────────

def _atualizar_status(db: Session, id_ingestao: int, **campos) -> None:
    """Atualiza campos do registro e faz commit. `atualizado_em` é sempre tocado."""
    registro = db.get(DocumentoIngestao, id_ingestao)
    if registro is None:
        log.warning("[ingestao %d] registro não encontrado para atualizar status", id_ingestao)
        return
    for campo, valor in campos.items():
        setattr(registro, campo, valor)
    registro.atualizado_em = datetime.now()  # type: ignore[assignment]
    db.commit()


def _processar_em_background(id_ingestao: int, caminho: Path) -> None:
    """Roda o pipeline completo e atualiza o status a cada etapa.

    Cria a própria sessão de banco: a sessão do request já foi fechada quando
    o background começa (o FastAPI devolve o 202 antes de rodar esta função).
    """
    db = SessionLocal()
    try:
        def on_etapa(etapa: str) -> None:
            _atualizar_status(db, id_ingestao, status=etapa)
            log.info("[ingestao %d] status → %s", id_ingestao, etapa)

        resultado = ingerir_pdf(caminho, session=db, on_etapa=on_etapa)

        _atualizar_status(
            db, id_ingestao,
            status="concluido",
            num_chunks=resultado.num_chunks,
            processo_numero=resultado.processo_numero,
            tipo_documento=resultado.tipo_documento,
        )
        log.info("[ingestao %d] concluido — %d chunks indexados", id_ingestao, resultado.num_chunks)

        # ── Hook do Drive (arquivamento) ───────────────────────────────────────
        # Só executa quando DRIVE_UPLOAD_ENABLED=true. Nunca bloqueia o
        # "concluido": se falhar, loga o aviso mas o documento já está
        # disponível para consulta.
        if os.getenv("DRIVE_UPLOAD_ENABLED", "false").lower() == "true":
            try:
                folder_id = os.getenv("DRIVE_FOLDER_ID", "")
                credencial = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
                enviar_para_drive(caminho, folder_id, credencial)
                _atualizar_status(db, id_ingestao, arquivado_drive=True)
                log.info("[ingestao %d] arquivado no Drive", id_ingestao)
            except Exception:
                log.warning("[ingestao %d] falha ao arquivar no Drive (documento disponível para consulta)", id_ingestao, exc_info=True)

    except IngestaoError as e:
        log.error("[ingestao %d] falha em '%s': %s", id_ingestao, e.etapa, e.mensagem, exc_info=e.causa)
        _atualizar_status(db, id_ingestao, status="erro", mensagem_erro=e.mensagem)

    except Exception:
        log.exception("[ingestao %d] erro inesperado", id_ingestao)
        _atualizar_status(
            db, id_ingestao,
            status="erro",
            mensagem_erro="Erro inesperado. Tente novamente em instantes.",
        )

    finally:
        db.close()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[IngestaoOut])
def listar_ingestoes(limite: int = 10, db: Session = Depends(get_db)):
    """Últimas ingestões, da mais recente para a mais antiga."""
    return (
        db.query(DocumentoIngestao)
        .order_by(DocumentoIngestao.data_ingestao.desc())
        .limit(limite)
        .all()
    )


@router.get("/{id_ingestao}", response_model=IngestaoOut)
def status_ingestao(id_ingestao: int, db: Session = Depends(get_db)):
    """Status atual de uma ingestão — consultado em polling pela interface."""
    registro = db.get(DocumentoIngestao, id_ingestao)
    if registro is None:
        raise HTTPException(status_code=404, detail="Ingestão não encontrada.")
    return registro


@router.post("/ingerir", response_model=IngestaoOut, status_code=status.HTTP_202_ACCEPTED)
def ingerir_documento(
    arquivo: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """Salva o PDF, cria o registro `recebido` e dispara o pipeline em background."""
    conteudo = arquivo.file.read()
    _validar_pdf(arquivo, conteudo)

    caminho, nome_salvo = salvar_pdf(conteudo, arquivo.filename)

    agora = datetime.now()
    registro = DocumentoIngestao(
        nome_arquivo=nome_salvo,
        nome_original=arquivo.filename,
        data_ingestao=agora,
        atualizado_em=agora,
        status="recebido",
    )
    db.add(registro)
    db.commit()
    db.refresh(registro)

    background_tasks.add_task(_processar_em_background, int(registro.id_ingestao), caminho)  # type: ignore[arg-type]
    return registro