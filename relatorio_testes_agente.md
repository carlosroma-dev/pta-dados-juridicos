# Relatório de Testes — Agente Jurídico
### PTA Dados 2026.1 — Equipe Mezzalira

---

## Ambiente de teste

- **Como foi testado:** interface Streamlit (`http://localhost:8501`, aba Agente Jurídico), Swagger UI (`http://localhost:8000/docs`, rota `POST /agente/perguntar`) e logs de container via `docker compose logs -f api`.
- **Pré-requisitos:** Postgres no ar com dados seedados, `OPENAI_API_KEY` configurada, API com `API_KEY` no `.env`, containers `api`, `interface` e `scheduler` no ar.
- **Modelo LLM:** `gpt-5.4-mini-2026-03-17` (OpenAI), `temperature=0`.
- **Modelo de embeddings:** `nomic-ai/nomic-embed-text-v1` (local, 768 dim).
- **Período de testes:** 02/06/2026 a 05/06/2026

---

## 1. Hipótese inicial — o que esperávamos ao começar

Antes de rodar o primeiro teste, a hipótese era de que a troca de LLM seria simples: substituir `ChatGroq` por `ChatOpenAI`, ajustar a variável de ambiente e subir o container. Os prompts já existiam e tinham sido validados com o `llama-3.3-70b-versatile`, então imaginávamos que o comportamento seria equivalente ou até melhor com um modelo da OpenAI.

O raciocínio era:
- O grafo estava funcionando com o Groq, portanto a lógica estava correta.
- O `gpt-5.4-mini` é um modelo robusto para tarefas estruturadas.
- A mudança seria basicamente de credencial e de nome de classe Python.

Essa hipótese se mostrou **parcialmente errada**. O comportamento dos dois modelos é suficientemente diferente para quebrar várias partes do sistema que dependiam de como o llama interpretava prompts com margem de liberdade.

---

## 2. Resumo executivo

| Métrica | Valor |
| :--- | :--- |
| Testes registrados | 15 |
| Passaram na validação (`validado: true`) | 10 |
| Com problema identificado durante os testes | 7 |
| Problemas corrigidos | 7 |
| Bugs críticos encontrados | 2 |
| Arquivos modificados para corrigir | 8 |

---

## 3. Tabela de testes (índice)

Status: ✅ passou · ❌ falhou · 🔧 falhou e foi corrigido

| # | Pergunta | Rota esperada | Status final | Problema identificado |
| :--- | :--- | :---: | :---: | :--- |
| 1 | Quantos processos vencem daqui a duas semanas? | relacional | ✅ | Janela 14d usava fallback de 7d — não corrigido nesta sprint |
| 2 | Quais processos têm prazo nos próximos 7 dias? | relacional | 🔧 | Ia para `reformular` antes da correção do classificador |
| 3 | Como está a carteira de processos do escritório? | relacional | 🔧 | Ia para `reformular` — faltavam exemplos de panorama |
| 4 | Quais honorários estão em aberto ou atrasados? | relacional | 🔧 | Bug crítico: `formular` inventava `[inserir CPF]`, corrompendo o SQL |
| 5 | Quais processos têm honorários em atraso? | relacional | ✅ | — |
| 6 | O que consta nos contratos e petições cadastrados? | vetorial | 🔧 | Ia para `relacional` — faltavam exemplos vetorial genérico |
| 7 | O que diz o contrato de honorários da Ana Lima? | vetorial | ✅ | — |
| 8 | Quem é o advogado da Fernanda Costa? | híbrido | ✅ | — |
| 9 | Qual é o conteúdo do acordo extrajudicial da Fernanda Costa? | híbrido | 🔧 | Ia para `relacional` — faltava exemplo explícito |
| 10 | Quero saber sobre o acordo extrajudicial da Fernanda Costa | híbrido | 🔧 | Referência implícita — `formular` inventava placeholder |
| 11 | Liste os 5 maiores honorários atrasados | relacional | ✅ | — |
| 12 | Qual o CPF da Ana Lima? | relacional | ✅ | — |
| 13 | E aí, tudo certo? (fora de escopo) | reformular | ✅ | — |
| 14 | Qual a previsão do tempo amanhã em Recife? | reformular | ✅ | — |
| 15 | Insights da aba Insights | interface | 🔧 | `max_tokens` não suportado em modelos novos → `max_completion_tokens` |

---

## 4. O processo de investigação

### 4.1 A migração inicial (o que parecia simples)

A primeira etapa foi a substituição em lote:

```
langchain_groq.ChatGroq → langchain_openai.ChatOpenAI
GROQ_API_KEY            → OPENAI_API_KEY
llama-3.3-70b-versatile → gpt-5.4-mini-2026-03-17
groq.Groq               → openai.OpenAI  (insights.py)
```

Ao tentar instalar as dependências, o primeiro erro surgiu imediatamente:

```
ERROR: Could not find a version that satisfies the requirement openai==1.59.0
```

A versão `1.59.0` não existia no PyPI. A versão mais próxima disponível era `1.59.2`. Corrigido em `requirements.txt` e `fase3_interface/requirements.txt`.

A segunda falha imediata foi na aba Insights:

```
Erro ao chamar o LLM: Error code: 400 - max_tokens not supported
```

O parâmetro `max_tokens` foi descontinuado nos modelos mais novos da OpenAI e substituído por `max_completion_tokens`. Corrigido em `fase3_interface/app/pages/insights.py`.

---

### 4.2 O agente subia, mas não respondia

Com o ambiente corrigido, o agente subia e a API respondia. O problema era que perguntas que deveriam funcionar retornavam respostas como:

> *"Não ficou claro o que você quer saber..."*

> *"Não encontrei essa informação nos registros oficiais."*

As primeiras perguntas testadas:

- **"Quais processos têm prazo nos próximos 7 dias?"** → `reformular`
- **"Como está a carteira de processos do escritório?"** → `reformular`
- **"Quais honorários estão em aberto ou atrasados?"** → sem resultado

A hipótese imediata foi: *problema no classificador*. O classificador estava mandando perguntas relacionais claras para `reformular`.

---

### 4.3 Diagnóstico — o classificador estava ficando perdido

O `llama-3.3-70b-versatile` tinha boa generalização semântica: com poucos exemplos, entendia a categoria pela intenção. O `gpt-5.4-mini` é mais literal — ele segue os exemplos fornecidos de perto, e se a pergunta não se assemelha textualmente a nenhum exemplo, a confiança cai.

Com 15 exemplos por categoria, perguntas como "Como está a carteira?", "Me dá um panorama geral" e "Quais processos têm prazo?" não tinham correspondência próxima nos exemplos RELACIONAL e eram classificadas com `confiança: baixa` → caindo em `reformular` ou sendo forçadas para `híbrido`.

**Ação:** Expansão dos exemplos de 15 para 30 na categoria RELACIONAL, cobrindo:
- Panorama / carteira / visão geral do escritório
- Honorários em aberto / atrasados / em dia
- Prazos / vencimentos urgentes
- Distribuição e contagens

Adição de 3 exemplos VETORIAL para consultas genéricas de documentos e 3 exemplos HÍBRIDO para consultas sobre acordos de clientes específicos.

Adição de regras de desempate explícitas no topo do prompt:
```
- Pergunta sobre visão geral, panorama, carteira → RELACIONAL
- Pergunta sobre honorários em aberto/atrasados  → RELACIONAL
- Pergunta sobre prazos, vencimentos urgentes    → RELACIONAL
```

Após essa correção, o classificador passou a rotear corretamente os testes 2, 3 e 6.

---

### 4.4 Bug crítico — o nó `formular` inventando dados

Com o classificador corrigido, os testes 4 e 10 ainda falhavam com respostas sem sentido. A resposta para "Quais honorários estão em aberto ou atrasados?" continuava vazia.

A investigação dos logs revelou o bug real:

```
2026-06-03 | INFO    | Nó: formular
Pergunta reformulada: "Quais honorários estão em aberto ou atrasados 
para o processo [inserir número do processo] do cliente [inserir CPF]?"
```

O nó `formular` estava **inventando placeholders** (`[inserir CPF]`, `[inserir ID]`, `[inserir número do processo]`) em perguntas genéricas que não tinham um identificador específico. Isso acontecia porque o prompt original pedia ao modelo para "deixar a pergunta mais específica" sem proibir explicitamente a criação de informações novas.

O efeito em cascata: a pergunta corrompida chegava ao sub-roteador relacional com texto literal `[inserir CPF]`, o gerador de SQL incluía esse placeholder no WHERE, e o banco rejeitava a query com erro de sintaxe.

**Ação:** Reescrita completa do system prompt do nó `formular` com regras negativas explícitas:

```
REGRAS OBRIGATÓRIAS:
- Use o histórico para resolver pronomes: "ela", "o dele", "esse processo" etc.
- Preserve dados já presentes na pergunta (CPF, ID, número de processo).
- NUNCA adicione informações que não estavam na pergunta ou no histórico.
- NUNCA invente ou adicione placeholders como [inserir CPF], [inserir ID].
- Se não houver identificadores específicos, apenas reescreva de forma clara mantendo o caráter geral.
```

Esse bug era a causa raiz de pelo menos 4 dos 7 problemas identificados.

---

### 4.5 Problema no `checar_honorarios` — bloqueando queries por status

Após corrigir o `formular`, "Quais honorários estão em aberto ou atrasados?" chegava corretamente ao sub-roteador relacional — mas era redirecionado de `checar_honorarios` para `consultar_banco` por uma guarda que exigia número de processo CNJ.

A guarda original:
```python
if escolha == "checar_honorarios" and not _CNJ_RE.search(pergunta):
    escolha = "consultar_banco"
```

Essa lógica foi escrita para evitar que `checar_honorarios` rodasse sem um processo específico, mas impedia consultas legítimas por status (atrasado, em dia, quitado) sem número de processo.

**Ação:** Adição de verificação de status antes do redirecionamento:
```python
_STATUS_HONORARIOS = ("atrasado", "em_dia", "quitado", "em aberto", "em atraso", "inadimplente")
tem_status = any(s in pergunta.lower() for s in _STATUS_HONORARIOS)
if escolha == "checar_honorarios" and not _CNJ_RE.search(pergunta) and not tem_status:
    escolha = "consultar_banco"
```

---

### 4.6 Problema no `_extrair_params_honorarios` — status inválido

Mesmo com a guarda corrigida, a ferramenta `checar_honorarios` às vezes retornava zero resultados. Investigando o log do SQL gerado:

```sql
WHERE status_pagamento = 'em_aberto'
-- resultado: 0 linhas (coluna não tem esse valor)
```

O modelo estava interpretando "em aberto" da pergunta como um valor de status e passando `em_aberto` como parâmetro — mas os valores válidos no banco são apenas `atrasado`, `em_dia` e `quitado`.

**Ação:** Reescrita do prompt de extração de parâmetros com mapeamento explícito:
```
Status válidos APENAS: atrasado, em_dia, quitado.
'em aberto', 'pendente', 'em atraso', 'inadimplente' NÃO são status válidos — use null.
Se a pergunta mencionar 'em aberto E atrasado' ou 'em aberto ou atrasado', use null (retorna todos).
```

---

### 4.7 `gerar_resposta` repetindo mensagens de erro do sistema

Em alguns testes, quando uma das fontes de dados retornava vazio, o agente incluía literalmente a mensagem interna na resposta ao usuário:

> *"Nenhum resultado encontrado para essa consulta. (Fonte: processos.csv)"*

**Ação:** Adição de instrução explícita no prompt de `gerar_resposta`:
```
IMPORTANTE: Se os dados indicarem "Nenhum prazo", "Nenhum resultado" para UMA fonte,
mas houver dados válidos em OUTRA, use os dados válidos. Só diga "Não encontrei" quando
TODAS as fontes estiverem vazias.
NUNCA repita literalmente mensagens de erro do sistema.
```

---

## 5. Registros detalhados dos testes

### Teste #1 — "Quantos processos vencem daqui a duas semanas?"

- **Rota:** relacional → `verificar_prazos`
- **Validado:** `true`
- **Resposta do agente:** listou 4 processos, mas descreveu a janela como "próximas duas semanas, mais especificamente nos próximos 7 dias". Contradição explícita.
- **Causa:** a função `_extrair_dias` extrai apenas números explícitos da pergunta. "Duas semanas" não contém o número de dias em formato numeral, então cai no fallback de 7 dias. Não há conversão semanas/meses → dias.
- **Status de correção:** não corrigido nesta sprint. Workaround: usar "14 dias" na pergunta.
- **Impacto:** baixo — comportamento previsível e a resposta ainda é útil.

---

### Teste #2 — "Quais processos têm prazo nos próximos 7 dias?"

- **Rota esperada:** relacional → `verificar_prazos`
- **Comportamento antes:** classificado como `reformular` com confiança alta.
- **Causa:** nenhum dos 15 exemplos RELACIONAL originais cobria explicitamente "prazos nos próximos N dias". O modelo interpretava como pergunta ambígua.
- **Correção:** adição de "Quais processos têm prazo nos próximos 7 dias?" e "Tem algum prazo vencendo essa semana?" como exemplos diretos + regra de desempate "prazos/vencimentos → RELACIONAL".
- **Resultado após correção:** ✅ classificado como relacional, ferramenta `verificar_prazos`, resposta com lista correta.

---

### Teste #3 — "Como está a carteira de processos do escritório?"

- **Rota esperada:** relacional → `status_carteira`
- **Comportamento antes:** classificado como `reformular`.
- **Causa:** "carteira" e "panorama" não apareciam nos exemplos. O modelo entendia como pergunta vaga sem contexto.
- **Correção:** exemplos adicionados ("Como está a carteira de processos do escritório?", "Mostre um panorama geral dos processos", "Como está a distribuição por status?") + regra de desempate "panorama/carteira → RELACIONAL (use status_carteira)".
- **Resultado após correção:** ✅ classificado como relacional, ferramenta `status_carteira`, retornou distribuição completa por advogado e status.

---

### Teste #4 — "Quais honorários estão em aberto ou atrasados?"

- **Rota esperada:** relacional → `checar_honorarios`
- **Comportamento antes:** classificado como relacional, mas retornava "Não encontrei".
- **Causa (investigação em camadas):**
  1. Primeiro suspeito: classificador → descartado, rota estava correta.
  2. Segundo suspeito: ferramenta → investigação dos logs revelou que o `formular` estava corrompendo a pergunta com `[inserir CPF]`.
  3. Terceiro suspeito (após corrigir formular): guarda do `checar_honorarios` bloqueando por falta de CNJ.
  4. Quarto suspeito (após corrigir guarda): `_extrair_params_honorarios` gerando `em_aberto` como status, retornando 0 linhas.
- **Correções aplicadas:** 4 camadas de fix. Cada uma descoberta só depois que a anterior foi resolvida.
- **Resultado:** ✅ retorna lista de honorários atrasados com valores corretos.

---

### Teste #6 — "O que consta nos contratos e petições cadastrados?"

- **Rota esperada:** vetorial
- **Comportamento antes:** classificado como relacional.
- **Causa:** a pergunta não cita um documento ou cliente específico. O modelo entendia como consulta de contagem/listagem (relacional) em vez de consulta de conteúdo.
- **Correção:** adição de exemplos vetorial genérico: "O que consta nos contratos e petições cadastrados?", "Mostre o conteúdo dos documentos do escritório", "O que dizem os contratos cadastrados?".
- **Resultado após correção:** ✅ classificado como vetorial, busca semântica nos chunks indexados, resposta com trechos reais dos PDFs.

---

### Teste #10 — "Quero saber sobre o acordo extrajudicial da Fernanda Costa"

- **Contexto:** segunda mensagem numa conversa onde a primeira foi "Qual o advogado da Fernanda Costa?".
- **Rota esperada:** híbrido
- **Comportamento antes:** `formular` produzia "Quero saber sobre o acordo extrajudicial da Fernanda Costa [inserir número do processo]".
- **Causa:** o modelo tentava completar a pergunta com um número de processo que não existia na conversa.
- **Correção:** regra NUNCA no prompt do `formular` + instrução de manter caráter geral quando não há identificadores.
- **Resultado após correção:** ✅ agente buscou por "Fernanda Costa" no banco, identificou o processo com acordo extrajudicial e retornou o conteúdo do documento correto.

---

### Teste #15 — Aba Insights

- **Comportamento:** ao clicar em "Atualizar" na aba Insights, exibia:
  ```
  Erro ao chamar o LLM: Error code: 400 - {'error': {'message': 'max_tokens is not supported...', ...}}
  ```
- **Causa:** o parâmetro `max_tokens` foi descontinuado em modelos mais recentes da OpenAI. O arquivo `insights.py` ainda usava a API do Groq com esse parâmetro.
- **Correção:** `max_tokens=2000` → `max_completion_tokens=2000` em `_gerar_insights()`.
- **Resultado:** ✅ aba gera entre 4 e 7 insights estratégicos a partir dos documentos indexados.

---

## 6. Problemas de infraestrutura encontrados

### 6.1 `docker compose down -v` destrói o banco

Durante os testes, o container foi reiniciado várias vezes para aplicar mudanças de código. Em dois momentos, o comando `docker compose down -v` foi usado por engano — esse flag remove os volumes, o que apaga o banco de dados inteiro.

**Consequência:** foi necessário rodar `python -m fase1_engenharia.db.seed` depois de cada ocorrência para repopular as tabelas.

**Comando correto para reiniciar após mudança de código:**
```bash
docker-compose up --build api interface scheduler -d
```

Esse comando reconstrói apenas os containers de código (sem tocar nos volumes do banco).

**Comando destrutivo — usar só para reset completo:**
```bash
docker compose down -v && docker compose up -d
python -m fase1_engenharia.db.seed
```

### 6.2 Primeira execução lenta do modelo de embeddings

Na primeira vez que a rota `/busca/` é chamada após subir o container, o servidor demora ~15–30 segundos para responder. Isso é esperado — o modelo `nomic-ai/nomic-embed-text-v1` (~500 MB) é carregado em memória no primeiro acesso (lazy loading). As requisições seguintes são instantâneas.

---

## 7. Migração Groq → OpenAI: lições aprendidas

### O que mudou de comportamento entre os modelos

| Comportamento | llama-3.3-70b (Groq) | gpt-5.4-mini (OpenAI) |
| :--- | :--- | :--- |
| Generalização semântica | Alta — poucos exemplos bastavam | Baixa — precisa de exemplos textuais próximos |
| Seguimento de regras negativas | Parcial — às vezes ignorava | Literal — segue NUNCA/SEMPRE rigorosamente |
| Saída estruturada (Pydantic) | Estável | Mais estável ainda |
| Tendência a completar lacunas | Baixa — aceitava perguntas abertas | Alta — tentava "ajudar" inventando dados |
| Custo | Gratuito (Groq free tier) | Por token (baixo para o volume do projeto) |

### O que ficou melhor com o gpt-5.4-mini

- Regras negativas no `formular` funcionam 100% — zero ocorrências de placeholder após a correção.
- Saída estruturada do classificador é mais consistente — `confiança: alta` nos casos claros, `baixa` nos casos de fronteira.
- Prompts de extração de parâmetros (status, dias) são seguidos mais literalmente.

### O que exigiu mais trabalho

- O classificador precisou de mais exemplos (15 → 30 por categoria) para cobrir casos que o llama resolvia por generalização.
- Prompts que funcionavam com "seja preciso" precisaram de regras explícitas ("NUNCA", "APENAS", "OBRIGATÓRIO").

---

## 8. Estado final dos componentes testados

| Componente | Estado | Observação |
| :--- | :---: | :--- |
| Classificador de perguntas | ✅ Estável | 30 exemplos RELACIONAL, 15 VETORIAL, 14 HÍBRIDO, 10 REFORMULAR |
| Nó `formular` | ✅ Estável | Regras NUNCA previnem placeholder |
| Sub-roteador relacional | ✅ Estável | Guarda `checar_honorarios` com verificação de status |
| Ferramenta `checar_honorarios` | ✅ Estável | Status válidos documentados no prompt |
| Ferramenta `verificar_prazos` | ✅ Estável | Fallback 7 dias para "semanas/meses" ainda presente |
| Ferramenta `consultar_banco` | ✅ Estável | SQL gerado dinamicamente, guard DDL/DML ativa |
| Ferramenta `status_carteira` | ✅ Estável | Visão geral completa por advogado |
| Nó `gerar_resposta` | ✅ Estável | Não repete mensagens de erro do sistema |
| Nó `validar` | ✅ Estável | Critério balanceado — não exige dados concretos para passar |
| Aba Insights | ✅ Estável | `max_completion_tokens` corrigido |
| Busca vetorial (pgvector) | ✅ Estável | Embeddings locais, sem dependência de API externa |

---

## 9. Pontos em aberto (não resolvidos nesta sprint)

| # | Descrição | Impacto | Sugestão |
| :--- | :--- | :---: | :--- |
| 1 | `_extrair_dias` não converte "semanas" / "meses" para dias | Baixo | Adicionar mapeamento: "semana" → 7, "mês" → 30 |
| 2 | Agente não combina respostas de duas perguntas pendentes em uma | Baixo | Limitação de design do grafo — seria necessário memória de "intenções pendentes" |
| 3 | Busca vetorial sem filtro por data — retorna documentos antigos com mesma relevância | Médio | Adicionar campo `data_documento` ao schema e filtrar por recência |
| 4 | Sem paginação nos endpoints de listagem | Médio | Aceitável para o volume atual; priorizar se base crescer |

---

*Relatório gerado pela equipe de desenvolvimento — Equipe Mezzalira, CITi-UFPE, jun/2026.*
