#!/usr/bin/env bash
# scripts/release.sh
#
# Release command do Railway — roda antes do startup da API.
# Sequência: schema → seed → extração de PDFs → indexação vetorial.
#
# Idempotência:
#   • O init.sql usa CREATE TABLE sem IF NOT EXISTS — a flag "|| true" garante
#     que re-deploys não quebrem quando as tabelas já existem.
#   • O seed e a indexação são idempotentes por design (upsert / skip se já indexado).
#   • A extração de PDFs pode ser cara; comentar a linha abaixo em re-deploys
#     onde os PDFs não mudaram.

set -e  # aborta em qualquer erro não tratado explicitamente

echo "▶ [1/4] Aplicando schema do banco..."
psql "$DATABASE_URL" -f fase1_engenharia/docs/init.sql || echo "⚠ Schema já existe ou erro ignorado — continuando."

echo "▶ [2/4] Populando tabelas relacionais (seed)..."
python -m fase1_engenharia.db.seed

echo "▶ [3/4] Extraindo texto dos PDFs via LLM..."
(cd /app/fase1_engenharia && python pipeline_extracao.py) || echo "⚠ Extração de PDFs falhou — continuando com JSONs já existentes."

echo "▶ [4/4] Indexando chunks no pgvector..."
python -m fase1_engenharia.indexacao.indexar_documentos

echo "✅ Release concluído."