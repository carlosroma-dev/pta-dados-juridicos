# Checklist de validação pós-deploy

Execute na ordem. Cada item tem um critério claro de aprovação.
Não avance para o próximo se o atual falhar.

---

## 1. Banco e schema

```sql
-- Conectar no banco Railway e rodar:
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```
**Esperado:** 8 tabelas — `advogados`, `clientes`, `documento_chunks`,
`documentos_ingestao`, `honorarios`, `movimentacoes`, `processo_advogados`, `processos`.

```sql
SELECT extname FROM pg_extension WHERE extname = 'vector';
```
**Esperado:** retorna `vector`. Se vazio, a extensão não foi criada — o release.sh falhou.

---

## 2. Seed (dados relacionais)

```sql
SELECT COUNT(*) FROM clientes;
SELECT COUNT(*) FROM processos;
SELECT COUNT(*) FROM honorarios;
SELECT COUNT(*) FROM advogados;
```
**Esperado:** valores acima de zero em todas as tabelas.
Se alguma retornar 0, o seed não rodou — verificar logs do release command no Railway.

---

## 3. Indexação vetorial

```sql
SELECT COUNT(*) FROM documento_chunks;
SELECT COUNT(*) FROM documento_chunks WHERE embedding IS NULL;
```
**Esperado:** primeira query > 0. Segunda query = 0 (nenhum chunk sem embedding).
Se segunda > 0, a indexação foi parcial — rodar `indexar_documentos` manualmente.

---

## 4. Health check da API

```bash
curl https://seu-app-api.railway.app/health
```
**Esperado:**
```json
{
  "status": "ok",
  "banco": "ok",
  "pgvector": { "ok": true, "chunks_indexados": <N> },
  "agente": { "ok": true, "groq_key_presente": true }
}
```
Qualquer `"status": "erro"` ou `"ok": false` indica qual componente falhou.

---

## 5. Endpoints principais da API

Substituir `<API_KEY>` pela chave configurada no Railway.

```bash
# Clientes
curl -H "X-API-Key: <API_KEY>" \
  https://seu-app-api.railway.app/clientes/

# Processos
curl -H "X-API-Key: <API_KEY>" \
  https://seu-app-api.railway.app/processos/

# Prazos próximos
curl -H "X-API-Key: <API_KEY>" \
  "https://seu-app-api.railway.app/processos/prazos?dias=30"

# Honorários em atraso
curl -H "X-API-Key: <API_KEY>" \
  "https://seu-app-api.railway.app/honorarios/?status_pagamento=atrasado"

# Busca semântica
curl -X POST -H "X-API-Key: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"query": "contratos com prazo vencendo"}' \
  https://seu-app-api.railway.app/busca/
```
**Esperado:** HTTP 200 com lista de resultados em todos os endpoints.
HTTP 401 = `API_KEY` errada ou ausente. HTTP 500 = erro interno — ver logs.

---

## 6. Agente

```bash
curl -X POST -H "X-API-Key: <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"pergunta": "Quais processos vencem nos próximos 30 dias?"}' \
  https://seu-app-api.railway.app/agente/perguntar
```
**Esperado:** HTTP 200 com campo `resposta` preenchido e `status: "ok"`.
Se `groq_key_presente: false` no `/health`, esse endpoint vai falhar — verificar a variável `GROQ_API_KEY` no Railway.

---

## 7. Interface (Streamlit Cloud)

- [ ] App abre sem erro de build
- [ ] Painel de consultas carrega os gráficos (Vis-1 a Vis-4)
- [ ] Aba do agente responde a uma pergunta de teste
- [ ] Aba "Adicionar Documento" exibe o formulário sem erro 500
- [ ] Tema coral/creme está aplicado (se estiver com tema padrão do Streamlit, o `.streamlit/config.toml` não foi detectado)

---

## 8. Scheduler

No painel do Railway, serviço `scheduler`:

- [ ] Status do serviço: **Running** (não Crashed)
- [ ] Logs mostram a mensagem de inicialização do APScheduler sem exceção
- [ ] Nenhum erro de conexão com o banco nos logs

---

## Resultado esperado ao final

| Item | Status |
|------|--------|
| Banco com 8 tabelas e extensão vector | ✅ / ❌ |
| Seed populado (todas as tabelas > 0) | ✅ / ❌ |
| Chunks indexados sem embedding nulo | ✅ / ❌ |
| `/health` retorna `status: ok` | ✅ / ❌ |
| Endpoints principais retornam 200 | ✅ / ❌ |
| Agente responde sem erro | ✅ / ❌ |
| Interface abre com tema e dados | ✅ / ❌ |
| Scheduler rodando sem crash | ✅ / ❌ |