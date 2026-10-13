import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from fase1_engenharia.api.routes import agente, advogados, alertas, busca, clientes, documentos, honorarios, painel, processos
load_dotenv()

# Lê a chave do .env. Se não estiver configurada, a API funciona sem autenticação
# — útil para desenvolvimento local sem ter que setar variáveis de ambiente.
_API_KEY = os.getenv("API_KEY", "")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _verificar_chave(request: Request, key: Optional[str] = Security(_api_key_header)) -> None:
    if request.url.path == "/health":
        return
    if _API_KEY and key != _API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key ausente ou inválida",
        )


app = FastAPI(
    title="PTA Dados 2026 — API",
    description="API de dados jurídicos com busca semântica via pgvector.",
    version="1.0.0",
    # Aplica autenticação globalmente a todas as rotas
    dependencies=[Security(_verificar_chave)],
)

app.include_router(clientes.router)
app.include_router(processos.router)
app.include_router(honorarios.router)
app.include_router(busca.router)
app.include_router(agente.router)
app.include_router(advogados.router)
app.include_router(painel.router)
app.include_router(documentos.router)
app.include_router(alertas.router)

@app.get("/health", tags=["health"])
def health():
    from sqlalchemy import text
    from fase1_engenharia.db.database import SessionLocal

    resultado: dict = {"status": "ok", "banco": "erro", "pgvector": {}, "agente": {}}

    # Check 1 — banco
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        resultado["banco"] = "ok"
    except Exception as exc:
        resultado["banco"] = f"erro: {exc}"
        resultado["status"] = "erro"

    # Check 2 — pgvector (documento_chunks acessível)
    try:
        with SessionLocal() as session:
            n = session.execute(text("SELECT COUNT(*) FROM documento_chunks")).scalar()
        resultado["pgvector"] = {"ok": True, "chunks_indexados": n}
    except Exception as exc:
        resultado["pgvector"] = {"ok": False, "detalhe": str(exc)}
        if resultado["status"] == "ok":
            resultado["status"] = "degradado"

    # Check 3 — agente (grafo LangGraph compilado importável)
    try:
        from fase2_agente.grafo.grafo import app as _agent  # noqa: F401
        resultado["agente"] = {
            "ok": True,
            "openai_key_presente": bool(os.getenv("OPENAI_API_KEY")),
        }
    except Exception as exc:
        resultado["agente"] = {"ok": False, "detalhe": str(exc)}
        if resultado["status"] == "ok":
            resultado["status"] = "degradado"

    http_status = 503 if resultado["status"] == "erro" else 200
    return JSONResponse(content=resultado, status_code=http_status)
