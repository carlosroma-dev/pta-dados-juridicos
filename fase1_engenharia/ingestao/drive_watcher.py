import json
import logging
import os
import time
from pathlib import Path

from fase1_engenharia.ingestao import drive_client
from fase1_engenharia.ingestao.extrair_pdfs import processar_pdfs

logger = logging.getLogger(__name__)
STATE_PATH = Path("drive_state.json")


def carregar_state() -> dict:
    """
    Lê o registro do que já foi baixado (id -> modifiedTime).
    Se o arquivo ainda não existe (primeira execução), devolve {} —
    o que faz a comparação tratar todos os PDFs como novos.
    """
    if not STATE_PATH.exists():
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
    
def salvar_state(state: dict) -> None:
    """
    Grava o registro atualizado (id -> modifiedTime) no drive_state.json.
    Chamado depois de baixar arquivos, para lembrar o que já foi processado.
    """
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def filtrar_novos_ou_modificados(arquivos: list[dict], state: dict, pasta_pdfs: Path) -> list[dict]:
    """
    Retorna os PDFs que precisam ser baixados:
    - novos (id nunca visto)
    - modificados (data diferente da guardada)
    - ausentes no disco (state diz que temos, mas o arquivo local sumiu)
    """
    para_baixar = []
    for arq in arquivos:
        file_id = arq["id"]
        modificado_em = arq["modifiedTime"]
        arquivo_local = pasta_pdfs / arq["name"]

        novo = file_id not in state
        modificado = state.get(file_id) != modificado_em
        sumiu_do_disco = not arquivo_local.exists()

        if novo or modificado or sumiu_do_disco:
            para_baixar.append(arq)

    return para_baixar
def processar_ciclo(servico, folder_id: str, pasta_pdfs: Path) -> None:
    """
    Executa uma passada completa: lista os PDFs do Drive, baixa os novos
    ou modificados, dispara a extração de cada um e atualiza o state.
    """
    state = carregar_state()
    arquivos = drive_client.listar_pdfs(servico, folder_id)
    para_baixar = filtrar_novos_ou_modificados(arquivos, state, pasta_pdfs)

    if not para_baixar:
        logger.info("Nenhum PDF novo ou modificado.")
        return

    logger.info(f"{len(para_baixar)} PDF(s) para processar.")

    for arq in para_baixar:
        caminho = drive_client.baixar_pdf(servico, arq["id"], arq["name"], pasta_pdfs)
        processar_pdfs(caminho)
        state[arq["id"]] = arq["modifiedTime"]

    salvar_state(state)

def main() -> None:
    """
    Inicia o watcher: autentica no Drive e fica em loop, verificando
    a pasta a cada INTERVALO segundos até ser interrompido (Ctrl+C).
    """
    credencial = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    folder_id = os.getenv("DRIVE_FOLDER_ID")
    intervalo = int(os.getenv("DRIVE_POLL_INTERVAL", "60"))
    pasta_pdfs = Path(__file__).resolve().parents[2] / "data" / "pdfs"

    servico = drive_client.autenticar(credencial)
    logger.info(f"Watcher iniciado. Verificando a cada {intervalo}s. (Ctrl+C para parar)")

    while True:
        try:
            processar_ciclo(servico, folder_id, pasta_pdfs)
        except Exception as e:
            logger.error(f"Erro no ciclo: {e}")
        time.sleep(intervalo)


if __name__ == "__main__":
    main()