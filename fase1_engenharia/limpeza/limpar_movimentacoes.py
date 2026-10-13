
import logging

import pandas as pd
import numpy as np

from fase1_engenharia.limpeza.transformacoes import (
    MAPA_ADVOGADOS_ID,
    normalizar_advogado_serie,
    normalizar_boolean_serie,
    normalizar_enum_serie,
    padronizar_data_serie,
)

logger = logging.getLogger(__name__)

def _contar_nao_mapeados(antes: pd.Series, depois: pd.Series) -> int:
    return int((antes.notna() & depois.isna()).sum())

def limpar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    logger.info("=" * 60)
    logger.info("Iniciando limpeza de Movimentações")
    logger.info("=" * 60)

    df = df.copy()
    linhas_iniciais = len(df)
    logger.info(f"Linhas iniciais: {linhas_iniciais}")

    # Diagnóstico inicial ─────────────────────────────────────────────
    nulos_antes = df.isna().sum().to_dict()
    logger.info(f"Nulos por coluna (antes): {nulos_antes}")

    # Remoção de duplicatas ───────────────────────────────────────────
    duplicatas = df.duplicated().sum()
    if duplicatas > 0:
        df = df.drop_duplicates().reset_index(drop=True)
        logger.info(f"Duplicatas removidas: {duplicatas}")
    else:
        logger.info("Nenhuma duplicata encontrada")

    # Número do processo (identificador, só strip) ────────────────────
    df["numero_processo"] = df["numero_processo"].astype(str).str.strip()
    df["numero_processo"] = df["numero_processo"].replace(
        {"nan": np.nan, "none": np.nan, "": np.nan}
    )

    # Tipo de ato (enum técnico) ──────────────────────────────────────
    # "Sentença" → "sentenca", "agravo regimental" → "agravo_regimental"
    df["tipo_ato"] = normalizar_enum_serie(df["tipo_ato"])

    # Advogado responsável (mapa canônico) ────────────────────────────
    advogado_antes = df["advogado_responsavel"].copy()
    df["advogado_responsavel"] = normalizar_advogado_serie(df["advogado_responsavel"])
    advogados_nao_mapeados = _contar_nao_mapeados(
    advogado_antes, df["advogado_responsavel"]
)
    # Adição: coluna de ID do advogado (inteiro, chave estrangeira)
    idx_adv = list(df.columns).index("advogado_responsavel")

    # Mapeia os nomes normalizados para IDs usando o MAPA_ADVOGADOS_ID
    serie_ids = df["advogado_responsavel"].map(MAPA_ADVOGADOS_ID)
    
    # Contagem de advogados não mapeados (nomes que não viraram ID)
    df.insert(idx_adv, "advogado_id", serie_ids)
    
    # Descrição (texto livre, só strip) ───────────────────────────────
    df["descricao"] = df["descricao"].astype(str).str.strip()
    df["descricao"] = df["descricao"].replace(
        {"nan": np.nan, "none": np.nan, "": np.nan}
    )

    # Datas ───────────────────────────────────────────────────────────
    df["data_movimentacao"] = padronizar_data_serie(df["data_movimentacao"])
    datas_mov_invalidas = (
        df["data_movimentacao"].isna().sum()
        - nulos_antes.get("data_movimentacao", 0)
    )
    if datas_mov_invalidas > 0:
        logger.warning(
            f"data_movimentacao: {datas_mov_invalidas} valores não parseáveis viraram NaT"
        )

    df["prazo_gerado"] = padronizar_data_serie(df["prazo_gerado"])
    # prazo_gerado tinha 5.617 nulos originais (não é erro — 70% dos atos
    # não geram prazo). Não vamos contar como "invalido" porque já era nulo.

    # Concluído (boolean) ─────────────────────────────────────────────
    # Mapeia 7 variações: sim/S/1/True → True, não/nao/N/0/False → False, NaN → <NA>
    df["concluido"] = normalizar_boolean_serie(df["concluido"])

    # Diagnóstico final ───────────────────────────────────────────────
    nulos_depois = df.isna().sum().to_dict()
    logger.info(f"Nulos por coluna (depois): {nulos_depois}")
    logger.info(f"Linhas finais: {len(df)}")

    # Estatísticas pra retorno ───────────────────────────────────────
    estatisticas = {
        "tabela": "movimentacoes",
        "linhas_iniciais": linhas_iniciais,
        "linhas_finais": len(df),
        "duplicatas_removidas": int(duplicatas),
        "nulos_antes": {k: int(v) for k, v in nulos_antes.items()},
        "nulos_depois": {k: int(v) for k, v in nulos_depois.items()},
        "datas_invalidas_movimentacao": int(datas_mov_invalidas),
        "advogados_nao_mapeados": int(advogados_nao_mapeados),
    }

    return df, estatisticas



# teste rápido
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    from fase1_engenharia.ingestao.ler_planilhas import ler_planilha

    df = ler_planilha("movimentacoes")
    df_limpo, stats = limpar(df)

    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)

    print("\nEstatísticas:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"\nPrimeiras 5 linhas do DF limpo:")
    print(df_limpo.head().to_string())

    print(f"\nTipos das colunas:")
    print(df_limpo.dtypes.to_string())

    print(f"\nValores únicos de 'tipo_ato':")
    print(df_limpo["tipo_ato"].value_counts(dropna=False).to_string())

    print(f"\nValores únicos de 'advogado_responsavel':")
    print(df_limpo["advogado_responsavel"].value_counts(dropna=False).to_string())

    print(f"\nValores únicos de 'concluido':")
    print(df_limpo["concluido"].value_counts(dropna=False).to_string())