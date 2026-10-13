# Imports
import logging
from pathlib import Path

import pandas as pd

# Configurações de caminhos e arquivos
RAIZ_PROJETO = Path(__file__).resolve().parents[2]
PASTA_PLANILHAS = RAIZ_PROJETO / "data" / "planilhas"

ARQUIVOS = {
    "clientes": "Clientes.xlsx",
    "processos": "Processos.xlsx",
    "honorarios": "Honorarios.xlsx",
    "movimentacoes": "Movimentacoes.xlsx",
}

logger = logging.getLogger(__name__) # Configura o logger para este módulo

# Funções de leitura das planilhas 
def ler_planilha(chave: str) -> pd.DataFrame:
    if chave not in ARQUIVOS: # Valida se a chave é válida
        raise KeyError(
            f"Planilha desconhecida: '{chave}'. "
            f"Opções válidas: {list(ARQUIVOS.keys())}"
        )

    caminho = PASTA_PLANILHAS / ARQUIVOS[chave]

    if not caminho.exists(): # Verifica se o arquivo existe
        raise FileNotFoundError(
            f"Planilha não encontrada em {caminho}. "
            f"Coloque o arquivo {ARQUIVOS[chave]} em {PASTA_PLANILHAS}."
        )

    logger.info(f"Lendo {ARQUIVOS[chave]}...")
    df = pd.read_excel(caminho)
    logger.info(
        f"  {ARQUIVOS[chave]}: {df.shape[0]} linhas × {df.shape[1]} colunas"
    )

    return df


def ler_todas() -> dict[str, pd.DataFrame]: # Lê todas as planilhas e retorna um dicionário de DataFrames

    logger.info("Iniciando leitura das planilhas...")
    dfs = {chave: ler_planilha(chave) for chave in ARQUIVOS}
    logger.info(f"Leitura concluída: {len(dfs)} planilhas carregadas.")
    return dfs

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    dfs = ler_todas() # Lê todas as planilhas e armazena em um dicionário

    print("\n" + "=" * 60)
    print("Resumo das planilhas lidas:")
    print("=" * 60)
    for nome, df in dfs.items():
        print(f"\n[{nome}]")
        print(f"  Linhas: {df.shape[0]}")
        print(f"  Colunas: {df.shape[1]}")
        print(f"  Nomes das colunas: {list(df.columns)}")