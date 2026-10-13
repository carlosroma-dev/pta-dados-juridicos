
# Script de extração de texto de PDFs jurídicos

# Imports
import logging
from pathlib import Path

import pdfplumber


# Configuração de caminhos

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
PASTA_PDFS = RAIZ_PROJETO / "data" / "pdfs"
PASTA_RAW = RAIZ_PROJETO / "data" / "raw"
ARQUIVO_LOG = PASTA_RAW / "extraction.log"

# Configuração de logging
logging.basicConfig(
    level=logging.INFO, # Nível de log: INFO para mensagens informativas
    format="%(asctime)s - %(levelname)s - %(message)s", # Formato do log: data, nível e mensagem
    datefmt="%d-%m-%Y %H:%M:%S",  
    handlers=[ # Handlers para salvar em arquivo e imprimir no terminal
        logging.FileHandler(ARQUIVO_LOG, encoding="utf-8"),
        logging.StreamHandler() # Imprime também no terminal
    ],
)
logger = logging.getLogger(__name__) # Logger para este módulo porque pode ser importado por outros scripts

def extrair_texto_pdf(caminho_pdf: Path) -> tuple[str, int]:
    # Extrai o texto de um pdf
    textos_por_pagina = []
    with pdfplumber.open(caminho_pdf) as pdf:
        numero_paginas = len(pdf.pages)

        for indice, pagina in enumerate(pdf.pages, start=1):
            texto = pagina.extract_text()

            if texto is None:
                logger.warning(f"Página {indice} do PDF '{caminho_pdf.name}' não contém texto extraível.")
                texto = ""  # Define como string vazia para evitar erros posteriores
            textos_por_pagina.append(texto)

    
    texto_completo = "\n".join(textos_por_pagina)

    return texto_completo, numero_paginas

def processar_pdfs(caminho_pdf: Path):
    # Processo um unico PDF, verifica se o texto já foi extraído e salva como .txt

    nome_arquivo = caminho_pdf.name
    caminho_saida = PASTA_RAW / f"{caminho_pdf.stem}.txt"

    # Se o texto já foi extraído, não processa novamente
    if caminho_saida.exists():
        logger.info(f"Texto do PDF '{nome_arquivo}' já foi extraído. Pulando processamento.")
        return "pulado"
    
    # Tenta extrair e salvar
    try:
        texto, num_paginas = extrair_texto_pdf(caminho_pdf)
        num_caracteres = len(texto)

        # Salva com encoding UTF-8 para evitar problemas de caracteres especiais
        caminho_saida.write_text(texto, encoding="utf-8")

        logger.info(f"{nome_arquivo} | {num_paginas} páginas |",
                    f"{num_caracteres} | caracteres | Extração bem-sucedida."
                    )
        return "processado"
    
    except Exception as error:
        logger.error(f"{nome_arquivo} | Erro ao extrair: {type(error).__name__}: {error}")
        return "erro"

def main() -> None:
    # Função principal para processar todos os PDFs na pasta

    PASTA_RAW.mkdir(parents=True, exist_ok=True) # Garante que a pasta de saída exista

    logger.info("----------------") # Linha de separação no log
    logger.info("Iniciando pipeline de extração de PDFs")
    logger.info(f"Entrada: {PASTA_PDFS}")
    logger.info(f"Saída: {PASTA_RAW}")
    logger.info("----------------")

    # Lista todos os PDFs na pasta de entrada
    pdfs = sorted(PASTA_PDFS.glob("*.pdf")) # Ordena para garantir processamento consistente

    if not pdfs:
        logger.warning(f"Nenhum PDF encontrado em '{PASTA_PDFS}'. Verifique o caminho e os arquivos.")
        return
    
    logger.info(f"Encontrados {len(pdfs)} PDF(s) para processar.")

    # Contadores pro resumo final

    contadores = {"processado": 0, "pulado": 0, "erro": 0}

    for pdf in pdfs:
        resultado = processar_pdfs(pdf)
        contadores[resultado] += 1

    
    # Resumo final
    logger.info("----------------")
    logger.info(
        f"Resumo: {contadores['processado']} processados,"
        f" {contadores['pulado']} pulados,"
        f" {contadores['erro']} erros."
    )
    logger.info("----------------")

if __name__ == "__main__":
    main()
    