import argparse
import logging
from pathlib import Path

import pandas as pd

from fase1_engenharia.ingestao.ler_planilhas import ler_todas
from fase1_engenharia.limpeza.limpar_clientes import limpar as limpar_clientes
from fase1_engenharia.limpeza.limpar_honorarios import limpar as limpar_honorarios
from fase1_engenharia.limpeza.limpar_movimentacoes import limpar as limpar_movimentacoes
from fase1_engenharia.limpeza.limpar_processos import limpar as limpar_processos

logger = logging.getLogger(__name__)

# Roteamento: mapeia o nome da planilha pra função de limpeza correspondente.
# Cada função segue o contrato (df) → (df_limpo, estatisticas).
# Se chegar uma chave desconhecida, o pipeline avisa e pula — não quebra.
LIMPADORES = {
    "clientes": limpar_clientes,
    "processos": limpar_processos,
    "honorarios": limpar_honorarios,
    "movimentacoes": limpar_movimentacoes,
}


def executar_pipeline(
    dfs: dict[str, pd.DataFrame],
    salvar_csv: bool = False,
    pasta_saida: Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, dict]]:

    resultados: dict[str, pd.DataFrame] = {}
    estatisticas: dict[str, dict] = {}

    # Garante que a pasta de saída existe antes de começar a processar.
    # Assim não quebra no meio do pipeline ao tentar salvar o primeiro arquivo.
    if salvar_csv and pasta_saida is None:
        pasta_saida = Path("data") / "planilhas_limpos"

    if pasta_saida is not None:
        pasta_saida = Path(pasta_saida)
        pasta_saida.mkdir(parents=True, exist_ok=True)
        logger.info(f"Diretório de saída: {pasta_saida}")

    # Processa cada planilha na ordem em que foi carregada.
    # Falha em uma tabela não interrompe as demais.
    for nome, df in dfs.items():
        if nome not in LIMPADORES:
            logger.warning(f"Nenhum limpador disponível para '{nome}'. Pulando.")
            continue

        logger.info(f"Iniciando pipeline de limpeza para '{nome}'")
        limpo, stats = LIMPADORES[nome](df)
        resultados[nome] = limpo
        estatisticas[nome] = stats

    # ── Pós-limpeza: coerência temporal entre tabelas ─────────────────────────
    # Ordem: (1) remove processos temporalmente incoerentes; (2) cascateia o
    # drop nas filhas (honorários/movimentações órfãos); (3) aplica a coerência
    # de datas das filhas contra a data_abertura. Tudo ANTES de salvar os CSVs.

    # (1) Drop de processos incoerentes (prazo<abertura OU abertura<cliente).
    if "processos" in resultados and "clientes" in resultados:
        from fase1_engenharia.limpeza.integridade_referencial import (
            remover_processos_incoerentes,
        )

        resultados["processos"], stats_proc = remover_processos_incoerentes(
            resultados["processos"], resultados["clientes"]
        )
        numeros_validos = set(
            resultados["processos"]["numero_processo"].dropna()
        )
        estatisticas.setdefault("processos", {})
        estatisticas["processos"]["coerencia_temporal"] = {
            k: v for k, v in stats_proc.items() if k != "numeros_removidos"
        }

        # (2) Cascata: remove órfãos nas filhas.
        from fase1_engenharia.limpeza.integridade_referencial import (
            remover_orfaos_por_processo,
        )
        for filha in ("honorarios", "movimentacoes"):
            if filha in resultados:
                resultados[filha], stats_orfaos = remover_orfaos_por_processo(
                    resultados[filha], numeros_validos, filha.capitalize()
                )
                estatisticas.setdefault(filha, {})
                estatisticas[filha]["cascata_orfaos"] = stats_orfaos

    # (3) Coerência temporal das filhas contra a data_abertura do processo.
    if "movimentacoes" in resultados and "processos" in resultados:
        from fase1_engenharia.limpeza.integridade_referencial import (
            remover_movimentacoes_anteriores_abertura,
        )

        resultados["movimentacoes"], stats_coerencia = (
            remover_movimentacoes_anteriores_abertura(
                resultados["movimentacoes"], resultados["processos"]
            )
        )
        # Anexa as estatísticas da coerência temporal ao bloco de movimentacoes.
        estatisticas.setdefault("movimentacoes", {})
        estatisticas["movimentacoes"]["coerencia_temporal"] = stats_coerencia

    if "honorarios" in resultados and "processos" in resultados:
        from fase1_engenharia.limpeza.integridade_referencial import (
            remover_honorarios_anteriores_abertura,
        )

        resultados["honorarios"], stats_coerencia_hon = (
            remover_honorarios_anteriores_abertura(
                resultados["honorarios"], resultados["processos"]
            )
        )
        estatisticas.setdefault("honorarios", {})
        estatisticas["honorarios"]["coerencia_temporal"] = stats_coerencia_hon

    # (4) Drop de clientes sem processo vinculado (decisão de escopo).
    # Roda por ÚLTIMO: depends do estado final de processos (já sem incoerentes).
    if "clientes" in resultados and "processos" in resultados:
        from fase1_engenharia.limpeza.integridade_referencial import (
            remover_clientes_sem_processo,
        )

        resultados["clientes"], stats_cli_sem_proc = (
            remover_clientes_sem_processo(
                resultados["clientes"], resultados["processos"]
            )
        )
        estatisticas.setdefault("clientes", {})
        estatisticas["clientes"]["clientes_sem_processo"] = stats_cli_sem_proc

    # ── Normalização de IDs sequenciais ──────────────────────────────────────
    # Reatribui IDs numéricos a partir de 1, preservando todos os outros dados.
    # cliente_id precisa propagar para as tabelas filhas; os demais são standalone.
    if resultados:
        # cliente_id: cria mapa antigo→novo e propaga somente para processos (FK direta)
        if "clientes" in resultados:
            df_cli = resultados["clientes"].sort_values("cliente_id").reset_index(drop=True)
            mapa_cliente = dict(zip(df_cli["cliente_id"], range(1, len(df_cli) + 1)))
            df_cli["cliente_id"] = range(1, len(df_cli) + 1)
            resultados["clientes"] = df_cli
            if "processos" in resultados:
                resultados["processos"]["cliente_id"] = resultados["processos"]["cliente_id"].map(mapa_cliente)

        # IDs standalone: apenas reordena e reatribui sequencialmente
        for tabela, col_id in [("processos", "processo_id"), ("honorarios", "honorario_id"), ("movimentacoes", "movimentacao_id")]:
            if tabela in resultados and col_id in resultados[tabela].columns:
                df_t = resultados[tabela].sort_values(col_id).reset_index(drop=True)
                df_t[col_id] = range(1, len(df_t) + 1)
                resultados[tabela] = df_t

        # cliente_id em honorarios: derivado via numero_processo → processos
        # Mais confiável que mapear pelo ID antigo, pois evita nulos por cascata de remoções.
        if "honorarios" in resultados and "processos" in resultados:
            proc_cli = resultados["processos"][["numero_processo", "cliente_id"]]
            df_hon = resultados["honorarios"].copy()
            cliente_derivado = df_hon[["numero_processo"]].merge(
                proc_cli, on="numero_processo", how="left"
            )["cliente_id"]
            df_hon["cliente_id"] = cliente_derivado.values
            resultados["honorarios"] = df_hon

    # ── Gravação dos CSVs (após toda transformação concluída) ─────────────────
    if salvar_csv and pasta_saida is not None:
        for nome, limpo in resultados.items():
            arquivo_saida = pasta_saida / f"{nome}_limpo.csv"
            limpo.to_csv(arquivo_saida, index=False, encoding="utf-8-sig")
            logger.info(f"Salvo CSV limpo: {arquivo_saida}")

    return resultados, estatisticas


def imprimir_resumo(estatisticas: dict[str, dict]) -> None:
    # Imprime as estatísticas de cada tabela no terminal pra conferência rápida.
    # O detalhe completo fica nos logs — aqui é só o resumo executivo.
    print("\n" + "=" * 60)
    print("RESUMO DO PIPELINE DE LIMPEZA")
    print("=" * 60)
    for nome, stats in estatisticas.items():
        print(f"\n[{nome}]")
        for chave, valor in stats.items():
            print(f"  {chave}: {valor}")


def criar_parser() -> argparse.ArgumentParser:
    # CLI com três flags opcionais — tudo tem default seguro pra rodar sem argumentos.
    parser = argparse.ArgumentParser(
        description="Pipeline de limpeza de dados das planilhas do projeto."
    )
    parser.add_argument(
        "--salvar-csv",
        action="store_true",
        help="Salvar os DataFrames limpos em CSV no diretório de saída.",
    )
    parser.add_argument(
        "--pasta-saida",
        type=Path,
        default=Path("data") / "planilhas_limpos",
        help="Pasta onde os CSVs limpos serão gravados.",
    )
    parser.add_argument(
        "--planilhas",
        nargs="*",
        choices=list(LIMPADORES),
        help="Planilhas específicas a serem limpas. Se omitido, limpa todas.",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = criar_parser()
    args = parser.parse_args()

    # Carrega só as planilhas pedidas pra não falhar quando arquivos ausentes.
    # Se --planilhas não for passado, carrega todas as quatro.
    if args.planilhas:
        from fase1_engenharia.ingestao.ler_planilhas import ler_planilha
        dfs = {nome: ler_planilha(nome) for nome in args.planilhas}
    else:
        dfs = ler_todas()

    limpos, estatisticas = executar_pipeline(
        dfs, salvar_csv=args.salvar_csv, pasta_saida=args.pasta_saida
    )

    imprimir_resumo(estatisticas)

    if args.salvar_csv:
        logger.info("Pipeline concluído com saída em CSV.")
    else:
        logger.info("Pipeline concluído sem gravação de arquivos.")


if __name__ == "__main__":
    main()