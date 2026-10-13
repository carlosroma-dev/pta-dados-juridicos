import logging

import numpy as np
import pandas as pd

from fase1_engenharia.limpeza.transformacoes import (
    MAPA_FORMA_PAGAMENTO,
    MAPA_STATUS_PAGAMENTO,
    aplicar_mapa,
    normalizar_boolean_serie,
    normalizar_percentual_decimal_serie,
    padronizar_data_serie,
    padronizar_valor_monetario_serie,
)

logger = logging.getLogger(__name__)


def _contar_nao_mapeados(antes: pd.Series, depois: pd.Series) -> int:
    """
    Conta quantos valores não estavam no mapa.
    
    Lógica: contamos onde 'antes' tinha valor (não-nulo) E 'depois' ficou nulo.
    Isso significa "tinha algo escrito mas o mapa não reconheceu".
    """
    return int((antes.notna() & depois.isna()).sum())


def limpar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    logger.info("=" * 60)
    logger.info("Iniciando limpeza de Honorários")
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

    # numero_processo (identificador, só strip) ───────────────────────
    # NOTA: cliente_id já vem como int64 do Excel, não tocamos pra evitar
    # quebrar a chave estrangeira (vai ser usada em integridade_referencial.py).
    df["numero_processo"] = df["numero_processo"].astype(str).str.strip()
    df["numero_processo"] = df["numero_processo"].replace(
        {"nan": np.nan, "none": np.nan, "": np.nan}
    )

    # Valores monetários ──────────────────────────────────────────────
    df["valor_total_contratado"] = padronizar_valor_monetario_serie(
        df["valor_total_contratado"]
    )
    df["valor_pago"] = padronizar_valor_monetario_serie(df["valor_pago"])
    df["valor_em_aberto"] = padronizar_valor_monetario_serie(df["valor_em_aberto"])

    # Datas ───────────────────────────────────────────────────────────
    df["data_contrato"] = padronizar_data_serie(df["data_contrato"])
    df["data_vencimento"] = padronizar_data_serie(df["data_vencimento"])

    # Forma de pagamento (enum via mapa) ──────────────────────────────
    # Guardamos coluna ANTES de aplicar mapa pra detectar não-mapeados corretamente.
    forma_pagamento_antes = df["forma_pagamento"].copy()
    df["forma_pagamento"] = aplicar_mapa(df["forma_pagamento"], MAPA_FORMA_PAGAMENTO)
    formas_nao_mapeadas = _contar_nao_mapeados(
        forma_pagamento_antes, df["forma_pagamento"]
    )
    if formas_nao_mapeadas > 0:
        logger.warning(
            f"forma_pagamento: {formas_nao_mapeadas} valores não estavam no "
            f"mapa. Considere atualizar MAPA_FORMA_PAGAMENTO."
        )

    # Honorário de êxito (boolean) ────────────────────────────────────
    df["honorario_exito"] = normalizar_boolean_serie(df["honorario_exito"])

    # Percentual de êxito (regra: 0-1 mantém / 1-100 divide / fora NaN) ────
    df["percentual_exito"] = normalizar_percentual_decimal_serie(
        df["percentual_exito"]
    )

    # Status de pagamento (enum via mapa) ─────────────────────────────
    status_pagamento_antes = df["status_pagamento"].copy()
    df["status_pagamento"] = aplicar_mapa(
        df["status_pagamento"], MAPA_STATUS_PAGAMENTO
    )
    status_nao_mapeados = _contar_nao_mapeados(
        status_pagamento_antes, df["status_pagamento"]
    )
    if status_nao_mapeados > 0:
        logger.warning(
            f"status_pagamento: {status_nao_mapeados} valores não estavam "
            f"no mapa. Considere atualizar MAPA_STATUS_PAGAMENTO."
        )

    # Diagnóstico final ───────────────────────────────────────────────
    nulos_depois = df.isna().sum().to_dict()
    logger.info(f"Nulos por coluna (depois): {nulos_depois}")
    logger.info(f"Linhas finais: {len(df)}")

    # Estatísticas pra retorno ────────────────────────────────────────
    estatisticas = {
        "tabela": "honorarios",
        "linhas_iniciais": linhas_iniciais,
        "linhas_finais": len(df),
        "duplicatas_removidas": int(duplicatas),
        "nulos_antes": {k: int(v) for k, v in nulos_antes.items()},
        "nulos_depois": {k: int(v) for k, v in nulos_depois.items()},
        "formas_pagamento_nao_mapeadas": formas_nao_mapeadas,
        "status_pagamento_nao_mapeados": status_nao_mapeados,
    }

    return df, estatisticas


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    from fase1_engenharia.ingestao.ler_planilhas import ler_planilha

    df = ler_planilha("honorarios")
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

    print(f"\nValores únicos de 'forma_pagamento':")
    print(df_limpo["forma_pagamento"].value_counts(dropna=False).to_string())

    print(f"\nValores únicos de 'honorario_exito':")
    print(df_limpo["honorario_exito"].value_counts(dropna=False).to_string())

    print(f"\nValores únicos de 'status_pagamento':")
    print(df_limpo["status_pagamento"].value_counts(dropna=False).to_string())

    print(f"\nEstatísticas de 'percentual_exito':")
    print(df_limpo["percentual_exito"].describe().to_string())