import logging

import pandas as pd
import numpy as np

from fase1_engenharia.limpeza.transformacoes import (
    normalizar_nome_proprio_serie,
    padronizar_data_serie,
)

logger = logging.getLogger(__name__)


def limpar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:

    logger.info("=" * 60)
    logger.info("Iniciando limpeza de Clientes")
    logger.info("=" * 60)

    # Trabalha numa cópia pra não bagunçar o original.
    df = df.copy()

    # Estado inicial.
    linhas_iniciais = len(df)
    logger.info(f"Linhas iniciais: {linhas_iniciais}")

    # Diagnóstico de nulos (antes da limpeza) 
    nulos_antes = df.isna().sum().to_dict()
    logger.info(f"Nulos por coluna (antes): {nulos_antes}")

    # Remoção de duplicatas 
    # Considera duplicata quando a linha inteira é igual a outra.
    duplicatas = df.duplicated().sum()
    if duplicatas > 0:
        df = df.drop_duplicates().reset_index(drop=True)
        logger.info(f"Duplicatas removidas: {duplicatas}")
    else:
        logger.info("Nenhuma duplicata encontrada")

    # adronização de strings 

    # Nome: Title Case (é nome próprio)
    df["nome"] = normalizar_nome_proprio_serie(df["nome"])

    # Cidade: Title Case (também nome próprio).
    # Consolida "recife/Recife/RECIFE" → "Recife".
    df["cidade"] = normalizar_nome_proprio_serie(df["cidade"])

    # Email: lowercase + strip (não é nome próprio, é identificador técnico).
    df["email"] = df["email"].astype(str).str.strip().str.lower()
    # astype(str) converte NaN em "nan" — desfazemos pra preservar nulos.
    df["email"] = df["email"].replace({"nan": np.nan, "none": np.nan, "": np.nan})

    # CPF: só strip. Formato XXX.XXX.XXX-XX é mantido conforme veio.
    df["cpf"] = df["cpf"].astype(str).str.strip()
    df["cpf"] = df["cpf"].replace({"nan": np.nan, "none": np.nan, "": np.nan})

    # Contato (telefone): só strip. Formato (XX) XXXXX-XXXX é mantido.
    df["contato"] = df["contato"].astype(str).str.strip()
    df["contato"] = df["contato"].replace({"nan": np.nan, "none": np.nan, "": np.nan})

    # ── 4. Padronização de data ────────────────────────────────────────────
    df["data_inicio"] = padronizar_data_serie(df["data_inicio"])
    datas_invalidas = df["data_inicio"].isna().sum()
    if datas_invalidas > 0:
        logger.warning(
            f"data_inicio: {datas_invalidas} valores não parseáveis viraram NaT"
        )

    # Diagnóstico final 
    nulos_depois = df.isna().sum().to_dict()
    logger.info(f"Nulos por coluna (depois): {nulos_depois}")
    logger.info(f"Linhas finais: {len(df)}")

    # Estatísticas pra retorno 
    estatisticas = {
        "tabela": "clientes",
        "linhas_iniciais": linhas_iniciais,
        "linhas_finais": len(df),
        "duplicatas_removidas": int(duplicatas),
        "nulos_antes": {k: int(v) for k, v in nulos_antes.items()},
        "nulos_depois": {k: int(v) for k, v in nulos_depois.items()},
        "datas_invalidas": int(datas_invalidas),
    }

    return df, estatisticas

if __name__ == "__main__":
    # Configura log básico pra ver o que tá acontecendo.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Adiciona a raiz do projeto ao path pra a importação funcionar
    # quando o script é rodado direto (não via pipeline).
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    from fase1_engenharia.ingestao.ler_planilhas import ler_planilha

    df = ler_planilha("clientes")
    df_limpo, stats = limpar(df)

    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)
    print(f"\nEstatísticas:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"\nPrimeiras 5 linhas do DF limpo:")
    print(df_limpo.head().to_string())

    print(f"\nTipos das colunas:")
    print(df_limpo.dtypes.to_string())

    print(f"\nValores únicos de cidade:")
    print(df_limpo["cidade"].value_counts(dropna=False).to_string())