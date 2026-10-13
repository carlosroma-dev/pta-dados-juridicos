# PTA Dados 2026.1 — Equipe Mezzalira

> Projeto acadêmico desenvolvido pela Equipe Mezzalira. Esta é uma cópia pública para portfólio; os créditos do trabalho coletivo permanecem com a equipe. Os dados de demonstração são fictícios.

Este projeto organiza os dados de um escritório de advocacia. Ele pega planilhas e PDFs de processos, limpa essas informações, guarda tudo num banco de dados e disponibiliza uma API onde dá pra consultar clientes, processos, prazos e até fazer perguntas em linguagem natural sobre os documentos. Por cima disso, há um agente conversacional e uma interface visual completa.

O sistema está dividido em três fases, **todas implementadas e funcionando**:

- **Fase 1 — Engenharia de Dados:** ingestão, limpeza, banco de dados, indexação vetorial e API REST (FastAPI).
- **Fase 2 — Agente:** agente conversacional com RAG e LangGraph, ferramentas SQL e automação de alertas de prazo por e-mail.
- **Fase 3 — Interface:** interface Streamlit com painel analítico, chat com o agente, upload de documentos, insights automáticos e central de alertas.

Repositório: https://github.com/carlosroma-dev/pta-dados-juridicos

---

## Índice

1. [Antes de começar: instale estas ferramentas](#antes-de-começar-instale-estas-ferramentas)
2. [Baixar e abrir o projeto](#baixar-e-abrir-o-projeto)
3. [Como rodar com Docker (recomendado)](#como-rodar-com-docker-recomendado)
4. [Como rodar manualmente (passo a passo)](#como-rodar-manualmente-passo-a-passo)
5. [O que dá pra consultar (API)](#o-que-dá-pra-consultar-api)
6. [Fase 2 — Agente de perguntas](#fase-2--agente-de-perguntas-em-linguagem-natural)
7. [Automação de alertas de prazo](#automação-de-alertas-de-prazo)
8. [Fase 3 — Interface visual](#fase-3--interface-visual-streamlit)
9. [Comandos extras (opcionais)](#comandos-extras-opcionais)
10. [Onde fica cada coisa](#onde-fica-cada-coisa)
11. [Se algo der errado](#se-algo-der-errado)

---

## Antes de começar: instale estas ferramentas

Se você nunca mexeu com programação, instale os 4 programas abaixo primeiro. Clique no nome, baixe e instale como qualquer outro programa (avançando as telas). É preciso fazer isso só uma vez.

- **[Python 3.11+](https://www.python.org/downloads/)** — a linguagem que roda o projeto. **No Windows, na primeira tela da instalação, marque a caixinha "Add Python to PATH"** antes de clicar em instalar. Isso é importante.
- **[Git](https://git-scm.com/downloads)** — serve para baixar o projeto. Pode instalar com as opções padrão.
- **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** — liga o banco de dados e todos os serviços sem complicação. Depois de instalar, **abra o programa Docker Desktop e deixe ele aberto** enquanto usa o projeto.
- **[Visual Studio Code (VS Code)](https://code.visualstudio.com/)** — o programa onde você vai abrir o projeto e digitar os comandos.

Você também vai precisar de **internet** (na primeira vez o projeto baixa um modelo de IA de ~500 MB sozinho).

### Uma coisa que você precisa pedir à equipe

Os documentos do escritório ficam guardados numa pasta no Google Drive, e a leitura deles usa um serviço de inteligência artificial. Por segurança, as chaves de acesso **não vêm no projeto**. Antes de começar, peça a um membro da equipe:

1. **O arquivo `service_account.json`** — a credencial que autoriza o projeto a acessar a pasta do Google Drive. A pessoa também vai liberar o seu acesso à pasta.

### Coisas que você precisa criar

2. **Uma chave da OpenAI (`OPENAI_API_KEY`)** — usada para a IA ler e organizar o conteúdo dos PDFs (Fase 1), para o agente de perguntas e a automação de alertas (Fase 2) e para a aba de insights (Fase 3). Crie a sua em [platform.openai.com](https://platform.openai.com).

3. **Uma chave do Resend (`RESEND_API_KEY`)** — usada pela automação de alertas de prazo para enviar e-mails aos advogados. Crie gratuitamente em [resend.com](https://resend.com). No plano gratuito, e-mails só podem ser enviados para o endereço verificado da sua conta.

Guarde tudo — você vai usá-los nos passos de configuração.

---

## Baixar e abrir o projeto

### 1. Baixar o projeto com o Git

Escolha uma pasta no seu computador onde o projeto vai ficar (por exemplo, a pasta "Documentos"). Abra o **VS Code**, e no menu de cima vá em **Terminal → New Terminal** (ou Ctrl+`). Vai aparecer uma faixa de comando na parte de baixo da tela — é ali que você digita os comandos.

No terminal, cole o comando abaixo e aperte Enter. Ele baixa o projeto inteiro:

```bash
git clone https://github.com/carlosroma-dev/pta-dados-juridicos.git
```

### 2. Abrir a pasta do projeto no VS Code

Ainda no VS Code, vá em **File → Open Folder** e selecione a pasta `PTA-Dados-26-Equipe-Mezzalira` que acabou de baixar.

A partir de agora, sempre que abrir um terminal no VS Code (**Terminal → New Terminal**), ele já estará dentro da pasta certa do projeto. É nesse terminal que você roda todos os comandos a seguir.

---

## Como rodar com Docker (recomendado)

Esta é a forma mais simples: um único comando sobe **tudo** (banco, carga dos dados, API, interface e scheduler). Antes de rodar, você precisa ter feito o **passo de configuração do `.env`** (descrito mais abaixo, no [passo 3 do modo manual](#3-criar-e-preencher-o-arquivo-de-configuração)).

Com o **Docker Desktop aberto** e o `.env` preenchido:

```bash
docker compose up --build
```

Isso faz automaticamente, na ordem certa:

1. Sobe o banco **PostgreSQL com pgvector** e cria o schema.
2. **Popula** as tabelas com os dados limpos das planilhas (serviço `init`).
3. **Extrai e estrutura** os PDFs com IA (pula os já processados).
4. **Indexa** os documentos no pgvector para a busca semântica.
5. Sobe a **API** em `http://localhost:8000` (Swagger em `/docs`).
6. Sobe a **interface** Streamlit em `http://localhost:8501`.
7. Sobe o **scheduler** de alertas de prazo (roda diariamente às 08:00).

Na segunda vez em diante, basta `docker compose up` (sem `--build`).

Para parar tudo: `Ctrl + C` e depois `docker compose down`.

> **Atenção:** `docker compose down -v` (com `-v`) apaga **todos os volumes**, incluindo o banco de dados inteiro. Use isso só quando quiser resetar do zero. Para parar normalmente, use `docker compose down` sem o `-v`.

> Os PDFs já vêm versionados em `data/pdfs/` e os JSONs estruturados em `data/structured/`, então o Docker não depende do Google Drive para a demo. O watcher do Drive é opcional (veja o modo manual, passo 6).

---

## Como rodar manualmente (passo a passo)

Use este modo se quiser entender cada etapa ou rodar fora do Docker. Faça os passos **na ordem**, todos no terminal do VS Code. Cada bloco cinza é um comando: copie, cole e aperte Enter.

### 1. Preparar o "espaço isolado" do projeto

Isso cria uma caixinha separada pra não bagunçar o resto do seu computador.

```bash
python -m venv .venv

# Se você usa Linux ou Mac:
source .venv/bin/activate
# Se você usa Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

> Se deu certo, vai aparecer um `(.venv)` no começo da linha do terminal.

### 2. Instalar o que o projeto usa

```bash
pip install -r requirements.txt
```

### 3. Criar e preencher o arquivo de configuração

```bash
cp .env.example .env
```

Esse comando cria um arquivo chamado `.env`. Abra esse arquivo no VS Code (ele aparece na lista de arquivos à esquerda) e preencha estas linhas com o que você pegou com a equipe:

```
OPENAI_API_KEY=cole_aqui_a_sua_chave_da_openai
LLM_MODEL=gpt-5.4-mini-2026-03-17
GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
DRIVE_FOLDER_ID=seu_id_da_pasta
DRIVE_POLL_INTERVAL=60
RESEND_API_KEY=cole_aqui_a_sua_chave_do_resend
EMAIL_FALLBACK=seu_email_verificado_no_resend@exemplo.com
```

Depois, coloque o arquivo **`service_account.json`** (que você recebeu da equipe) na **pasta raiz do projeto** — o mesmo lugar onde está o `docker-compose.yml`. O resto das configurações já vem com valores que funcionam.

> O `.env` **nunca** deve ser enviado ao GitHub — ele contém suas chaves secretas. O `.gitignore` já cuida disso.

### 4. Ligar o banco de dados

Confira que o **Docker Desktop está aberto**, então rode:

```bash
docker compose up -d db
```

Pra conferir se ligou (deve aparecer "Up" ou "healthy"):

```bash
docker compose ps
```

### 5. Carregar os dados das planilhas no banco

```bash
python -m fase1_engenharia.db.seed
```

Aqui o projeto lê as 4 planilhas, **corrige os erros** (datas bagunçadas, valores duplicados, etc.) e guarda tudo no banco. Pode rodar de novo quantas vezes quiser sem problema (é idempotente).

### 6. (Opcional) Baixar PDFs novos do Google Drive

Os PDFs do escritório já vêm versionados em `data/pdfs/`. Você só precisa deste passo se quiser **baixar arquivos novos ou modificados** do Drive:

```bash
python -m fase1_engenharia.ingestao.drive_watcher
```

> ⚠️ **Importante:** esse comando **não para sozinho**. Ele baixa os PDFs e depois fica vigiando a pasta, esperando arquivos novos. Quando aparecer a mensagem de que não há PDFs novos, aperte **`Ctrl + C`** para encerrar e seguir para o próximo passo. Isso é normal.

### 7. Organizar o conteúdo dos PDFs com a IA

```bash
cd fase1_engenharia
python pipeline_extracao.py
cd ..
```

Aqui a inteligência artificial lê cada PDF e extrai as informações importantes (número do processo, partes envolvidas, valores, um resumo), salvando como JSON em `data/structured/`. É esta etapa que usa a sua chave da OpenAI. Documentos já processados são pulados.

> Esse comando precisa ser rodado de dentro da pasta `fase1_engenharia` — por isso o `cd fase1_engenharia` no começo e o `cd ..` no fim, que voltam você para a pasta principal.

### 8. Preparar a busca por perguntas (RAG)

```bash
python -m fase1_engenharia.indexacao.indexar_documentos
```

Isso transforma os documentos em vetores (embeddings) e os guarda no pgvector, permitindo encontrar trechos a partir de perguntas escritas com suas próprias palavras. **Atenção:** a primeira vez demora um pouco, porque é quando o modelo de IA de ~500 MB é baixado.

### 9. Ligar a API

```bash
uvicorn fase1_engenharia.api.main:app --reload
```

Pronto! Abra no navegador:

**→ http://localhost:8000/docs**

Essa página (o **Swagger**) deixa você testar todas as consultas clicando em botões, sem precisar de comando nenhum.

> Para desligar a API quando terminar, volte ao terminal e aperte **`Ctrl + C`**.

### 10. (Opcional) Ligar a interface visual

Com a API no ar, abra **outro terminal**, ative o ambiente isolado (`.venv`) e rode:

```bash
streamlit run fase3_interface/app.py
```

A interface abre em **http://localhost:8501**. Veja mais detalhes na [seção da Fase 3](#fase-3--interface-visual-streamlit).

---

## Integração ponta a ponta

O sistema funciona em dois caminhos independentes:

**Caminho 1 — Pergunta do usuário:**
Interface Streamlit → FastAPI → Agente LangGraph → Retriever (pgvector) e/ou Ferramentas SQL → Resposta com citação de fonte → Interface

**Caminho 2 — Automação agendada:**
Scheduler → LangGraph → Consulta ao banco → E-mails de alerta (Resend) → Log em `logs/alertas_prazos.log`

---

## O que dá pra consultar (API)

A forma mais fácil de explorar é pela página **http://localhost:8000/docs** (Swagger), que lista e testa tudo. Os principais endpoints:

| O que faz | Método e rota |
|---|---|
| Saúde do sistema (banco, pgvector, agente) | `GET /health` |
| Lista de clientes | `GET /clientes/` |
| Lista de processos (filtra por status, cliente_id) | `GET /processos/` |
| Processos com prazo nos próximos N dias | `GET /processos/prazos?dias=30` |
| Honorários (filtra por status_pagamento) | `GET /honorarios/` |
| Lista de advogados | `GET /advogados/` |
| Busca semântica nos documentos | `POST /busca/` |
| Todos os chunks indexados (usado pelos insights) | `GET /busca/chunks` |
| Perguntar ao agente em linguagem natural | `POST /agente/perguntar` |
| Painel: prazos próximos | `GET /painel/prazos?dias=30` |
| Painel: inadimplência por cliente | `GET /painel/inadimplencia` |
| Painel: documentos indexados por tipo | `GET /painel/documentos` |
| Painel: carteira por advogado e status | `GET /painel/carteira` |
| Documentos: listar ingestões / status / enviar PDF | `GET /documentos/` · `GET /documentos/{id}` · `POST /documentos/ingerir` |
| Alertas: ver/editar e-mails, disparar, histórico | `GET·PUT /alertas/emails` · `POST /alertas/disparar` · `GET /alertas/historico` |

> A API usa autenticação por header `X-API-Key` quando `API_KEY` está definida no `.env`. Sem essa variável, ela sobe sem autenticação (modo dev). A rota `/health` é sempre pública.

Exemplos pelo terminal:

```bash
# Ver se está no ar
curl http://localhost:8000/health

# Listar clientes
curl http://localhost:8000/clientes/

# Processos com prazo nos próximos 15 dias
curl "http://localhost:8000/processos/prazos?dias=15"

# Fazer uma busca semântica nos documentos
curl -X POST http://localhost:8000/busca/ \
  -H "Content-Type: application/json" \
  -d '{"pergunta": "acordo de indenização por danos morais", "top_k": 3}'

# Perguntar ao agente
curl -X POST http://localhost:8000/agente/perguntar \
  -H "Content-Type: application/json" \
  -d '{"pergunta": "Quais honorários estão atrasados?"}'
```

---

## Fase 2 — Agente de perguntas em linguagem natural

A Fase 2 implementa um agente conversacional usando **LangGraph** que responde perguntas sobre os dados do escritório. O agente decide automaticamente onde buscar e valida a resposta antes de entregá-la.

### Como o agente decide onde buscar

O classificador roteia cada pergunta para uma de quatro categorias:

- **relacional** — dados estruturados do banco (prazos, status, honorários, CPF, contagens). Usa ferramentas SQL.
- **vetorial** — conteúdo de documentos (contratos, petições, acordos). Usa busca semântica no pgvector.
- **híbrido** — precisa das duas fontes ao mesmo tempo (ex.: "quem é o advogado da Fernanda Costa e o que diz o acordo dela?").
- **reformular** — pergunta vaga demais; o agente pede esclarecimento em vez de chutar.

### O grafo de estados

```
formular → rotear → (buscar_relacional | buscar_vetorial | buscar_hibrido) → gerar_resposta → validar → responder
                ↘ pedir_esclarecimento (quando ambígua)
```

1. **Formular** — reformula a pergunta resolvendo pronomes e referências do histórico.
2. **Rotear** — classifica em relacional / vetorial / híbrido / reformular.
3. **Buscar** — executa a busca na fonte certa (com fallback automático se vier vazio).
4. **Gerar resposta** — o LLM produz a resposta fundamentada no contexto, com citação de fonte.
5. **Validar** — um segundo LLM verifica se a resposta tem conteúdo concreto.
6. **Responder** — entrega a resposta final.

Se a pergunta for ambígua ou a validação falhar (até 2 tentativas cada), o agente retorna uma mensagem pedindo reformulação em vez de inventar uma resposta.

### Ferramentas do agente

Em `fase2_agente/ferramentas/`:

- `verificar_prazos` — processos com prazo próximo.
- `checar_honorarios` — situação financeira por processo ou status.
- `status_carteira` — visão geral da carteira (contagens, distribuição).
- `consultar_banco` — gera SQL dinâmico para consultas livres (CPF, ranking, listagens).
- `buscar_documento` — busca semântica nos PDFs indexados.

### Testar o agente

```bash
# Grafo completo (roda uma pergunta de exemplo e imprime rota + resposta)
python -m fase2_agente.grafo.testar_grafo

# Classificador de perguntas isolado
python -m fase2_agente.grafo.nos.testar_classificacao

# Nó gerador de respostas (requer banco ligado e OPENAI_API_KEY)
python -m fase2_agente.grafo.nos.testar_geracao

# Retriever semântico (requer banco com dados indexados)
python -m fase2_agente.rag.testar_retriever

# Ferramentas do agente
python -m fase2_agente.ferramentas.testar_ferramentas
```

---

## Automação de alertas de prazo

O projeto inclui um scheduler que busca processos com prazo nos próximos 7 dias, agrupa por advogado responsável e envia e-mails de alerta consolidados via Resend. O fluxo é um grafo linear:

```
buscar_prazos → resumir_processos → agrupar_por_advogado → enviar_emails → registrar_log
```

Para disparar manualmente e confirmar que o fluxo funciona:

```bash
python -m fase2_agente.automacoes.scheduler --run-now
```

Para rodar em modo contínuo (dispara todo dia às 08:00, horário de Recife):

```bash
python -m fase2_agente.automacoes.scheduler
```

O resultado de cada execução fica registrado em `logs/alertas_prazos.log`.

> Para usar o envio de e-mails, preencha `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_FALLBACK` e os e-mails dos advogados no `.env` conforme o `.env.example`. No plano gratuito do Resend, e-mails só chegam ao endereço verificado da conta.

---

## Fase 3 — Interface visual (Streamlit)

A Fase 3 é uma interface visual que apresenta os dados e o agente de forma mais amigável que o Swagger. Ela **não acessa o banco diretamente** — tudo que aparece na tela vem da API (Fases 1 e 2), através de um cliente HTTP.

### Como rodar

Com a API já no ar (passo 9 do modo manual), abra **outro terminal**, ative o ambiente isolado e rode:

```bash
streamlit run fase3_interface/app.py
```

A interface abre no navegador (por padrão **http://localhost:8501**). Na barra lateral há um indicador mostrando se a interface conseguiu se conectar e autenticar na API.

### As 5 abas

| Aba | O que faz |
|---|---|
| **Painel de Consultas** | Dashboard com gráficos: prazos próximos, inadimplência por cliente, documentos por tipo e carteira por advogado. |
| **Agente Jurídico** | Chat em linguagem natural com o agente da Fase 2, com histórico de conversas. |
| **Adicionar Documento** | Upload de um PDF novo, que dispara o pipeline completo (extrair → estruturar → indexar) e acompanha o status. |
| **Insights do Agente** | A IA analisa toda a base de documentos indexados e gera insights estratégicos automaticamente. |
| **Central de Alertas** | Visualiza e dispara os alertas de prazo, e configura os e-mails dos advogados. |

A interface usa as variáveis `API_BASE_URL` e `API_KEY` do `.env` (a mesma chave da API — não há chave separada).

---

## Comandos extras (opcionais)

Você só precisa destes se quiser refazer alguma etapa manualmente:

```bash
# Limpar as planilhas e gerar os CSVs organizados em data/planilhas_limpos/
python -m fase1_engenharia.limpeza.pipeline --salvar-csv

# Extrair apenas o texto cru dos PDFs (sem a IA), salvando em data/raw/
python -m fase1_engenharia.ingestao.extrair_pdfs

# Testar a busca semântica sem precisar ligar a API
python -m fase1_engenharia.indexacao.testar_busca

# Inspecionar as tabelas direto no banco
docker exec -it pta_dados_db psql -U postgres -d pta_dados -c "\dt"
```

---

## Onde fica cada coisa

```
PTA-Dados-26-Equipe-Mezzalira/
├── docker-compose.yml            # Orquestra todos os serviços (db, init, api, interface, scheduler)
├── Dockerfile                    # Imagem usada por todos os serviços de código
├── requirements.txt              # Dependências da API e do pipeline
├── railway.json                  # Configuração de deploy no Railway
├── scripts/release.sh            # Comando de release (seed + extração + indexação)
├── .env.example                  # Modelo do arquivo de configuração
├── service_account.json          # Credencial do Google (você recebe da equipe — não versionado)
├── README.md                     # Este arquivo
├── DECISIONS.md                  # Por que cada escolha técnica foi feita
├── DEPLOY_CHECKLIST.md           # Passo a passo do deploy em produção
├── relatorio_testes_agente.md    # Registro dos testes do agente
│
├── data/                         # Os dados do projeto
│   ├── planilhas/                #   4 planilhas originais (.xlsx)
│   ├── planilhas_limpos/         #   versões limpas em CSV
│   ├── pdfs/                     #   PDFs dos processos
│   ├── raw/                      #   texto cru extraído dos PDFs
│   └── structured/               #   JSONs estruturados pela IA
│
├── fase1_engenharia/             # FASE 1 — pipeline de dados e API
│   ├── ingestao/                 #   lê planilhas e baixa/lê os PDFs do Drive
│   │   ├── ler_planilhas.py      #     leitura das 4 planilhas
│   │   ├── extrair_pdfs.py       #     extração de texto (pdfplumber)
│   │   ├── drive_watcher.py      #     baixa PDFs novos do Google Drive
│   │   ├── drive_client.py       #     cliente da API do Drive
│   │   ├── armazenamento.py      #     salva PDFs recebidos
│   │   └── orquestrador.py       #     pipeline de um PDF (extrair→estruturar→indexar)
│   ├── limpeza/                  #   corrige e organiza os dados
│   │   ├── pipeline.py           #     orquestra a limpeza das 4 tabelas
│   │   ├── limpar_*.py           #     uma função por tabela
│   │   ├── transformacoes.py     #     utilitários reusáveis (datas, valores, enums)
│   │   └── integridade_referencial.py  # coerência temporal e FKs
│   ├── db/                       #   banco de dados
│   │   ├── models.py             #     modelos SQLAlchemy + schemas Pydantic
│   │   ├── database.py           #     conexão e sessão
│   │   └── seed.py               #     limpa as planilhas e popula o banco
│   ├── indexacao/                #   indexação vetorial (pgvector)
│   │   ├── indexar_documentos.py #     gera embeddings e insere os chunks
│   │   └── testar_busca.py
│   ├── api/                      #   API REST (FastAPI)
│   │   ├── main.py               #     app + autenticação + /health
│   │   ├── routes/               #     uma rota por recurso (clientes, processos, ...)
│   │   └── models/               #     schemas de request/response e enums
│   ├── schemas/                  #   schema de extração dos documentos (Pydantic)
│   ├── utils/                    #   utilitários (pdf_handler)
│   ├── docs/                     #   schema.sql, init.sql e DiagramaER.png
│   └── pipeline_extracao.py      #   usa a IA para estruturar o conteúdo dos PDFs
│
├── fase2_agente/                 # FASE 2 — agente conversacional (LangGraph)
│   ├── rag/                      #   retriever semântico (pgvector)
│   │   └── retriever.py          #     busca chunks por similaridade cosseno
│   ├── grafo/                    #   grafo LangGraph do agente
│   │   ├── grafo.py              #     grafo completo (formular→rotear→buscar→gerar→validar)
│   │   ├── estado.py             #     definição do AgentState
│   │   └── nos/                  #     nós individuais
│   │       ├── classificar_pergunta.py  # classifica: relacional/vetorial/híbrido/reformular
│   │       └── gerar_resposta.py        # gera resposta fundamentada no contexto
│   ├── ferramentas/              #   ferramentas SQL e de busca do agente
│   │   ├── verificar_prazos.py
│   │   ├── checar_honorarios.py
│   │   ├── status_carteira.py
│   │   ├── consultar_banco.py    #     gera SQL dinâmico
│   │   └── buscar_documento.py   #     busca semântica
│   ├── memoria/                  #   janela de contexto e sessões do chat
│   ├── automacoes/               #   automação de alertas de prazo (e-mail)
│   │   ├── verificar_prazos.py   #     grafo linear de busca + envio
│   │   ├── scheduler.py          #     agenda a execução diária (08:00)
│   │   └── email_sender.py       #     envio via Resend
│   └── docs/
│       └── arquitetura.md        #   diagrama do grafo de estados
│
└── fase3_interface/              # FASE 3 — interface Streamlit
    ├── app.py                    #   entrypoint (roteamento das abas)
    ├── requirements.txt          #   dependências enxutas do frontend (sem ML pesado)
    └── app/
        ├── config.py             #     lê API_BASE_URL e API_KEY do ambiente
        ├── pages/                #     uma página por aba
        │   ├── dashboard.py      #       Painel de Consultas
        │   ├── agente.py         #       Agente Jurídico (chat)
        │   ├── adicionar_documento.py  # Adicionar Documento
        │   ├── insights.py       #       Insights do Agente
        │   └── alertas.py        #       Central de Alertas
        ├── components/           #     componentes reusáveis (sidebar, status de conexão)
        └── services/             #     cliente HTTP da API e histórico de conversas
```

---

## Se algo der errado

- **`python` ou `pip` "não é reconhecido" (Windows)?** O Python foi instalado sem marcar "Add Python to PATH". Reinstale marcando essa caixinha, ou tente trocar `python` por `py` nos comandos.
- **Erro ao rodar o `docker compose`?** Confirme que o **Docker Desktop está aberto** (o ícone da baleia precisa estar ativo).
- **O serviço `init` falha com erro de `OPENAI_API_KEY`?** A chave não está no `.env` ou está com espaços/aspas em volta. Confira a linha `OPENAI_API_KEY=sk-...` (sem aspas) e suba de novo com `docker compose up`.
- **Erro de acesso ao Drive (passo 6)?** Confirme que o `service_account.json` está na pasta raiz, que o `DRIVE_FOLDER_ID` no `.env` está correto, e que a equipe liberou o seu acesso à pasta.
- **O comando do Drive (passo 6) não para?** É assim mesmo. Espere a mensagem de "nenhum PDF novo" e aperte `Ctrl + C`.
- **Erro no passo 7 (organizar com a IA)?** Confirme que a `OPENAI_API_KEY` está preenchida no `.env` e que há PDFs em `data/pdfs/`.
- **A API não conecta no banco?** Veja se o banco está ligado com `docker compose ps`.
- **A primeira busca/indexação está demorando muito?** É normal — está baixando o modelo de IA de ~500 MB. Só acontece uma vez.
- **`/clientes/` não mostra nada?** Você pulou o passo 5. Rode `python -m fase1_engenharia.db.seed`.
- **A busca não retorna nada?** Confira se rodou os passos 7 e 8 na ordem (organizar com IA → indexar).
- **O agente retorna "Não foi possível elaborar uma resposta confiável"?** A pergunta pode estar ambígua. Tente ser mais específico, incluindo o nome do cliente ou o número do processo.
- **A interface diz que não conecta na API?** Confirme que a API está no ar (passo 9) e que `API_BASE_URL` no `.env` aponta para ela (`http://localhost:8000` em modo local).
- **Erro de autenticação na automação de alertas?** Confirme que `RESEND_API_KEY` e `EMAIL_FALLBACK` estão preenchidos no `.env`.
- **Quer começar do zero?** Rode `docker compose down -v` e depois `docker compose up --build`. Lembre: o `-v` apaga o banco.
