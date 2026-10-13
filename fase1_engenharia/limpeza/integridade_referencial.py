import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Verificações de Foreign Keys

def _verificar_fk(
    df_filho: pd.DataFrame,
    coluna_fk: str,
    df_pai: pd.DataFrame,
    coluna_pk: str,
    nome_relacao: str,
) -> dict:

    # Conjunto de IDs válidos (existentes em df_pai)
    ids_validos = set(df_pai[coluna_pk].dropna().unique())

    # Detecta linhas órfãs (cuja FK não está em ids_validos)
    mascara_orfaos = ~df_filho[coluna_fk].isin(ids_validos)

    # Ignora linhas onde a FK em si é nula (não é órfã, é desconhecida)
    mascara_orfaos &= df_filho[coluna_fk].notna()

    linhas_orfas = int(mascara_orfaos.sum())
    ids_orfaos = df_filho.loc[mascara_orfaos, coluna_fk].unique().tolist()

    resultado = {
        "relacao": nome_relacao,
        "linhas_orfas": linhas_orfas,
        "ids_orfaos_unicos": len(ids_orfaos),
        "amostra_ids_orfaos": ids_orfaos[:10],
    }

    if linhas_orfas > 0:
        logger.warning(
            f"{nome_relacao}: {linhas_orfas} linhas órfãs "
            f"({len(ids_orfaos)} IDs únicos não existem). "
            f"Amostra: {ids_orfaos[:5]}"
        )
    else:
        logger.info(f"{nome_relacao}: OK (sem órfãos)")

    return resultado


# Verificações de consistência cruzada

def _verificar_valor_em_aberto(df_honorarios: pd.DataFrame, tolerancia: float = 0.01) -> dict:

    df = df_honorarios

    # Só verifica linhas onde os 3 valores existem
    mascara_validavel = (
        df["valor_total_contratado"].notna()
        & df["valor_pago"].notna()
        & df["valor_em_aberto"].notna()
    )

    df_validavel = df[mascara_validavel].copy()
    total_validavel = len(df_validavel)

    if total_validavel == 0:
        logger.warning("valor_em_aberto: nenhuma linha tem os 3 valores pra validar")
        return {
            "total_validavel": 0,
            "linhas_inconsistentes": 0,
            "maior_divergencia": None,
            "amostra_inconsistentes": [],
        }

    # Calcula o esperado e a diferença
    esperado = (
        df_validavel["valor_total_contratado"] - df_validavel["valor_pago"]
    )
    diferenca = (df_validavel["valor_em_aberto"] - esperado).abs()

    # Detecta inconsistências (diferença > tolerância)
    mascara_inconsistente = diferenca > tolerancia
    linhas_inconsistentes = int(mascara_inconsistente.sum())

    maior_divergencia = float(diferenca.max()) if total_validavel > 0 else 0.0

    ids_problematicos = (
        df_validavel.loc[mascara_inconsistente, "honorario_id"]
        .head(5)
        .tolist()
    )

    resultado = {
        "total_validavel": total_validavel,
        "linhas_inconsistentes": linhas_inconsistentes,
        "maior_divergencia": maior_divergencia,
        "amostra_inconsistentes": ids_problematicos,
    }

    if linhas_inconsistentes > 0:
        logger.warning(
            f"valor_em_aberto: {linhas_inconsistentes}/{total_validavel} linhas "
            f"não batem com (total - pago). Maior divergência: "
            f"R$ {maior_divergencia:.2f}. Amostra IDs: {ids_problematicos}"
        )
    else:
        logger.info(
            f"valor_em_aberto: OK ({total_validavel} linhas validadas, "
            f"todas dentro da tolerância de R$ {tolerancia:.2f})"
        )

    return resultado


# Transformações de coerência temporal
# Diferente das funções _verificar_* acima (que só observam), estas MODIFICAM
# o DataFrame, removendo linhas temporalmente incoerentes contra a
# data_abertura do processo correspondente.

def remover_anteriores_abertura(
    df_filho: pd.DataFrame,
    df_processos: pd.DataFrame,
    coluna_data: str,
    nome_tabela: str,
    coluna_fk: str = "numero_processo",
) -> tuple[pd.DataFrame, dict]:
    """
    Remove linhas de df_filho cuja `coluna_data` é anterior à data_abertura do
    processo correspondente (ligação por `coluna_fk` → processos.numero_processo).

    Regra (decidida com a equipe):
      - Linha no MESMO DIA da abertura é mantida (data >= data_abertura).
      - Linha SEM data (NaT) na coluna comparada é removida: sem data não há
        como validar a coerência temporal.
      - Linha cujo processo não tem data_abertura (NaT) é mantida: sem
        referência, não dá pra afirmar incoerência.

    Retorna (df_filtrado, estatisticas).
    """
    df = df_filho.copy()
    linhas_iniciais = len(df)

    datas_proc = df_processos[["numero_processo", "data_abertura"]].rename(
        columns={
            "data_abertura": "_data_abertura_processo",
            "numero_processo": coluna_fk,
        }
    )
    df = df.merge(datas_proc, on=coluna_fk, how="left")

    data_filho = pd.to_datetime(df[coluna_data], errors="coerce")
    data_proc = pd.to_datetime(df["_data_abertura_processo"], errors="coerce")

    anterior = data_filho < data_proc
    sem_data = data_filho.isna()
    proc_sem_data = data_proc.isna()

    # Remove se anterior OU sem data própria. Quando o processo não tem data,
    # só remove se a própria linha também não tiver data (sem referência).
    remover = (anterior | sem_data) & (~proc_sem_data | sem_data)

    n_anteriores = int((anterior & ~sem_data).sum())
    n_sem_data = int(sem_data.sum())

    df_filtrado = (
        df.loc[~remover]
        .drop(columns=["_data_abertura_processo"])
        .reset_index(drop=True)
    )

    removidas = linhas_iniciais - len(df_filtrado)
    logger.info(
        f"Coerência temporal {nome_tabela} ({coluna_data} vs data_abertura): "
        f"{removidas} removidas ({linhas_iniciais} → {len(df_filtrado)}). "
        f"Anteriores à abertura: {n_anteriores}; sem data: {n_sem_data}."
    )

    estatisticas = {
        "coluna_comparada": coluna_data,
        "linhas_iniciais": linhas_iniciais,
        "linhas_finais": len(df_filtrado),
        "removidas_total": int(removidas),
        "removidas_anteriores_abertura": n_anteriores,
        "removidas_sem_data": n_sem_data,
    }

    return df_filtrado, estatisticas


def remover_movimentacoes_anteriores_abertura(
    df_movimentacoes: pd.DataFrame,
    df_processos: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Wrapper: aplica a coerência temporal a Movimentacoes (data_movimentacao)."""
    return remover_anteriores_abertura(
        df_movimentacoes,
        df_processos,
        coluna_data="data_movimentacao",
        nome_tabela="Movimentacoes",
    )


def remover_honorarios_anteriores_abertura(
    df_honorarios: pd.DataFrame,
    df_processos: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """Wrapper: aplica a coerência temporal a Honorarios (data_vencimento)."""
    return remover_anteriores_abertura(
        df_honorarios,
        df_processos,
        coluna_data="data_vencimento",
        nome_tabela="Honorarios",
    )


def remover_processos_incoerentes(
    df_processos: pd.DataFrame,
    df_clientes: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """
    Remove processos temporalmente incoerentes por DOIS critérios (união):
      Critério 1: prazo_proximo < data_abertura (prazo no passado da abertura).
      Critério 2: data_abertura < data_inicio do cliente (processo aberto antes
                  de o cliente existir no sistema).

    Bordas:
      - NaT em prazo_proximo NÃO aciona o critério 1 (sem prazo ≠ incoerente).
      - NaT em data_inicio do cliente NÃO aciona o critério 2 (sem referência).
      - NaT em data_abertura: não há como avaliar nenhum dos dois → mantém.

    Retorna (df_filtrado, estatisticas). A lista de numero_processo removidos
    fica em estatisticas["numeros_removidos"] para o cascateamento nas filhas.
    """
    df = df_processos.copy()
    linhas_iniciais = len(df)

    cli = df_clientes[["cliente_id", "data_inicio"]].rename(
        columns={"data_inicio": "_data_inicio_cliente"}
    )
    df_m = df.merge(cli, on="cliente_id", how="left")

    da = pd.to_datetime(df_m["data_abertura"], errors="coerce")
    pp = pd.to_datetime(df_m["prazo_proximo"], errors="coerce")
    di = pd.to_datetime(df_m["_data_inicio_cliente"], errors="coerce")

    criterio1 = pp < da               # NaT em pp ou da → False (não remove)
    criterio2 = da < di               # NaT em da ou di → False (não remove)
    remover = criterio1 | criterio2

    n_c1 = int(criterio1.sum())
    n_c2 = int(criterio2.sum())
    n_ambos = int((criterio1 & criterio2).sum())

    df_filtrado = df.loc[~remover.values].reset_index(drop=True)
    numeros_removidos = (
        df.loc[remover.values, "numero_processo"].dropna().unique().tolist()
    )
    removidas = linhas_iniciais - len(df_filtrado)

    logger.info(
        f"Coerência Processos: {removidas} removidos "
        f"({linhas_iniciais} → {len(df_filtrado)}). "
        f"Crit1 (prazo<abertura): {n_c1}; Crit2 (abertura<cliente): {n_c2}; "
        f"ambos: {n_ambos}."
    )

    estatisticas = {
        "linhas_iniciais": linhas_iniciais,
        "linhas_finais": len(df_filtrado),
        "removidos_total": int(removidas),
        "removidos_criterio1_prazo": n_c1,
        "removidos_criterio2_cliente": n_c2,
        "removidos_ambos": n_ambos,
        "numeros_removidos": numeros_removidos,
    }

    return df_filtrado, estatisticas


def remover_orfaos_por_processo(
    df_filho: pd.DataFrame,
    numeros_validos: set,
    nome_tabela: str,
    coluna_fk: str = "numero_processo",
) -> tuple[pd.DataFrame, dict]:
    """
    Remove linhas de df_filho cujo numero_processo não está em `numeros_validos`
    (cascata após o drop de processos). Uma movimentação/honorário sem processo
    válido é órfã por definição aqui.
    """
    df = df_filho.copy()
    linhas_iniciais = len(df)
    mascara_valida = df[coluna_fk].isin(numeros_validos)
    df_filtrado = df.loc[mascara_valida].reset_index(drop=True)
    removidas = linhas_iniciais - len(df_filtrado)

    logger.info(
        f"Cascata {nome_tabela}: {removidas} órfãos removidos "
        f"({linhas_iniciais} → {len(df_filtrado)}) após drop de processos."
    )

    return df_filtrado, {
        "linhas_iniciais": linhas_iniciais,
        "linhas_finais": len(df_filtrado),
        "orfaos_removidos": int(removidas),
    }


def remover_clientes_sem_processo(
    df_clientes: pd.DataFrame,
    df_processos: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """
    Remove clientes que não estão vinculados a nenhum processo (decisão de
    escopo: manter apenas o núcleo conectado de dados).

    ATENÇÃO: cliente sem processo é um estado VÁLIDO no schema (a FK é
    processos.cliente_id → clientes, não o inverso). Estes registros não são
    incoerentes; são removidos por decisão de negócio, não por integridade.
    """
    df = df_clientes.copy()
    linhas_iniciais = len(df)

    clientes_com_processo = set(df_processos["cliente_id"].dropna())
    mascara_mantem = df["cliente_id"].isin(clientes_com_processo)
    df_filtrado = df.loc[mascara_mantem].reset_index(drop=True)
    removidas = linhas_iniciais - len(df_filtrado)

    logger.info(
        f"Clientes sem processo: {removidas} removidos "
        f"({linhas_iniciais} → {len(df_filtrado)}). "
        f"DECISÃO DE ESCOPO — não é incoerência."
    )

    return df_filtrado, {
        "linhas_iniciais": linhas_iniciais,
        "linhas_finais": len(df_filtrado),
        "clientes_sem_processo_removidos": int(removidas),
    }


# Orquestrador

def verificar_integridade(dfs: dict[str, pd.DataFrame]) -> dict:

    logger.info("=" * 60)
    logger.info("Iniciando verificação de integridade referencial")
    logger.info("=" * 60)

    # ── Foreign Keys ──────────────────────────────────────────────────
    fk_processos_clientes = _verificar_fk(
        df_filho=dfs["processos"],
        coluna_fk="cliente_id",
        df_pai=dfs["clientes"],
        coluna_pk="cliente_id",
        nome_relacao="Processos.cliente_id → Clientes",
    )

    fk_honorarios_clientes = _verificar_fk(
        df_filho=dfs["honorarios"],
        coluna_fk="cliente_id",
        df_pai=dfs["clientes"],
        coluna_pk="cliente_id",
        nome_relacao="Honorarios.cliente_id → Clientes",
    )

    fk_honorarios_processos = _verificar_fk(
        df_filho=dfs["honorarios"],
        coluna_fk="numero_processo",
        df_pai=dfs["processos"],
        coluna_pk="numero_processo",
        nome_relacao="Honorarios.numero_processo → Processos",
    )

    fk_movimentacoes_processos = _verificar_fk(
        df_filho=dfs["movimentacoes"],
        coluna_fk="numero_processo",
        df_pai=dfs["processos"],
        coluna_pk="numero_processo",
        nome_relacao="Movimentacoes.numero_processo → Processos",
    )

    # Consistência cruzada
    consistencia_valor_aberto = _verificar_valor_em_aberto(dfs["honorarios"])

    # Resumo 
    relatorio = {
        "foreign_keys": {
            "processos_clientes": fk_processos_clientes,
            "honorarios_clientes": fk_honorarios_clientes,
            "honorarios_processos": fk_honorarios_processos,
            "movimentacoes_processos": fk_movimentacoes_processos,
        },
        "consistencia_cruzada": {
            "valor_em_aberto": consistencia_valor_aberto,
        },
    }

    # Total de problemas detectados
    total_orfaos = sum(
        v["linhas_orfas"] for v in relatorio["foreign_keys"].values()
    )
    total_inconsistencias = consistencia_valor_aberto["linhas_inconsistentes"]

    logger.info("=" * 60)
    logger.info(
        f"Resumo: {total_orfaos} linhas órfãs, "
        f"{total_inconsistencias} inconsistências em valor_em_aberto"
    )
    logger.info("=" * 60)

    return relatorio


# teste rápido


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Importa os limpadores pra ter os DFs limpos pra testar
    from fase1_engenharia.ingestao.ler_planilhas import ler_todas
    from fase1_engenharia.limpeza.limpar_clientes import limpar as limpar_clientes
    from fase1_engenharia.limpeza.limpar_honorarios import limpar as limpar_honorarios
    from fase1_engenharia.limpeza.limpar_movimentacoes import (
        limpar as limpar_movimentacoes,
    )
    from fase1_engenharia.limpeza.limpar_processos import limpar as limpar_processos

    # Lê e limpa tudo
    print("Lendo e limpando planilhas...")
    dfs_brutos = ler_todas()

    dfs_limpos = {}
    dfs_limpos["clientes"], _ = limpar_clientes(dfs_brutos["clientes"])
    dfs_limpos["processos"], _ = limpar_processos(dfs_brutos["processos"])
    dfs_limpos["honorarios"], _ = limpar_honorarios(dfs_brutos["honorarios"])
    dfs_limpos["movimentacoes"], _ = limpar_movimentacoes(
        dfs_brutos["movimentacoes"]
    )

    # Roda verificações
    print("\n")
    relatorio = verificar_integridade(dfs_limpos)

    # Imprime relatório
    print("\n" + "=" * 60)
    print("RELATÓRIO DE INTEGRIDADE")
    print("=" * 60)

    print("\n--- Foreign Keys ---")
    for nome, dados in relatorio["foreign_keys"].items():
        print(f"\n[{nome}]")
        for k, v in dados.items():
            print(f"  {k}: {v}")

    print("\n--- Consistência cruzada ---")
    for nome, dados in relatorio["consistencia_cruzada"].items():
        print(f"\n[{nome}]")
        for k, v in dados.items():
            print(f"  {k}: {v}")