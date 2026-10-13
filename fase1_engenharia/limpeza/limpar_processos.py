import logging

import pandas as pd
import numpy as np

from fase1_engenharia.limpeza.transformacoes import (
    MAPA_STATUS,
    MAPA_TIPO_PROCESSO,
    aplicar_mapa,
    normalizar_advogado_serie,
    normalizar_enum_serie,
    normalizar_nome_proprio_serie,
    padronizar_data_serie,
    padronizar_valor_monetario_serie,
)

logger = logging.getLogger(__name__)

def _contar_nao_mapeados(antes: pd.Series, depois: pd.Series) -> int:
    # Conta quantos valores não estavam no mapa.
    # Lógica: contamos onde 'antes' tinha valor (não-nulo) E 'depois' ficou nulo.
    return int((antes.notna() & depois.isna()).sum())

def limpar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:

    logger.info("=" * 60)
    logger.info("Iniciando limpeza de Processos")
    logger.info("=" * 60)

    df = df.copy()
    linhas_iniciais = len(df)
    logger.info(f"Linhas iniciais: {linhas_iniciais}")

    # ── 1. Diagnóstico de nulos (antes) 
    nulos_antes = df.isna().sum().to_dict()
    logger.info(f"Nulos por coluna (antes): {nulos_antes}")

    # ── 2. Remoção de duplicatas 
    duplicatas = df.duplicated().sum()
    if duplicatas > 0:
        df = df.drop_duplicates().reset_index(drop=True)
        logger.info(f"Duplicatas removidas: {duplicatas}")
    else:
        logger.info("Nenhuma duplicata encontrada")

    # Enums técnicos
    # tipo: "Trabalhista/TRABALHISTA" → "trabalhista", "Civil/Cível" → "civel"

    tipo_antes = df["tipo"].copy()
    df["tipo"] = aplicar_mapa(df["tipo"], MAPA_TIPO_PROCESSO)
    tipos_nao_mapeados = _contar_nao_mapeados(tipo_antes, df["tipo"])
    if tipos_nao_mapeados > 0:
        logger.warning(
        f"tipo: {tipos_nao_mapeados} valores não estavam no mapa. "
        f"Considere atualizar MAPA_TIPO_PROCESSO."
    )

    # sentença" → "sentenca", "acordo extrajudicial" → "acordo_extrajudicial"
    df["fase"] = normalizar_enum_serie(df["fase"])

    # Status (mapa pt/en → pt canônico)
    status_antes = df["status"].copy()
    df["status"] = aplicar_mapa(df["status"], MAPA_STATUS)
    status_nao_mapeados = _contar_nao_mapeados(status_antes, df["status"])
    if status_nao_mapeados > 0:
        logger.warning(
        f"status: {status_nao_mapeados} valores não estavam no mapa "
        f"e viraram NaN. Considere atualizar MAPA_STATUS."
    )
        

    # Advogado responsável (mapa canônico) 
    advogado_antes = df["advogado_responsavel"].copy()
    df["advogado_responsavel"] = normalizar_advogado_serie(df["advogado_responsavel"])
    advogados_nao_mapeados = _contar_nao_mapeados(
    advogado_antes, df["advogado_responsavel"]
)
    if advogados_nao_mapeados > 0:
        logger.warning(
        f"advogado_responsavel: {advogados_nao_mapeados} valores não "
        f"estavam no mapa. Considere atualizar MAPA_ADVOGADOS."
    )

    # Vara (nome próprio)
    df["vara"] = normalizar_nome_proprio_serie(df["vara"])

    # Observações (texto livre, só strip) 
    df["observacoes"] = df["observacoes"].astype(str).str.strip()
    df["observacoes"] = df["observacoes"].replace(
        {"nan": np.nan, "none": np.nan, "": np.nan}
    )

    # 8. Número do processo (identificador, só strip) 
    df["numero_processo"] = df["numero_processo"].astype(str).str.strip()
    df["numero_processo"] = df["numero_processo"].replace(
        {"nan": np.nan, "none": np.nan, "": np.nan}
    )

    # 9. Datas 
    df["data_abertura"] = padronizar_data_serie(df["data_abertura"])
    datas_abertura_invalidas = df["data_abertura"].isna().sum()
    if datas_abertura_invalidas > nulos_antes.get("data_abertura", 0):
        logger.warning(
            f"data_abertura: "
            f"{datas_abertura_invalidas - nulos_antes.get('data_abertura', 0)} "
            f"valores não parseáveis viraram NaT"
        )

    df["prazo_proximo"] = padronizar_data_serie(df["prazo_proximo"])
    # prazo_proximo já tinha 398 nulos originalmente (não é erro, é dado faltante).

    # Valor da causa: padroniza + imputa mediana 
    df["valor_causa"] = padronizar_valor_monetario_serie(df["valor_causa"])

    nulos_valor_causa = df["valor_causa"].isna().sum()
    mediana_valor_causa = df["valor_causa"].median()

    if pd.isna(mediana_valor_causa):
        logger.error(
            "valor_causa: TODOS os valores são nulos! "
            "Impossível calcular mediana. Mantendo como NaN."
        )
    else:
        logger.info(
            f"valor_causa: imputando {nulos_valor_causa} nulos com "
            f"mediana = R$ {mediana_valor_causa:,.2f}"
        )
        logger.warning(
            "ATENÇÃO: estratégia de imputação por mediana em valor_causa "
            "precisa ser confirmada com o cliente. "
            "Pode existir motivo de negócio pra valor nulo."
        )
        df["valor_causa"] = df["valor_causa"].fillna(mediana_valor_causa)

    # Deduplicação por numero_processo ────────────────────────────────
    # Mantém o registro com data_abertura mais recente quando o mesmo
    # numero_processo aparece em múltiplas linhas (duplicata parcial).
    # Feito APÓS a limpeza de data_abertura para que o sort seja correto.
    n_antes_dedup_np = len(df)
    df = (
        df.sort_values("data_abertura", ascending=False, na_position="last")
        .drop_duplicates(subset=["numero_processo"])
        .reset_index(drop=True)
    )
    duplicatas_numero_processo = n_antes_dedup_np - len(df)
    if duplicatas_numero_processo > 0:
        logger.info(
            f"Processos duplicados por numero_processo: {duplicatas_numero_processo} removidos "
            f"(mantendo o mais recente por data_abertura)."
        )

    # Diagnóstico final
    nulos_depois = df.isna().sum().to_dict()
    logger.info(f"Nulos por coluna (depois): {nulos_depois}")
    logger.info(f"Linhas finais: {len(df)}")

    # Estatísticas pra retorno 
    estatisticas = {
        "tabela": "processos",
        "linhas_iniciais": linhas_iniciais,
        "linhas_finais": len(df),
        "duplicatas_removidas": int(duplicatas),
        "duplicatas_numero_processo_removidas": int(duplicatas_numero_processo),
        "nulos_antes": {k: int(v) for k, v in nulos_antes.items()},
        "nulos_depois": {k: int(v) for k, v in nulos_depois.items()},
        "valor_causa": {
            "nulos_imputados": int(nulos_valor_causa),
            "mediana_usada": (
                float(mediana_valor_causa)
                if not pd.isna(mediana_valor_causa)
                else None
            ),
        },
        "status_nao_mapeados": int(status_nao_mapeados),
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

    df = ler_planilha("processos")
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

    print(f"\nValores únicos de 'tipo':")
    print(df_limpo["tipo"].value_counts(dropna=False).to_string())

    print(f"\nValores únicos de 'fase':")
    print(df_limpo["fase"].value_counts(dropna=False).to_string())

    print(f"\nValores únicos de 'status':")
    print(df_limpo["status"].value_counts(dropna=False).to_string())

    print(f"\nValores únicos de 'advogado_responsavel':")
    print(df_limpo["advogado_responsavel"].value_counts(dropna=False).to_string())

    print(f"\nEstatísticas de 'valor_causa':")
    print(df_limpo["valor_causa"].describe().to_string())