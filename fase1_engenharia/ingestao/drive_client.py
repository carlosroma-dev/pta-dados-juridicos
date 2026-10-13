from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

load_dotenv()

# Escopo de leitura usado pelo watcher. O upload exige drive.file (escrita
# restrita aos arquivos criados pelo próprio app). Para ativar o upload:
#   1. Troque SCOPES_LEITURA por SCOPES_ESCRITA abaixo.
#   2. Gere um novo token/credencial com o escopo atualizado no Google Cloud.
#   3. Defina DRIVE_UPLOAD_ENABLED=true no .env.
SCOPES_LEITURA = ["https://www.googleapis.com/auth/drive.readonly"]
SCOPES_ESCRITA = ["https://www.googleapis.com/auth/drive.file"]

SCOPES = SCOPES_LEITURA

def autenticar(caminho_credencial: str):
    """
    Lê o JSON da Service Account e devolve um objeto de serviço do Drive,
    já autenticado e pronto para listar e baixar arquivos.
    """
    creds = Credentials.from_service_account_file(caminho_credencial, scopes=SCOPES)
    servico = build("drive", "v3", credentials=creds)
    return servico

def listar_pdfs(servico, folder_id: str) -> list[dict]:
    """
    Lista os PDFs da pasta do Drive.
    Retorna uma lista de dicts com id, nome e data de modificação de cada um.
    Lida com paginação: o Drive devolve no máximo ~100 itens por página.
    """
    query = (
        f"'{folder_id}' in parents "
        f"and mimeType = 'application/pdf' "
        f"and trashed = false"
    )

    arquivos = []
    page_token = None

    while True:
        resposta = (
            servico.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, modifiedTime)",
                pageToken=page_token,
            )
            .execute()
        )
        arquivos.extend(resposta.get("files", []))
        page_token = resposta.get("nextPageToken")
        if not page_token:
            break

    return arquivos

def baixar_pdf(servico, file_id: str, nome_arquivo: str, pasta_destino: Path) -> Path:
    """
    Baixa um PDF do Drive para a pasta local de destino.
    Retorna o caminho do arquivo salvo. Baixa em pedaços (chunks),
    então funciona bem mesmo com PDFs grandes.
    """
    pasta_destino.mkdir(parents=True, exist_ok=True)
    caminho_destino = pasta_destino / nome_arquivo

    requisicao = servico.files().get_media(fileId=file_id)

    with open(caminho_destino, "wb") as f:
        downloader = MediaIoBaseDownload(f, requisicao)
        concluido = False
        while not concluido:
            _, concluido = downloader.next_chunk()

    return caminho_destino


def enviar_para_drive(caminho_pdf: Path, folder_id: str, caminho_credencial: str) -> str:
    """Envia um PDF para a pasta do Drive e devolve o file_id gerado.

    Pré-requisito: a service account precisa ter escopo `drive.file` (não
    `drive.readonly`) e permissão de Editor na pasta `folder_id`.
    Enquanto a credencial de escrita não estiver configurada, esta função
    levanta `NotImplementedError` — a ingestão continua normalmente sem
    arquivar no Drive.

    Para ativar:
        1. Gere uma credencial com escopo drive.file no Google Cloud.
        2. Dê permissão de Editor da pasta à service account.
        3. Defina DRIVE_UPLOAD_ENABLED=true no .env.
    """
    if SCOPES != SCOPES_ESCRITA:
        raise NotImplementedError(
            "Upload para o Drive requer credencial com escopo drive.file. "
            "Consulte os comentários em drive_client.py para ativar."
        )

    servico = autenticar(caminho_credencial)
    metadados = {"name": caminho_pdf.name, "parents": [folder_id]}
    conteudo = MediaIoBaseUpload(
        BytesIO(caminho_pdf.read_bytes()),
        mimetype="application/pdf",
        resumable=True,
    )
    arquivo = (
        servico.files()
        .create(body=metadados, media_body=conteudo, fields="id")
        .execute()
    )
    return arquivo["id"]