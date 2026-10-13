# DECISIONS.md — PTA Dados 2026.1 (Equipe Mezzalira)

Este documento registra **por que** cada escolha técnica foi feita ao longo das
três fases do projeto, com números reais e os trade-offs considerados. Serve
como memória de engenharia: ao mexer no código, consulte aqui o raciocínio
original antes de mudar uma decisão.

**Responsável:** Equipe Mezzalira

### Sumário

1. Pipeline de ingestão e limpeza de planilhas (seções 1–14)
2. Ingestão de PDFs e estruturação via LLM (seções 15–19)
3. Indexação de documentos no pgvector
4. API FastAPI
5. Nó gerador de respostas (LangGraph)
6. Nó classificador de perguntas (LangGraph)
7. Grafo completo do agente (LangGraph)
8. Automação de alertas de prazo (LangGraph)
9. Painel analítico (Fase 3)
10. Preparação do ambiente de produção (deploy)
11. Migração para OpenAI (gpt-5.4-mini)

---

## Decisões — Pipeline de Ingestão e Limpeza de Planilhas

**Responsável:** Equipe Mezzalira  

### Contexto

As 4 planilhas (Clientes, Processos, Honorarios, Movimentacoes)
chegaram com inconsistências propositais. Este documento registra
as decisões tomadas durante o pipeline de limpeza, com números reais.

### 1. Datas em formato misto

**Problema:** datas vinham em 2 formatos misturados:

- `2024-02-20 00:00:00` (ISO timestamp)
- `18 de julho de 2025` (extenso em pt-br)

**Decisão:** padronizar tudo pra `datetime` Python.

**Números:**

- Clientes.data_inicio: 1.133 ISO + 387 extenso
- Processos.data_abertura: 3.726 ISO + 1.274 extenso
- Processos.prazo_proximo: 3.400 ISO + 1.202 extenso (+ 398 nulos preservados)
- Honorarios.data_contrato: 3.030 ISO + 1.000 extenso
- Honorarios.data_vencimento: 2.986 ISO + 1.044 extenso
- Movimentacoes.data_movimentacao: 6.093 ISO + 1.957 extenso
- Movimentacoes.prazo_gerado: 1.804 ISO + 629 extenso (+ 5.617 nulos preservados)

### 2. Valores monetários

**Problema:** 3 formatos misturados (`34627.03`, `R$ 178.093`, `R$ 8.141,30`)

- valores corrompidos detectados (ex: `8812-04-01 00:00:00` em `valor_pago`).

**Decisão:** parsear todos pra `float`. Valores não-parseáveis viram `null`
e o registro vai pro log com motivo.

**Números:** formato float ex(10.05)

### 3. Duplicatas

**Decisão:** remover duplicatas baseadas em todas as colunas, registrar
quantidade no log.

**Números encontrados na análise inicial:**

- Clientes: 20 duplicatas
- Processos: 0 duplicatas
- Honorarios: 30 duplicatas
- Movimentacoes: 50 duplicatas

> **Atualização (ver seção 10):** esta seção trata apenas de duplicatas
> *exatas* (linha inteira idêntica). A análise posterior revelou que Processos,
> apesar de 0 duplicatas exatas, tinha `numero_processo` repetido em 4.600
> linhas — tratado como deduplicação por chave primária na seção 10.

### 4. Nulos — estratégias por campo

| Tabela        | Campo            | Nulos | %     | Estratégia                                 |
| ------------- | ---------------- | ----- | ----- | ------------------------------------------ |
| Clientes      | contato          | 116   | 7.6%  | manter null                                |
| Clientes      | email            | 176   | 11.6% | manter null                                |
| Processos     | prazo_proximo    | 398   | 8.0%  | manter null (faz sentido)                  |
| Processos     | valor_causa      | 1.298 | 26.0% | imputar mediana                            |
| Processos     | observacoes      | 2.207 | 44.1% | manter null                                |
| Honorarios    | valor_em_aberto  | 184   | 4.6%  | manter null                                |
| Honorarios    | honorario_exito  | 539   | 13.4% | manter null                                |
| Honorarios    | percentual_exito | 829   | 20.6% | manter null (semântica "não se aplica")    |
| Honorarios    | status_pagamento | 590   | 14.6% | manter null                                |
| Movimentacoes | descricao        | 1.020 | 12.7% | manter null                                |
| Movimentacoes | prazo_gerado     | 5.617 | 69.8% | manter null (nem todo ato gera prazo)      |
| Movimentacoes | concluido        | 1.158 | 14.4% | manter null                                |

### 5. Padronização de strings — enums técnicos

**Decisão:** lowercase + underscore.

**Mapeamentos aplicados:**

- `status` (Processos): `ativo / Ativo / ATIVO / active` → `ativo` etc.
- `tipo` (Processos): `Trabalhista / TRABALHISTA / trabalhista` → `trabalhista` etc.
- `forma_pagamento` (Honorarios): `PIX / pix` → `pix`, `Boleto / boleto` → `boleto` etc.
- `status_pagamento` (Honorarios): `ATRASADO / atrasado` → `atrasado` etc.
- `tipo_ato` (Movimentacoes): normalizado pra lowercase.

### 6. Padronização de strings — nomes próprios

**Decisão:** Title Case, mantendo formato natural.

**Cidades (Clientes):**

- `recife / Recife / RECIFE` → `Recife` (719 registros consolidados)

**Advogados (Processos e Movimentacoes):**

- `Dr. Barros / dr. barros / DR. BARROS` → `Dr. Barros`
- `Dra. Cavalcante / DRA. CAVALCANTE` → `Dra. Cavalcante`
- `Dr. Melo / dr. melo` → `Dr. Melo`
- `Dra. Fontes / Dra Fontes` → `Dra. Fontes`

### 7. Booleanos

**Decisão:** valores tipo sim/não/S/N/1/0 convertidos pra `True`/`False`.

**Mapeamento:**

- `Sim / sim / S / 1` → `True`
- `Não / não / nao / N / 0` → `False`
- `null` → mantém `null`

**Campos afetados:**

- Honorarios.honorario_exito (6 variações → True/False/null)
- Movimentacoes.concluido (7 variações → True/False/null)

### 8. Integridade referencial

**Decisão:** verificar todas as FK e logar órfãos. Não há tratamento ativo
porque a análise inicial mostrou zero órfãos.

**Resultado (a confirmar quando rodar o script):**

- Processos → Clientes: 0 órfãos
- Honorarios → Clientes: 0 órfãos
- Honorarios → Processos: 0 órfãos
- Movimentacoes → Processos: 0 órfãos

> **Atualização (ver seções 11-13):** a base original não tinha órfãos, mas as
> regras de coerência temporal introduzidas depois *removem* processos e, por
> cascata, geram remoções nas tabelas filhas. A integridade referencial passou
> a ter tratamento ativo — descrito nas seções 12 e 13.

### 9. Decisões abertas (a discutir com a equipe/cliente)

- ❓ `valor_causa` nulo em 26% dos processos: é válido uma ação sem
  valor de causa? Imputação com mediana é apropriada?
- ✅ ~~Advogados como string vs tabela separada~~ — **RESOLVIDO:** modelado
  como tabela própria (`Advogado`) com FK, conforme `db/models.py` e `seed.py`.
  Ver seção 18.

### 10. Deduplicação de Processos por numero_processo

**Problema:** Processos chegou com 5.000 linhas, mas apenas 400
`numero_processo` distintos (cada um repetido em média 12x, até 41x). Pelo
`docs/schema.sql`, `numero_processo` é PRIMARY KEY da tabela ("PK =
numero_processo, conforme decisão da equipe"), logo cada número deve ocorrer
uma única vez.

**Decisão:** em `limpar_processos.py`, após normalizar `data_abertura`, agrupar
por `numero_processo` e manter a linha de `data_abertura` mais recente,
descartando as demais.

**Detalhes:**

- Roda DEPOIS da padronização de datas — a escolha do "mais recente" depende
  das datas já convertidas para `datetime`.
- Linhas sem `data_abertura` (NaT) são tratadas como as mais antigas
  (`na_position="last"` no sort decrescente), perdendo para qualquer data válida.
- Contagem de removidas vai para o log e para o dict de estatísticas
  (`dedup_numero_processo_removidas`).

**Números:** 5.000 → 400 (4.600 removidas).

**Ponto de atenção:** o efeito remove 92% das linhas. A regra só faz sentido
sob a premissa (confirmada pelo schema) de que `numero_processo` é o
identificador único. Se a regra de negócio mudar e cada linha passar a
representar um processo distinto (chave = `processo_id`), esta etapa precisa
ser revista.

### 11. Coerência temporal — tabelas filhas vs. data_abertura

**Princípio:** um evento vinculado a um processo não pode ocorrer antes de o
processo existir. A coluna de data comparada varia por tabela — escolha
deliberada, não mecânica.

**Movimentacoes** — `data_movimentacao >= data_abertura`. Um andamento é
interno ao processo; anterioridade é logicamente impossível. Mesmo-dia é
mantido; sem data é removido.

**Honorarios** — `data_vencimento >= data_abertura` (e **não** `data_contrato`).
Um contrato de honorários pode legitimamente ser assinado antes da abertura do
processo (o cliente contrata, o advogado então protocola), logo `data_contrato`
anterior à abertura é fluxo normal e foi descartado como critério — usá-lo
removeria ~3.659 registros financeiros válidos (91%). Já uma parcela vencer
antes de o processo existir é incoerente.

**Implementação:** função genérica `remover_anteriores_abertura` em
`integridade_referencial.py`, parametrizada pela coluna de data, com wrappers
por tabela. Chamada como pós-limpeza no `pipeline.py`, que foi reestruturado
para separar limpeza de gravação (antes salvava o CSV dentro do loop, o que
gravaria os dados antes dos filtros).

### 12. Coerência temporal de Processos + cascata referencial

**Decisão (Processos):** remover processos incoerentes por DOIS critérios (união):

- Critério 1 — `prazo_proximo < data_abertura` (incoerência lógica): 156.
- Critério 2 — `data_abertura < data_inicio do cliente` (processo aberto antes
  de o cliente existir): 31. Sobreposição entre os dois critérios: 6.
- Total: 181 processos removidos (400 → 219).

**Cascata:** como `numero_processo` é FK das tabelas filhas, remover um processo
torna seus honorários e movimentações órfãos, que são removidos em seguida
(`remover_orfaos_por_processo`).

**Ordem no pipeline:** (1) drop de processos incoerentes → (2) cascata nas
filhas → (3) coerência temporal das datas das filhas (seção 11). Essa ordem
garante que a coerência de datas roda já sobre o conjunto final de processos
válidos.

**Premissa registrada:** o critério 2 assume que cadastro tardio de cliente
NÃO é válido neste contexto — decisão de negócio confirmada. Se a premissa
mudar, remover o critério 2 reduz o impacto em ~25 processos.

### 13. Clientes sem processo (decisão de ESCOPO, não de integridade)

**Decisão:** remover clientes não vinculados a nenhum processo após toda a
limpeza. Removidos: 1.302 (1.500 → 198).

**Natureza:** cliente sem processo é um estado VÁLIDO no schema (a FK é
`processos.cliente_id → clientes`, não o inverso — não há obrigação de todo
cliente ter processo). Estes 1.302 registros têm dados íntegros; ficaram
desconectados como efeito acumulado dos drops anteriores (seções 10 e 12).
Foram removidos por decisão de negócio, para manter apenas o núcleo conectado
de dados — não por incoerência.

**Reversibilidade:** basta remover o passo (4) do `pipeline.py` para preservar
todos os clientes cadastrados.

### 14. Funil acumulado final (original → limpo)

| Tabela        | Original | Final | % mantido |
| ------------- | -------- | ----- | --------- |
| clientes      | 1.520    | 198   | 13%       |
| processos     | 5.000    | 219   | 4%        |
| honorarios    | 4.030    | 1.113 | 28%       |
| movimentacoes | 8.050    | 392   | 5%        |

Base final totalmente conectada: sem órfãos, sem FK quebrada, sem violações
temporais (verificado). A redução expressiva é o efeito **composto** das regras
acima: a dedup de Processos (seção 10) puxa as aberturas para datas recentes, o
que amplifica o volume removido pelas regras de coerência temporal (seções
11-12). Cada etapa é individualmente justificada; o efeito acumulado deve ser
apresentado em conjunto na defesa do PTA.

---

### 15. Extração de texto de PDFs

**Decisão:** extração de texto via biblioteca **`pdfplumber`**
(`utils/pdf_handler.py` e `ingestao/extrair_pdfs.py`).

**Detalhes do código:**
- Percorre página a página; páginas sem texto extraível são logadas como
  warning e tratadas como string vazia (evita erro em PDF escaneado/em branco).
- `extrair_pdfs.processar_pdfs` é **idempotente**: se o `.txt` de saída já
  existe em `data/raw/`, o PDF é pulado ("já extraído"). Reprocessar a pasta
  não refaz trabalho.

**Justificativa da escolha do pdfplumber:** boa extração de layout/tabelas em PDFs jurídicos vs. PyPDF2/pdfminer.

### 16. Estruturação via LLM (OpenAI + Pydantic)

**Decisão:** transformar o texto cru em JSON estruturado usando um LLM com
saída validada por schema (`pipeline_extracao.py`).

**Configuração (do código):**
- Provedor/modelo: **OpenAI**, `gpt-5.4-mini-2026-03-17`.
- `temperature=0` — para respostas determinísticas e reduzir alucinação
  ("para ele ser preciso e não inventar", conforme comentário no código).
- Saída estruturada via `llm.with_structured_output(DocumentoEstruturado)`,
  que força o modelo a preencher o schema Pydantic.
- Erros de extração são gravados em `logs/extracao_erros.log`.

**Justificativa OpenAI + gpt-5.4-mini-2026-03-17:** ver seção *Migração para OpenAI* ao final deste documento.

### 17. Schema de extração (`DocumentoEstruturado`)

**Decisão:** cada documento é reduzido a um conjunto fixo de campos
(`schemas/documents_schemas.py`):

| Campo           | Tipo      | Obrigatório | Observação                       |
| --------------- | --------- | ----------- | -------------------------------- |
| numero_processo | str       | Opcional    | padrão CNJ; pode ser nulo        |
| tipo_documento  | str       | Sim         | ex: Petição, Contrato, Intimação |
| data_documento  | str       | Opcional    | formato YYYY-MM-DD               |
| partes          | List[str] | Sim         | nomes das partes envolvidas      |
| valor           | float     | Opcional    | valor da causa ou honorários     |
| resumo          | str       | Sim         | resumo executivo de até 2 linhas |

**Nota de coerência com a limpeza:** `numero_processo` ser opcional aqui é
consistente com os documentos sem número CNJ identificados na fase de planilhas
(ex: contratos de honorários sem processo associado).

### 18. Ingestão incremental via Google Drive

**Decisão:** o `drive_watcher.py` baixa PDFs de uma pasta do Drive e só
processa o que é novo ou foi modificado.

**Mecanismo (do código):**
- Estado persistido em `drive_state.json` como `id → modifiedTime`.
- Na primeira execução (sem state), todos os PDFs são tratados como novos.
- Autenticação por **Service Account** com escopo **somente-leitura**
  (`drive.readonly`) — o robô lê e baixa, nunca modifica o Drive
  (`drive_client.py`).
- Listagem lida com paginação (~100 itens por página).

**Justificativa do escopo readonly:** decisão de segurança explícita no código
(princípio do menor privilégio).

### 19. Carga no banco relacional (`seed.py`)

**Decisão:** popular o banco a partir dos CSVs limpos, respeitando o schema
relacional (`db/seed.py`, `db/models.py`, `docs/schema.sql`).

**Ordem de inserção (por causa das FKs):**
`advogados → clientes → processos → honorarios → movimentacoes`.

**Mapeamento coluna CSV → coluna do banco** (ponto de atenção: os nomes
divergem entre o CSV limpo e o banco — mexer num lado sem o outro quebra a
carga):

| Tabela        | CSV               | Banco             |
| ------------- | ----------------- | ----------------- |
| clientes      | cpf               | CPF               |
| clientes      | data_inicio       | data_cadastro     |
| processos     | numero_processo   | (PK, varchar CNJ) |
| honorarios    | n_parcelas        | numero_parcelas   |
| honorarios    | numero_processo   | processo_numero   |
| movimentacoes | data_movimentacao | data_evento       |
| movimentacoes | numero_processo   | processo_numero   |

**Advogados como entidade:** `advogado_responsavel` (string nas planilhas) é
promovido a tabela própria `Advogado` com FK — resolve a decisão antes aberta
na seção 9.

---

## Decisões — Indexação de Documentos no pgvector


### Contexto
Os JSONs estruturados dos documentos jurídicos precisam ser indexados
no pgvector para permitir busca por similaridade semântica pelo chatbot.

### 1. Estratégia de Chunking
**Tamanho do chunk:** ~500 tokens (2000 caracteres)  
**Sobreposição:** ~50 tokens (200 caracteres)

**Justificativa:**
- Chunks de 500 tokens têm contexto suficiente para retornar respostas
  relevantes sem serem genéricos demais
- Chunks menores perdem contexto e não fazem sentido sozinhos
- Chunks maiores retornam informação demais, prejudicando a precisão da busca
- A sobreposição de 50 tokens evita perda de contexto nas bordas dos chunks

### 2. Modelo de Embeddings

**Modelo:** `nomic-ai/nomic-embed-text-v1` (HuggingFace, local)  
**Dimensões:** 768  
**Justificativa:** A task especificava o Gemini `embedding-001`, porém
estávamos com dificuldade em usar as chaves de API desse modelo desde a etapa de extração.
O `nomic-embed-text-v1` foi escolhido por ser gratuito, rodar localmente
sem necessidade de API key, e ter boa qualidade para textos jurídicos.
O schema foi ajustado de `vector(1536)` para `vector(768)` para compatibilidade.

### 3. Idempotência

**Decisão:** antes de inserir um chunk, verificar se o conteúdo já existe
na tabela. Se existir, o chunk é ignorado. Isso garante que reindexar
um documento não gera duplicatas.

---

## Decisões — API FastAPI


### Contexto

Com os dados limpos no banco e os chunks indexados no pgvector, a etapa seguinte
foi expor essas informações via uma API REST. A API serve como camada de acesso
tanto para consultas relacionais simples quanto para a busca semântica dos
documentos jurídicos.

### 1. Autenticação via API Key global

**Decisão:** autenticação por header `X-API-Key`, aplicada globalmente via
`dependencies` no construtor do `FastAPI`. Se a variável `API_KEY` não estiver
configurada no `.env`, a API sobe sem autenticação — comportamento intencional
para facilitar o desenvolvimento local sem precisar configurar variáveis de
ambiente toda vez.

### 2. Enums como parâmetros de query

**Decisão:** os filtros de `status` (Processos) e `status_pagamento`
(Honorarios) usam enums Python do tipo `str, Enum` em vez de strings livres.
Isso faz o FastAPI validar automaticamente os valores aceitos e exibir as
opções no Swagger, sem nenhuma lógica adicional de validação nas rotas.

Os enums definidos em `api/models/enums.py` são:

| Enum | Valores |
| ---- | ------- |
| StatusProcesso | ativo, suspenso, encerrado, em_recurso, acordo |
| StatusPagamento | quitado, em_dia, atrasado |

**Nota de coerência:** os valores aqui espelham exatamente a padronização
aplicada na seção 5 (lowercase + underscore). Qualquer valor fora do enum
retorna 422 automaticamente.

### 3. Ordem das rotas em /processos

**Decisão:** a rota `GET /processos/prazos` foi declarada **antes** de
`GET /processos/` no arquivo. É uma convenção defensiva: se futuramente for
adicionada uma rota `GET /processos/{id}`, o FastAPI resolveria rotas por ordem
de declaração e `"prazos"` seria capturado como valor do parâmetro `{id}` em
vez de bater na rota correta.

### 4. Lazy loading do modelo de embedding na busca

**Decisão:** o `SentenceTransformer` (nomic-embed-text-v1) não é carregado no
startup do servidor. Ele é inicializado na primeira chamada ao endpoint
`POST /busca/` e reutilizado nas seguintes via variável global `_modelo`.

**Justificativa:** carregar o modelo no startup travava o uvicorn por vários
segundos, o que é problemático em ambiente de desenvolvimento. O lazy loading
distribui esse custo para a primeira requisição de busca, que fica mais lenta,
mas deixa o servidor disponível imediatamente.

### 5. Busca semântica via pgvector

**Decisão:** o endpoint `POST /busca/` converte a pergunta em vetor usando o
mesmo modelo de embedding da indexação (`nomic-embed-text-v1`, 768 dimensões)
e consulta o pgvector com o operador de distância cosseno `<=>`. O parâmetro
`top_k` controla quantos chunks retornar (entre 1 e 20, padrão 5).

A pergunta é encodada com `normalize_embeddings=True`, o que padroniza a
magnitude dos vetores e torna a distância cosseno numericamente equivalente
à similaridade cosseno — valores mais próximos de 0 indicam maior relevância.

**Consistência com a indexação:** usar o mesmo modelo tanto na ingestão quanto
na busca é obrigatório. Modelos diferentes geram espaços vetoriais
incompatíveis e os resultados seriam sem sentido. Isso foi tratado como
premissa não negociável na implementação.

### 6. Formato de resposta padronizado

**Decisão:** todos os endpoints retornam o mesmo envelope JSON:

```json
{"dados": [...], "total": N, "status": "ok"}
```

Erros retornam 500 com `{"detail": "mensagem"}` via `HTTPException`. Não há
paginação implementada — os endpoints de listagem retornam todos os registros
de uma vez. Para o volume atual de dados (198 clientes, 219 processos, 1.113
honorários), isso é aceitável; se a base crescer, paginação seria o próximo
passo natural.

---

## Decisões — Nó gerador de respostas (LangGraph)


### Contexto

Primeiro nó do grafo LangGraph da Fase 2. Recebe os chunks recuperados pelo
retriever e gera uma resposta em linguagem natural fundamentada exclusivamente
no contexto fornecido.

### 1. System prompt minimalista

**Decisão:** prompt curto com instrução explícita de não inventar e fallback
definido ("Não encontrei essa informação nos documentos.").

**Justificativa:** prompts longos aumentam custo sem garantir mais fidelidade.
A instrução "SOMENTE com base no contexto" é suficiente para o caso de uso
jurídico — onde inventar é inaceitável.

### 2. temperature=0

**Decisão:** `temperature=0` — mesmo valor já adotado na extração (Fase 1).

**Justificativa:** respostas jurídicas exigem determinismo, conforme requisitado pelo cliente. Saída reproduzível
para a mesma entrada facilita depuração e validação.

### 3. Lazy loading do LLM

**Decisão:** `ChatOpenAI` instanciado na primeira chamada via `_get_llm()`, não
no import do módulo.

**Justificativa:** mesmo padrão do `retriever.py` (`_get_modelo`). Não trava o
startup e permite importar o módulo sem a `OPENAI_API_KEY` disponível.

---

## Decisões — Nó classificador de perguntas (LangGraph)


### Contexto

O agente tem três caminhos de busca: pgvector (documentos), SQL (dados
estruturados) e híbrido (as duas fontes combinadas). Antes de buscar, precisa
identificar para onde rotear.

### 1. Nó separado vs. lógica interna

**Decisão:** nó separado (`classificar_pergunta`).

**Justificativa:** LangGraph expressa roteamento via conditional edges — o
padrão idiomático da biblioteca. O resultado fica no estado (`tipo_consulta`),
visível para debug e logs. Alinha com o diagrama em `docs/arquitetura.md`.

### 2. Classificação via LLM com few-shot

**Decisão:** LLM (OpenAI) com `with_structured_output(Classificacao)` e até 30
exemplos por categoria no prompt. O schema `Classificacao` devolve dois campos:
`tipo` (a categoria) e `confianca` (`alta` ou `baixa`).

**Justificativa:** few-shot é mais robusto que keywords para linguagem jurídica
variada. Mesmo padrão do `pipeline_extracao.py` (`with_structured_output`).

**Quatro categorias:**
- `"vetorial"` — conteúdo de documentos (contratos, petições, acordos)
- `"relacional"` — dados estruturados (prazos, clientes, honorários, status)
- `"hibrido"` — precisa das duas fontes ao mesmo tempo (ex.: vínculos de
  representação, "quem é o advogado de X e o que diz o contrato dela?")
- `"reformular"` — pergunta ambígua; agente retorna pedindo reformulação

### 3. Confiança como rede de segurança — fallback para híbrido

**Decisão:** quando o LLM classifica com `confianca="baixa"` (e o tipo não é
`reformular`), o roteador força a busca **híbrida** em vez de arriscar uma
fonte só. Se nem com contexto o LLM consegue classificar, cai em `"reformular"`.

**Justificativa:** uma classificação errada roda a busca na fonte errada e gera
resposta incorreta. Em caso de dúvida, buscar nas duas fontes cobre o caso sem
custo de qualidade — é melhor trazer dados a mais do que devolver vazio. Pedir
reformulação fica reservado para perguntas genuinamente sem contexto.

### 4. Unificação do roteador — rotear chama classificar_pergunta

**Contexto:** o nó `rotear` em `grafo/grafo.py` foi refatorado para delegar
a classificação ao `classificar_pergunta` de `grafo/nos/classificar_pergunta.py`,
eliminando a duplicação de lógica que existia anteriormente.

**Decisão:** o `rotear` importa e chama `classificar_pergunta` diretamente,
mapeando `"reformular"` → `"ambigua"` para manter compatibilidade com os
conditional edges do grafo.

**Justificativa:** havia dois classificadores com comportamentos distintos —
o `rotear` original usava prompt simples sem few-shot, o que causava erros de
roteamento (ex: "Quem é o advogado da Fernanda Costa?" indo para relacional
em vez de vetorial). Unificar garante que a API e os testes isolados usem
exatamente o mesmo classificador refinado.

---

## Decisões — Grafo completo do agente (LangGraph)


### Contexto

O grafo principal (`grafo/grafo.py`) conecta todos os nós do agente e define
o fluxo de execução, incluindo os mecanismos de retry e o nó de falha.

### 1. Estado do grafo (`Estado` TypedDict)

**Decisão:** o grafo principal usa um `Estado` TypedDict local,
separado do `AgentState` definido em `grafo/estado.py`.

| Campo | Tipo | Descrição |
| --- | --- | --- |
| pergunta_original | str | Pergunta exatamente como o usuário digitou |
| pergunta_reformulada | str | Versão reformulada pelo nó `formular` |
| rota | Literal["relacional", "vetorial", "hibrido", "ambigua"] | Decisão do nó `rotear` |
| ferramenta_relacional | str | Sub-rota relacional escolhida (verificar_prazos, checar_honorarios, etc.) |
| contexto | str | Resultado da busca (SQL e/ou pgvector) como texto |
| contexto_relacional | str | Parte relacional do contexto (usado internamente pelo híbrido) |
| contexto_vetorial | str | Parte vetorial do contexto (usado internamente pelo híbrido) |
| resposta | str | Resposta gerada pelo LLM |
| validado | bool | Resultado da validação pelo nó `validar` |
| tentativas_ambigua | int | Contador de vezes que o roteador retornou "ambigua" |
| tentativas_validacao | int | Contador de tentativas de validação |
| historico | list[dict] | Histórico da conversa, para resolver referências entre turnos |

**Nota sobre `AgentState`:** o `estado.py` define um `AgentState` mais
enxuto (4 campos) usado pelos nós isolados (`classificar_pergunta`,
`gerar_resposta`). Os dois coexistem porque os nós individuais foram
desenvolvidos para serem testáveis de forma independente, com um estado mínimo.
O `Estado` do `grafo.py` é mais rico por precisar carregar informação de
controle de fluxo (tentativas, validação) que os nós isolados não precisam.

### 2. Fluxo linear com ramificações para nós terminais

**Decisão:** o grafo não tem loops de retorno. Cada caminho termina num nó
terminal dedicado, em vez de voltar a `formular`:

- Quando a rota é `ambigua`, o fluxo vai direto para `pedir_esclarecimento`
  (que gera uma pergunta de esclarecimento) e encerra.
- Quando a validação falha, o fluxo vai para `falha` e encerra.
- Os contadores `tentativas_ambigua` e `tentativas_validacao` ficam no estado
  para observabilidade/log, registrando quantas vezes cada situação ocorreu.

**Justificativa:** loops de re-roteamento aumentavam o custo (mais chamadas ao
LLM) sem ganho prático — quando a pergunta é ambígua, pedir esclarecimento ao
usuário resolve melhor do que tentar reformular sozinho repetidamente. Terminar
em nós explícitos torna o fluxo previsível e fácil de depurar.

### 3. Nó de esclarecimento e nó de falha

**Decisão:** dois nós terminais distintos para os dois tipos de "não respondeu":

- **`pedir_esclarecimento`** — quando a pergunta é ambígua. Gera, via LLM, uma
  pergunta de volta ao usuário explicando o que faltou e dando exemplos de como
  reformular. Tem fallback fixo caso o LLM falhe.
- **`falha`** — quando a resposta gerada não passou na validação. Retorna uma
  mensagem construtiva sugerindo incluir CNJ, CPF ou o tipo de documento.

**Justificativa:** tornar os estados de "não respondeu" explícitos no grafo (em
vez de retornar string vazia ou levantar exceção) facilita debug, logging e
tratamento futuro — como escalar para um operador humano. Separar os dois casos
permite mensagens adequadas a cada situação.

### 4. Nó de validação por LLM

**Decisão:** após `gerar_resposta`, um segundo LLM valida se a resposta
é relevante e contém informações concretas. Respostas que dizem "não
encontrei informações" ou "não tenho contexto suficiente" são marcadas
como `nao_passou`.

**Justificativa:** o gerador pode produzir respostas educadas porém vazias
de conteúdo. A validação por LLM detecta esse caso e dá ao agente uma
segunda tentativa de busca antes de entregar uma resposta de baixa qualidade.

**Custo:** cada pergunta passa por `formular` + `rotear` (classificação) +
`gerar_resposta` + `validar`, além das chamadas internas da busca (o sub-roteador
relacional e a geração de SQL, ou a busca vetorial). Como não há loop de retry,
o número de chamadas por pergunta é limitado e previsível — aceitável para o
volume atual.

---

## Decisões — Automação de alertas de prazo (LangGraph)

### Contexto

Grafo de automação que roda de forma agendada, busca processos com prazo próximo e envia emails proativos para os advogados responsáveis sem o cliente precisar perguntar.

### 1. Grafo linear sem LLM

**Decisão:** grafo linear fixo `buscar_prazos → agrupar_por_advogado → enviar_emails → registrar_log`, sem LLM nem roteamento condicional.

**Justificativa:** o fluxo é determinístico — não há ambiguidade nem necessidade de interpretação semântica. Usar LLM aqui aumentaria custo e latência sem benefício.

### 2. Agrupamento por advogado

**Decisão:** um email consolidado por advogado com todos os seus processos, em vez de um email por processo.

**Justificativa:** múltiplos emails por processo sobrecarregaria a caixa do advogado. Um email consolidado é mais prático e profissional.

### 3. Envio de email via Resend

**Decisão:** usar a API do Resend em vez de SMTP direto (Gmail).

**Justificativa:** as contas institucionais da UFPE bloqueiam criação de senhas de app do Gmail necessárias para SMTP. O Resend oferece plano gratuito com API simples sem configuração de servidor SMTP.

**Limitação:** no plano gratuito, emails só podem ser enviados para o endereço verificado da conta. Em produção, configurar um domínio verificado resolve essa limitação.

### 4. EMAIL_FALLBACK para advogados sem email configurado

**Decisão:** quando o advogado responsável não tem email mapeado, o sistema usa `EMAIL_FALLBACK` em vez de ignorar o alerta.

**Justificativa:** a tabela `processo_advogados` estava inicialmente vazia (bug no seed corrigido posteriormente). O fallback garante que nenhum alerta seja perdido mesmo com configuração incompleta de emails.

### 5. JOIN com processo_advogados para obter o responsável

**Decisão:** a query de busca de prazos faz LEFT JOIN com `processo_advogados` e `advogados` para obter o nome do responsável, em vez de usar uma coluna direta em `processos`.

**Justificativa:** o schema modela a relação processo-advogado como N:N via tabela de junção. Não há coluna `advogado_responsavel` direta em `processos` — o responsável precisa ser buscado via JOIN.

## Decisões — Painel Analítico (Fase 3)

### Contexto

As 4 dores mapeadas são:

| # | Dor | Descrição |
| - | --- | --------- |
| 1 | Prazos | O escritório perde prazos processuais por falta de visibilidade consolidada |
| 2 | Honorários | Inadimplência e honorários em aberto não são monitorados de forma proativa |
| 3 | Documentos | Não há clareza sobre o volume e cobertura dos documentos já indexados |
| 4 | Rastreabilidade | Difícil saber quem é responsável por cada processo e qual é o status atual |

### Vis-1 — Prazos nos próximos 30 dias

**Dor:** Dor 1 — visibilidade de prazos
**Pergunta:** *"Quais processos vencem em breve e qual é o mais urgente?"*
**Endpoint:** `GET /processos/prazos?dias=30`
**Gráfico:** `px.bar` horizontal, ordenado por urgência, colorido por faixa (≤7d vermelho, 8–15d laranja, 16–30d amarelo)
**Por que barras horizontais:** labels de processo são texto longo — barra vertical ficaria ilegível. A cor adiciona a dimensão de urgência sem segundo eixo.
**Pronto quando:** renderiza dados reais, ordenado, cores implementadas.

### Vis-2 — Inadimplência por cliente

**Dor:** Dor 2 — honorários em aberto não monitorados
**Pergunta:** *"Quem deve ao escritório e quanto?"*
**Endpoint:** `GET /honorarios/?status_pagamento=atrasado`
**Gráfico:** `px.bar` vertical, `valor_em_aberto` agregado por cliente, ordenado decrescente
**Por que barras verticais ordenadas:** a convenção de valor monetário no eixo Y é estabelecida. Ordenar decrescente elimina a necessidade de varrer todos os valores para encontrar o maior — o mais crítico aparece primeiro.
**Por que não pizza:** pizza só funciona para composição de um todo. Aqui cada cliente é independente — a pergunta é ranking, não proporção.
**Pronto quando:** exibe apenas `status_pagamento = atrasado`, agrega por cliente, tooltip mostra `valor_em_aberto` + quantidade de parcelas em atraso.

### Vis-3 — Documentos indexados por tipo

**Dor:** Dor 3 — sem clareza sobre cobertura da base de documentos
**Pergunta:** *"Quais tipos de documento estão na base e em que quantidade?"*
**Endpoint:** `GET /documentos/`
**Gráfico:** `px.bar` agrupado por `tipo_documento`
**Por que barras agrupadas e não heatmap:** com 11 PDFs indexados atualmente, um heatmap teria muitas células vazias e ficaria esparso. Barras agrupadas são mais legíveis nesse volume.
**Dependência:** endpoint `GET /documentos/`.
**Pronto quando:** lista os tipos reais da base com contagem de chunks por tipo.

### Vis-4 — Distribuição de processos por advogado e status

**Dor:** Dor 4 — difícil rastrear responsáveis e status da carteira
**Pergunta:** *"Quem cuida de quê e como está a carteira de cada advogado?"*
**Endpoints:** `GET /processos/` + `GET /advogados/` 
**Gráfico:** `px.bar` empilhado (`barmode="stack"`), eixo X por advogado, segmentos por status
**Por que empilhado e não agrupado:** empilhado mostra volume total e composição ao mesmo tempo. Agrupado dificultaria comparar o total entre advogados. 100% empilhado foi descartado porque perderia a informação de volume absoluto.
**Dependências:** endpoint `GET /advogados/`.
**Pronto quando:** exibe todos os advogados com pelo menos 1 processo, status corretamente empilhados, cores mapeadas para os valores do enum `StatusProcesso`.

## Decisões — Preparação do Ambiente de Produção (Deploy)

### Contexto

Com as três fases funcionando localmente via `docker-compose`, a etapa de deploy
deixa de ser um "passo final" e vira uma tarefa com preparação própria. Subir em
produção sem essa preparação leva a variáveis de ambiente faltando, banco sem
schema e demo quebrando ao vivo. Esta seção registra a plataforma escolhida para
cada componente, a justificativa, e as consequências dessa escolha para a
configuração de produção.

### 1. Plataforma por componente

**Decisão:** dividir o sistema entre duas plataformas:

| Componente | Origem (docker-compose) | Plataforma de produção |
| ---------- | ----------------------- | ---------------------- |
| Banco (Postgres + pgvector) | serviço `db` | Railway — serviço a partir da imagem `pgvector/pgvector:pg15` |
| API FastAPI | serviço `api` | Railway — serviço web (uvicorn) |
| Scheduler de prazos | serviço `scheduler` | Railway — serviço worker (sem porta) |
| Carga inicial (seed + extração + indexação) | serviço `init` | Railway — *release command*, não serviço permanente |
| Interface Streamlit | serviço `interface` | Streamlit Community Cloud |

**Justificativa (backend no Railway):** o backend tem dois processos de longa
duração que dependem do mesmo banco — a `api` (uvicorn) e o `scheduler`
(APScheduler rodando `verificar_prazos`). Railway é container-based (sem
serverless / sem cold start) e roda múltiplos serviços do mesmo repositório
compartilhando variáveis de ambiente, o que casa diretamente com a topologia que
já existe no `docker-compose`. Plataformas com free tier que derrubam o serviço
por inatividade penalizariam o scheduler e a demo ao vivo.

**Justificativa (frontend no Streamlit Community Cloud):** a interface é uma app
Streamlit pura que só consome a API por HTTP — não precisa de banco nem de libs
pesadas de ML. O Streamlit Community Cloud hospeda esse tipo de app de graça e é
feito exatamente pra isso, evitando consumir crédito/recurso do Railway com o
frontend.

### 2. Consequências da escolha (o que muda em relação ao local)

**a) `pgvector` no banco gerenciado.** O Postgres de produção precisa ter a
extensão `vector` disponível. Para garantir paridade com o ambiente local,
o banco no Railway é criado a partir da imagem `pgvector/pgvector:pg15` (a mesma
do compose), e o schema é aplicado rodando o conteúdo de
`fase1_engenharia/docs/init.sql` na primeira carga — em produção o
`docker-entrypoint-initdb.d` **não** roda automaticamente, então o schema entra
via release command.

**b) O `init` vira release command, não serviço.** Localmente o `init` é um
serviço one-shot orquestrado por `depends_on`. Em produção, a sequência
`seed → pipeline_extracao → indexar_documentos` roda como comando de release
(pré-deploy) da API, garantindo que o banco esteja populado e indexado antes da
API receber tráfego. Não pode virar serviço permanente (ele termina e o Railway
o trataria como crash).

**c) Custo (Railway não tem free tier permanente).** Railway oferece um crédito
único de US$5 que expira em 30 dias; depois disso é necessário o plano Hobby
(US$5/mês). A cobrança é por recurso consumido (vCPU/RAM por segundo), então
containers ociosos — como o `scheduler` 24/7 — também geram custo. Para a janela
da demo isso é coberto pelo crédito de trial; para uso contínuo, contar com o
Hobby. *(Termos verificados em jun/2026 — reconfirmar na página de pricing antes
de subir.)*

**d) Limites do Streamlit Community Cloud.** A app precisa estar num repositório
GitHub (público, ou privado com o escopo OAuth de deploy), entra em "sleep" após
período sem acesso (primeira visita reinicializa) e tem ~1 GB de RAM garantida.
Por isso o frontend **não** instala o `requirements.txt` completo: ele usa um
arquivo de dependências enxuto (sem `torch`/`sentence-transformers`), já que só
fala com a API por HTTP. *(Detalhado no Passo 2.)*

**e) `service_account.json` (Google Drive) não vai pro repositório.** Em
produção o watcher do Drive fica desligado por padrão (`DRIVE_UPLOAD_ENABLED=false`)
para a demo. Se for necessário ligá-lo, o JSON da service account é injetado via
variável de ambiente (conteúdo do arquivo), nunca commitado.

### 3. Decisão registrada

Plataforma definida: **Railway (backend: banco pgvector + API + scheduler) +
Streamlit Community Cloud (frontend)**. Os próximos passos da tarefa de deploy
(requirements fixados, validação do compose como base, inventário de variáveis de
ambiente e checklist de validação pós-deploy) assumem essa topologia.

---

## Migração para OpenAI (gpt-5.4-mini-2026-03-17)

### Contexto

Durante os testes finais do projeto, a pilha de LLM foi migrada integralmente do Groq (`llama-3.3-70b-versatile`) para a OpenAI (`gpt-5.4-mini-2026-03-17`), para garantir estabilidade e qualidade na apresentação e entrega. A troca trouxe dificuldades de adaptação: o modelo do Groq interpretava os prompts de forma diferente do GPT-mini, o que obrigou o grupo a reformular vários exemplos de classificação e a tornar as regras dos prompts mais explícitas, entre outros ajustes.

### 1. Motivação da migração

Durante os testes, o `llama-3.3-70b-versatile` apresentou comportamentos problemáticos em dois pontos críticos do grafo:

1. **Nó `formular` inventava placeholders:** em perguntas genéricas (sem CPF ou número de processo), o modelo adicionava trechos como `[inserir CPF]` ou `[inserir número do processo]` à pergunta reformulada. Isso corrompeu todos os nós seguintes do grafo — o SQL gerado vinha com sintaxe inválida e as buscas nunca retornavam resultados.

2. **Classificador instável com fewer exemplos:** com 15 exemplos por categoria, o llama generalizava de forma incorreta. Perguntas relacionais claras (ex: "Como está a carteira de processos?") eram enviadas para `reformular`, e perguntas vetoriais iam para `relacional`. O modelo parecia interpretar intenção geral ao invés de seguir os exemplos literalmente.

### 2. Por que o gpt-5.4-mini-2026-03-17 resolveu

O `gpt-5.4-mini-2026-03-17` apresentou comportamento mais previsível nas mesmas condições:

- Segue regras negativas explícitas no prompt (`NUNCA adicione`, `NUNCA invente`) de forma literal e consistente — o nó `formular` parou de criar placeholders.
- Com exemplos suficientes, classifica corretamente mesmo consultas não cobertas textualmente pelos exemplos — o que levou à expansão do classificador de 15 para 30 exemplos por categoria (relacional) e à adição de regras de desempate explícitas para panorama/carteira, honorários e prazos.
- A saída estruturada via `with_structured_output` se mostrou mais estável para o schema Pydantic em português jurídico.

### 3. Escopo da migração

Todos os pontos do sistema que chamavam o LLM foram atualizados:

| Arquivo | Antes | Depois |
| ------- | ----- | ------ |
| `fase1_engenharia/pipeline_extracao.py` | `ChatGroq` + `GROQ_API_KEY` | `ChatOpenAI` + `OPENAI_API_KEY` |
| `fase1_engenharia/ingestao/orquestrador.py` | `ChatGroq` + `GROQ_API_KEY` | `ChatOpenAI` + `OPENAI_API_KEY` |
| `fase2_agente/grafo/grafo.py` | `ChatGroq` + `GROQ_API_KEY` | `ChatOpenAI` + `OPENAI_API_KEY` |
| `fase2_agente/grafo/nos/classificar_pergunta.py` | `ChatGroq` + `GROQ_API_KEY` | `ChatOpenAI` + `OPENAI_API_KEY` |
| `fase2_agente/automacoes/verificar_prazos.py` | `ChatGroq` + `GROQ_API_KEY` | `ChatOpenAI` + `OPENAI_API_KEY` |
| `fase3_interface/app/pages/insights.py` | `groq.Groq` + `GROQ_API_KEY` | `openai.OpenAI` + `OPENAI_API_KEY` |

### 4. Ajustes de prompt decorrentes da migração

A troca de modelo exigiu revisões nos prompts para aproveitar o comportamento mais literal do gpt-5.4-mini-2026-03-17:

- **Nó `formular`:** regras explícitas adicionadas proibindo invenção de placeholders e instruindo o modelo a manter o caráter geral da pergunta quando não há identificadores no histórico.
- **`_extrair_params_honorarios`:** lista explícita dos três status válidos (`atrasado`, `em_dia`, `quitado`) com mapeamento de termos coloquiais (`em atraso`, `inadimplente` → `atrasado`), e instrução para retornar `null` para `em aberto` (que deve consultar todos os status).
- **Classificador:** exemplos expandidos de 15 para 30 na categoria relacional e adicionadas três regras de desempate no topo (panorama/carteira → relacional; honorários em aberto/atrasados → relacional; prazos → relacional).
- **`gerar_resposta`:** instrução adicionada para não repetir literalmente mensagens de sistema quando uma das fontes não retornar dados.

### 5. Trade-off de custo

O `gpt-5.4-mini` tem custo por token; o Groq oferecia plano gratuito. Para o volume da demo e dos testes do projeto (dezenas a poucos centenas de chamadas), o custo é negligenciável. A decisão priorizou **confiabilidade da apresentação** sobre custo zero — um agente que responde corretamente vale mais do que um agente gratuito que inventa dados.