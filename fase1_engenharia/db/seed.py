"""
Popula o banco relacional a partir das planilhas limpas.

Ordem de inserção respeita as chaves estrangeiras (FKs):
  advogados → clientes → processos → honorarios → movimentacoes

Mapeamento coluna do CSV → coluna do banco:
  clientes:      cpf → "CPF" | data_inicio → data_cadastro
  processos:     numero_processo é a PK (varchar, formato CNJ)
  honorarios:    n_parcelas → numero_parcelas | numero_processo → processo_numero
  movimentacoes: data_movimentacao → data_evento | numero_processo → processo_numero
"""

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from fase1_engenharia.db.database import SessionLocal, engine
from fase1_engenharia.db.models import (
    Advogado,
    Cliente,
    Honorario,
    Movimentacao,
    Processo,
)
from fase1_engenharia.ingestao.ler_planilhas import ler_todas
from fase1_engenharia.limpeza.pipeline import executar_pipeline

logger = logging.getLogger(__name__)

# Caminho para o arquivo SQL que cria as tabelas
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "docs" / "schema.sql"


def _criar_schema() -> None:
    """
    Lê o schema.sql e executa cada comando no banco.
    Se uma tabela ou tipo já existir, o erro é ignorado silenciosamente
    — assim o seed pode ser rodado mais de uma vez sem quebrar.
    """
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                conn.execute(text(stmt))
            except Exception as e:
                logger.debug(f"Schema: ignorado — {e}")
    logger.info("Schema verificado.")

# Tabelas na ordem em que serão limpas. TRUNCATE com CASCADE já cuida das
# dependências de FK, mas listamos todas explicitamente para deixar claro
# o que é zerado a cada execução.

_TABELAS = [
    "documentos_ingestao",
    "documento_chunks",
    "movimentacoes",
    "honorarios",
    "processo_advogados",
    "processos",
    "clientes",
    "advogados",
]


def _limpar_tabelas() -> None:
    """
    Esvazia todas as tabelas antes de popular, tornando o seed idempotente:
    pode ser rodado quantas vezes quiser sem dar UniqueViolation.

    RESTART IDENTITY zera contadores de sequência; CASCADE remove linhas
    dependentes via FK. Tudo num único TRUNCATE para ser atômico e rápido.
    """
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABELAS)} RESTART IDENTITY CASCADE"))
    logger.info("Tabelas limpas (seed idempotente).")

def _val(row, col):
    """
    Retorna o valor da coluna, ou None se for NaN.
    Necessário porque pandas representa campos vazios como NaN,
    mas o banco espera None (NULL).
    """
    v = row.get(col)
    return None if pd.isna(v) else v


def _to_date(val):
    """
    Converte um Timestamp do pandas para um objeto date do Python.
    O banco espera date/datetime — não Timestamp.
    """
    if val is None:
        return None
    return val.date() if hasattr(val, "date") else val


def _inserir_advogados(db: Session, df_processos: pd.DataFrame) -> dict[str, int]:
    """
    Extrai os nomes únicos de advogados da coluna 'advogado_responsavel'
    da planilha de processos e os insere na tabela advogados.

    Retorna um dicionário {nome: id_advogado} para ser usado depois
    na hora de popular o campo advogado_id em processos.
    """
    nomes = sorted(df_processos["advogado_responsavel"].dropna().unique())
    mapa = {}
    for i, nome in enumerate(nomes, start=1):
        db.add(Advogado(id_advogado=i, nome=nome))
        mapa[nome] = i

    # flush envia os INSERTs pro banco sem fazer commit definitivo.
    # Necessário para que os IDs existam quando inserirmos processos.
    db.flush()
    logger.info(f"advogados inseridos: {len(mapa)}")
    return mapa


def _inserir_clientes(db: Session, df: pd.DataFrame) -> None:
    """
    Insere todos os clientes no banco.
    Traduz os nomes de coluna do CSV para os campos do modelo ORM.
    """
    objs = [
        Cliente(
            id_cliente=int(row["cliente_id"]),
            nome=row["nome"],
            cpf=_val(row, "cpf"),            # CSV: "cpf" → banco: coluna "CPF"
            email=_val(row, "email"),
            contato=_val(row, "contato"),
            data_cadastro=_val(row, "data_inicio"),  # CSV: "data_inicio" → banco: "data_cadastro"
            cidade=_val(row, "cidade"),
        )
        for _, row in df.iterrows()
    ]
    db.bulk_save_objects(objs)  # insere todos de uma vez (mais rápido que um a um)
    db.flush()
    logger.info(f"clientes inseridos: {len(objs)}")


def _inserir_processos(
    db: Session, df: pd.DataFrame, mapa_advogados: dict[str, int]
) -> set[str]:
    """
    Insere os processos no banco.

    Como numero_processo é a PK (chave primária), duplicatas causariam erro.
    Por isso removemos duplicatas antes de inserir.

    Retorna um set com todos os numero_processo inseridos — usado pra
    checar órfãos em honorarios e movimentacoes.
    """
    # numero_processo é PK — remove duplicatas mantendo a primeira ocorrência
    duplicatas = df.duplicated(subset=["numero_processo"]).sum()
    if duplicatas > 0:
        logger.warning(f"processos: {duplicatas} numero_processo duplicados ignorados (PK única)")
        df = df.drop_duplicates(subset=["numero_processo"], keep="first")

    objs = []
    numeros_inseridos: set[str] = set()

    for _, row in df.iterrows():
        # Busca o id do advogado pelo nome usando o mapa gerado antes
        adv_nome = _val(row, "advogado_responsavel")
        adv_id = mapa_advogados.get(adv_nome) if adv_nome else None

        objs.append(
            Processo(
                id_processos=int(row["processo_id"]),
                numero_processo=row["numero_processo"],
                tipo=_val(row, "tipo"),
                cliente_id=int(row["cliente_id"]) if pd.notna(row["cliente_id"]) else None,
                advogado_id=adv_id,
                status=_val(row, "status"),
                fase=_val(row, "fase"),
                prazo_proximo=_to_date(_val(row, "prazo_proximo")),
                valor_causa=_val(row, "valor_causa"),
                data_abertura=_val(row, "data_abertura"),
                vara=_val(row, "vara"),
                observacoes=_val(row, "observacoes"),
            )
        )
        numeros_inseridos.add(row["numero_processo"])

    db.bulk_save_objects(objs)
    db.flush()
    logger.info(f"processos inseridos: {len(objs)}")
    return numeros_inseridos


def _inserir_processo_advogados(
    db: Session, df: pd.DataFrame, mapa_advogados: dict[str, int]
) -> None:
    """
    Popula a tabela de junção processo_advogados (relação N:N entre
    processos e advogados).

    Hoje a planilha traz um único 'advogado_responsavel' por processo,
    então cada processo gera um par. Mas o modelo é N:N por decisão de
    negócio (um processo PODE ter vários advogados), e esta função já
    fica preparada para múltiplos pares por processo quando a fonte de
    dados passar a fornecê-los.
    """
    # numero_processo é PK em processos — dedup mantendo a primeira ocorrência
    df = df.drop_duplicates(subset=["numero_processo"], keep="first")

    pares: list[dict] = []
    for _, row in df.iterrows():
        adv_nome = _val(row, "advogado_responsavel")
        adv_id = mapa_advogados.get(adv_nome) if adv_nome else None
        # processos sem advogado não geram vínculo
        if adv_id is None:
            continue
        pares.append({
            "numero_processo": row["numero_processo"],
            "advogado_id": adv_id,
        })

    if not pares:
        logger.warning("processo_advogados: nenhum par a inserir")
        return

    db.execute(
        text("""
            INSERT INTO processo_advogados (numero_processo, advogado_id)
            VALUES (:numero_processo, :advogado_id)
            ON CONFLICT (numero_processo, advogado_id) DO NOTHING
        """),
        pares,  # executemany: SQLAlchemy itera a lista de dicts
    )
    db.flush()
    logger.info(f"processo_advogados inseridos: {len(pares)}")

def _inserir_honorarios(
    db: Session, df: pd.DataFrame, numeros_validos: set[str]
) -> None:
    """
    Insere honorários no banco.

    Honorários órfãos (cujo numero_processo não existe em processos)
    são ignorados com aviso — evita erro de FK.
    """
    objs = []
    orfaos = 0

    for _, row in df.iterrows():
        num = _val(row, "numero_processo")

        # Se o processo não foi inserido, pula este honorário
        if num not in numeros_validos:
            orfaos += 1
            continue

        objs.append(
            Honorario(
                id_honorarios=int(row["honorario_id"]),
                processo_numero=num,          # FK varchar apontando para processos.numero_processo
                status_pagamento=_val(row, "status_pagamento"),
                data_contrato=_to_date(_val(row, "data_contrato")),
                data_vencimento=_to_date(_val(row, "data_vencimento")),
                # CSV usa "n_parcelas", banco usa "numero_parcelas"
                numero_parcelas=int(row["n_parcelas"]) if pd.notna(row.get("n_parcelas")) else None,
                parcelas_pagas=int(row["parcelas_pagas"]) if pd.notna(row.get("parcelas_pagas")) else None,
                valor_total_contratado=_val(row, "valor_total_contratado"),
                valor_pago=_val(row, "valor_pago"),
                valor_em_aberto=_val(row, "valor_em_aberto"),
                forma_pagamento=_val(row, "forma_pagamento"),
                honorario_exito=_val(row, "honorario_exito"),
                percentual_exito=_val(row, "percentual_exito"),
            )
        )

    if orfaos:
        logger.warning(f"honorarios ignorados (processo não encontrado): {orfaos}")
    db.bulk_save_objects(objs)
    db.flush()
    logger.info(f"honorarios inseridos: {len(objs)}")


def _inserir_movimentacoes(
    db: Session, df: pd.DataFrame, numeros_validos: set[str]
) -> None:
    """
    Insere movimentações no banco.

    Assim como honorários, movimentações órfãs são ignoradas.
    CSV: data_movimentacao → banco: data_evento
    """
    objs = []
    orfaos = 0

    for _, row in df.iterrows():
        num = _val(row, "numero_processo")

        # Se o processo não foi inserido, pula esta movimentação
        if num not in numeros_validos:
            orfaos += 1
            continue

        objs.append(
            Movimentacao(
                id_movimentacao=int(row["movimentacao_id"]),
                processo_numero=num,
                tipo_ato=_val(row, "tipo_ato"),
                data_evento=_to_date(_val(row, "data_movimentacao")),  # tradução de nome
                descricao=_val(row, "descricao"),
                prazo_gerado=_to_date(_val(row, "prazo_gerado")),
                concluido=_val(row, "concluido"),
            )
        )

    if orfaos:
        logger.warning(f"movimentacoes ignoradas (processo não encontrado): {orfaos}")
    db.bulk_save_objects(objs)
    db.flush()
    logger.info(f"movimentacoes inseridas: {len(objs)}")


def seed() -> None:
    """
    Função principal. Executa tudo na ordem certa:
    1. Cria as tabelas (se não existirem)
    2. Carrega e limpa as planilhas
    3. Insere no banco respeitando as chaves estrangeiras

    Se qualquer inserção falhar, faz rollback — o banco volta ao estado anterior.

    O seed é idempotente: as tabelas são truncadas antes de popular, então
    pode ser rodado quantas vezes quiser sem dar UniqueViolation.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    _criar_schema()
    _limpar_tabelas()

    logger.info("Carregando e limpando planilhas...")
    dfs_brutos = ler_todas()
    dfs, _ = executar_pipeline(dfs_brutos)

    db: Session = SessionLocal()
    try:
        logger.info("Iniciando seed do banco relacional...")

        mapa_advogados = _inserir_advogados(db, dfs["processos"])
        _inserir_clientes(db, dfs["clientes"])
        numeros_validos = _inserir_processos(db, dfs["processos"], mapa_advogados)
        _inserir_processo_advogados(db, dfs["processos"], mapa_advogados)
        _inserir_honorarios(db, dfs["honorarios"], numeros_validos)
        _inserir_movimentacoes(db, dfs["movimentacoes"], numeros_validos)

        # commit torna todas as inserções permanentes no banco
        db.commit()
        logger.info("Seed concluído com sucesso!")

    except Exception as e:
        # rollback desfaz tudo se qualquer coisa der errado
        db.rollback()
        logger.error(f"Erro no seed, rollback executado: {e}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed()
