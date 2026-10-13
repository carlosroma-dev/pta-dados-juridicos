CREATE EXTENSION IF NOT EXISTS vector;

-- ── clientes ────────────────────────────────────────────────────────────────
CREATE TABLE "clientes" (
  "id_cliente" integer PRIMARY KEY,
  "nome" varchar NOT NULL,
  "CPF" varchar UNIQUE,
  "email" varchar,
  "contato" varchar,
  "data_cadastro" timestamp DEFAULT (now()),
  "cidade" varchar
);

-- ── advogados ───────────────────────────────────────────────────────────────
CREATE TABLE "advogados" (
  "id_advogado" integer PRIMARY KEY,
  "nome" varchar NOT NULL
);

-- ── processos ─────────────────────────────────────────────────────────────────
-- PK = numero_processo (varchar), conforme decisão da equipe.
CREATE TABLE "processos" (
  "id_processos" integer NOT NULL,
  "numero_processo" varchar PRIMARY KEY,
  "tipo" varchar,
  "cliente_id" integer,
  "advogado_id" integer,
  "status" varchar,
  "fase" varchar,
  "prazo_proximo" date,
  "valor_causa" float,
  "data_abertura" timestamp DEFAULT (now()),
  "vara" varchar,
  "observacoes" varchar
);

CREATE TABLE "honorarios" (
  "id_honorarios" integer PRIMARY KEY,
  "processo_numero" varchar,
  "status_pagamento" varchar,
  "data_contrato" date,
  "data_vencimento" date,
  "numero_parcelas" integer,
  "parcelas_pagas" integer,
  "valor_total_contratado" float,
  "valor_pago" float,
  "valor_em_aberto" float,
  "forma_pagamento" varchar,
  "honorario_exito" bool,
  "percentual_exito" float
);

CREATE TABLE "movimentacoes" (
  "id_movimentacao" integer PRIMARY KEY,
  "processo_numero" varchar,
  "tipo_ato" varchar,
  "data_evento" date,
  "descricao" text,
  "prazo_gerado" date,
  "concluido" bool
);

-- ── documento_chunks (RAG / embeddings) ────────────────────────────────────────
CREATE TABLE "documento_chunks" (
  "id_chunk" integer PRIMARY KEY,
  "movimentacao_id" integer,
  "conteudo" text,
  "embedding" vector(768),
  "processo_numero" varchar,
  "documento_fonte" varchar,
  "tipo_documento" varchar
);

-- ── processo_advogados (N:N) ────────────────────────────────────────────────────
CREATE TABLE "processo_advogados" (
  "numero_processo" varchar,
  "advogado_id" integer,
  PRIMARY KEY ("numero_processo", "advogado_id")
);

ALTER TABLE "processos" ADD FOREIGN KEY ("cliente_id") REFERENCES "clientes" ("id_cliente") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "documento_chunks" ADD FOREIGN KEY ("movimentacao_id") REFERENCES "movimentacoes" ("id_movimentacao") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "processo_advogados" ADD FOREIGN KEY ("advogado_id") REFERENCES "advogados" ("id_advogado") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "honorarios" ADD FOREIGN KEY ("processo_numero") REFERENCES "processos" ("numero_processo") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "movimentacoes" ADD FOREIGN KEY ("processo_numero") REFERENCES "processos" ("numero_processo") DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE "processo_advogados" ADD FOREIGN KEY ("numero_processo") REFERENCES "processos" ("numero_processo") DEFERRABLE INITIALLY IMMEDIATE;

CREATE TABLE "documentos_ingestao" (
  "id_ingestao" serial PRIMARY KEY,
  "nome_arquivo" varchar NOT NULL,
  "nome_original" varchar,
  "data_ingestao" timestamp DEFAULT (now()),
  "atualizado_em" timestamp DEFAULT (now()),
  "status" varchar NOT NULL DEFAULT 'recebido',
  "mensagem_erro" text,
  "num_chunks" integer,
  "processo_numero" varchar,
  "tipo_documento" varchar,
  "arquivado_drive" boolean DEFAULT false
);
