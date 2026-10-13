from fastapi import APIRouter, HTTPException

from fase1_engenharia.api.models.agente import AgenteRequest, AgenteResponse

router = APIRouter(prefix="/agente", tags=["agente"])


@router.post("/perguntar", response_model=AgenteResponse)
def perguntar_agente(body: AgenteRequest):
    """Recebe uma pergunta em linguagem natural e retorna a resposta do agente.

    Protegida por X-API-Key — a verificação é global (main.py), igual às demais rotas.
    """
    try:
        from fase2_agente.grafo.grafo import perguntar
        from fase2_agente.memoria.janela import aplicar_janela
        from fase2_agente.memoria.sessao import carregar_sessao, salvar_sessao

        sid, historico = carregar_sessao(body.session_id)
        resultado = perguntar(body.pergunta, historico)
        historico_atualizado = aplicar_janela(
            historico,
            resultado.get("pergunta_original", body.pergunta),
            resultado.get("resposta", ""),
        )
        salvar_sessao(sid, historico_atualizado)

        return AgenteResponse(
            pergunta=resultado.get("pergunta_original", body.pergunta),
            resposta=resultado.get("resposta", ""),
            rota=resultado.get("rota", ""),
            validado=resultado.get("validado", False),
            status="ok",
            session_id=sid,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
