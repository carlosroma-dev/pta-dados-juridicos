from datetime import date, datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from fase1_engenharia.db.database import Base

# ──────────────────────────────────────────────────────────────────────────────
# MODELOS ORM (SQLAlchemy)
#
# Cada classe aqui representa uma tabela no banco PostgreSQL.
# Os atributos da classe viram colunas da tabela.
# O SQLAlchemy traduz operações Python (db.query, db.add...) em SQL.
# ──────────────────────────────────────────────────────────────────────────────

class Advogado(Base):
    __tablename__ = "advogados"

    id_advogado = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)  # campo obrigatório


class Cliente(Base):
    __tablename__ = "clientes"

    id_cliente = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    # O atributo Python é "cpf" (minúsculo), mas a coluna no banco
    # se chama "CPF" (maiúsculo) — conforme definido no schema.sql.
    cpf = Column("CPF", String, unique=True)
    email = Column(String)
    contato = Column(String)
    data_cadastro = Column(DateTime)
    cidade = Column(String)

    # relationship diz ao SQLAlchemy que um cliente pode ter vários processos.
    # back_populates mantém os dois lados sincronizados: processo.cliente e cliente.processos.
    processos = relationship("Processo", back_populates="cliente")


class Processo(Base):
    __tablename__ = "processos"

    # id_processos existe mas NÃO é a chave primária.
    # A PK é numero_processo (string no formato CNJ).
    id_processos = Column(Integer, nullable=False)
    numero_processo = Column(String, primary_key=True)
    tipo = Column(String)        # ex: civel, trabalhista, criminal
    cliente_id = Column(Integer, ForeignKey("clientes.id_cliente"))
    advogado_id = Column(Integer)  # referencia advogados, mas sem FK declarada no schema
    status = Column(String)      # ex: ativo, encerrado, acordo, em_recurso
    fase = Column(String)        # ex: instrucao, sentenca, recurso
    prazo_proximo = Column(Date) # data do próximo prazo do processo
    valor_causa = Column(Float)
    data_abertura = Column(DateTime)
    vara = Column(String)        # ex: 5ª Vara Cível De Recife
    observacoes = Column(String)

    cliente = relationship("Cliente", back_populates="processos")
    honorarios = relationship("Honorario", back_populates="processo")
    movimentacoes = relationship("Movimentacao", back_populates="processo")


class Honorario(Base):
    __tablename__ = "honorarios"

    id_honorarios = Column(Integer, primary_key=True)
    # FK para processos usando o numero_processo (varchar) como chave
    processo_numero = Column(String, ForeignKey("processos.numero_processo"))
    status_pagamento = Column(String)       # ex: quitado, em_dia, atrasado
    data_contrato = Column(Date)
    data_vencimento = Column(Date)
    numero_parcelas = Column(Integer)
    parcelas_pagas = Column(Integer)
    valor_total_contratado = Column(Float)
    valor_pago = Column(Float)
    valor_em_aberto = Column(Float)
    forma_pagamento = Column(String)        # ex: pix, boleto, ted
    honorario_exito = Column(Boolean)       # se há cláusula de êxito
    percentual_exito = Column(Float)        # percentual cobrado em caso de êxito (0 a 1)

    processo = relationship("Processo", back_populates="honorarios")


class Movimentacao(Base):
    __tablename__ = "movimentacoes"

    id_movimentacao = Column(Integer, primary_key=True)
    # FK para processos usando numero_processo como chave
    processo_numero = Column(String, ForeignKey("processos.numero_processo"))
    tipo_ato = Column(String)    # ex: audiencia, despacho, sentenca
    data_evento = Column(Date)
    descricao = Column(Text)     # texto livre com detalhes do ato
    prazo_gerado = Column(Date)  # prazo que esse ato gerou (quando há)
    concluido = Column(Boolean)

    processo = relationship("Processo", back_populates="movimentacoes")


class DocumentoChunk(Base):
    """Armazena trechos de documentos PDF com seus embeddings para busca semântica (RAG)."""

    __tablename__ = "documento_chunks"

    id_chunk = Column(Integer, primary_key=True)
    movimentacao_id = Column(Integer, ForeignKey("movimentacoes.id_movimentacao"))
    conteudo = Column(Text)          # texto do trecho do documento
    embedding = Column(Vector(768)) # vetor numérico gerado pelo modelo de embedding
    processo_numero = Column(String)
    documento_fonte = Column(String)
    tipo_documento = Column(String)


# ──────────────────────────────────────────────────────────────────────────────
# SCHEMAS PYDANTIC (serialização da API)
#
# Definem o formato JSON que a API retorna.
# São diferentes dos modelos ORM — servem só pra entrada/saída da API.
# from_attributes=True permite converter um objeto SQLAlchemy direto pra JSON.
# ──────────────────────────────────────────────────────────────────────────────

class ClienteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_cliente: int
    nome: str
    cpf: Optional[str] = None
    email: Optional[str] = None
    contato: Optional[str] = None
    data_cadastro: Optional[datetime] = None
    cidade: Optional[str] = None


class ProcessoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero_processo: str
    tipo: Optional[str] = None
    cliente_id: Optional[int] = None
    status: Optional[str] = None
    fase: Optional[str] = None
    prazo_proximo: Optional[date] = None
    valor_causa: Optional[float] = None
    data_abertura: Optional[datetime] = None
    vara: Optional[str] = None


class HonorarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_honorarios: int
    processo_numero: Optional[str] = None
    valor_total_contratado: Optional[float] = None
    status_pagamento: Optional[str] = None
    data_vencimento: Optional[date] = None

class DocumentoIngestao(Base):
    """Registro de cada PDF enviado pela interface de ingestão.

    Duas funções:
      1. Auditoria — nome, data e status final de cada documento ingerido.
      2. Feedback em tempo real — a interface faz polling do `status` para
         mostrar o progresso ("extraindo", "indexando", "concluido"...).

    O `status` percorre o ciclo:
        recebido → extraindo → estruturando → indexando → concluido
    e, em qualquer falha, vai para `erro` com uma `mensagem_erro` amigável
    (sem stack trace — o cliente nunca vê detalhe técnico).
    """

    __tablename__ = "documentos_ingestao"

    id_ingestao = Column(Integer, primary_key=True, autoincrement=True)
    nome_arquivo = Column(String, nullable=False)    # nome salvo em disco (pode ter sufixo de timestamp)
    nome_original = Column(String)                   # nome que o usuário enviou (exibição amigável)
    data_ingestao = Column(DateTime)                 # quando o upload entrou
    atualizado_em = Column(DateTime)                 # última mudança de status (debug / detectar travamento)
    status = Column(String, nullable=False, default="recebido")
    mensagem_erro = Column(Text)                     # mensagem amigável em caso de falha
    num_chunks = Column(Integer)                     # quantos chunks foram indexados (preenchido ao concluir)
    processo_numero = Column(String)                 # extraído na estruturação (pode ser None)
    tipo_documento = Column(String)                  # extraído na estruturação (pode ser None)
    arquivado_drive = Column(Boolean, default=False) # hook do Drive (preenchido na fase de arquivamento)