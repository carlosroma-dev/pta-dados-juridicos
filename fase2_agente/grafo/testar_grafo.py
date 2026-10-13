from fase2_agente.grafo.grafo import app

def testar(pergunta: str):
    print(f"\n{'='*60}")
    print(f"Pergunta: {pergunta}")
    print('='*60)
    
    resultado = app.invoke({
        "pergunta_original": pergunta,
        "pergunta_reformulada": "",
        "rota": "",
        "contexto": "",
        "resposta": "",
        "validado": False,
        "tentativas_ambigua": 0,
        "tentativas_validacao": 0
    })
    
    print(f"Rota: {resultado['rota']}")
    print(f"Resposta: {resultado['resposta']}")

if __name__ == "__main__":
    testar("Qual é o numero do ultimo processo colocado no banco relacional?")