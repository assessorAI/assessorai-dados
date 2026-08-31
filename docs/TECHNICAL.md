# Especificações técnicas

Este documento descreve a implementação do corpus, dos releases, da API REST
e do servidor MCP. Para começar a usar o serviço, consulte primeiro o
[README](../README.md).

## Arquitetura

```text
crawler JSON ─┐
OCR exports ──┼─> canonicalização ─> GitHub Release ─> PostgreSQL/pgvector
outras fontes ┘        │                    │                   │
                 reconciliação       Parquet/JSONL/CSV      REST + MCP
```

O GitHub Releases é a fonte definitiva dos snapshots. PostgreSQL/pgvector é
somente um índice reconstruível. API e MCP não acessam bancos operacionais do
Assessoraí e não compartilham credenciais de escrita com ele.

## Componentes

- `src/assessorai_dados/canonical.py`: normalização, IDs estáveis,
  proveniência, deduplicação e quarentena.
- `src/assessorai_dados/release.py`: geração dos assets e do manifesto.
- `src/assessorai_dados/validation.py`: checksums, formatos, contagens e guard
  de publicação.
- `src/assessorai_dados/database.py`: migrações, carga e consultas.
- `src/assessorai_dados/api.py`: API REST e montagem do transporte MCP.
- `src/assessorai_dados/mcp_server.py`: ferramentas e recursos MCP.
- `config/sources.json`: política explícita de redistribuição por fonte.
- `migrations/`: schema reconstruível do PostgreSQL/pgvector.

## Modelo canônico

Cada proposição é um registro único. Os principais campos são:

- UUIDv5 estável e chave canônica;
- esfera, UF, município e casa legislativa;
- tipo, número, ano, título e ementa;
- autores, data de apresentação e situação;
- texto integral e método de extração;
- URL oficial e data da coleta;
- SHA-256 do conteúdo;
- lista completa de proveniência.

O schema publicado está em `schemas/proposition.schema.json`. O significado de
cada campo está em `docs/data-dictionary.json` e também acompanha cada release.

### Identidade e determinismo

Quando tipo, número e ano existem, a chave canônica combina casa, tipo, número
e ano. Os fallbacks usam o identificador ou URL da fonte. O UUID é derivado da
chave com um namespace UUIDv5 fixo.

Reprocessar a mesma entrada com a mesma política produz os mesmos IDs e hashes.
Identificadores legados de fontes foram preservados quando necessário para não
alterar IDs já produzidos.

### Reconciliação

Toda entrada termina em exatamente um estado no
`reconciliation.jsonl.zst`:

- `published`: criou uma proposição canônica;
- `deduplicated`: foi incorporada a uma proposição existente;
- `quarantined`: não passou por campos mínimos ou política de redistribuição.

Na fusão, textos e ementas mais completos são preferidos e toda proveniência é
preservada.

## Política de fontes e licença

`config/sources.json` registra por fonte:

- identificador estável e padrões de reconhecimento;
- jurisdição e atribuição;
- URL e descrição da base de redistribuição;
- data e responsável pela revisão;
- status `allowed`, `metadata_only`, `pending` ou `blocked`.

Somente `allowed` e `metadata_only` podem compor releases públicos. Em
`metadata_only`, o pipeline remove o texto integral. Fontes desconhecidas são
criadas como `pending` e ficam bloqueadas por padrão.

A compilação e a normalização são CC BY 4.0. A política atual considera textos
legislativos e demais atos oficiais fora da proteção autoral conforme o art.
8º, IV, da Lei 9.610/1998. A delimitação completa está em
[`DATA-LICENSE.md`](../DATA-LICENSE.md).

## Formato de uma release

Tags usam a data no formato `YYYY.MM.DD`. A release `2026.08.31` contém:

- `manifest.json`: versão, fontes, cobertura e catálogo de assets;
- `propositions--{casa}--{ano}--part-{n}.parquet`;
- `propositions--part-{n}.jsonl.zst`;
- `metadata--part-{n}.csv.zst`;
- `reconciliation.jsonl.zst`;
- `coverage.json`;
- `proposition.schema.json`;
- `data-dictionary.json`;
- `DATA-LICENSE.md`;
- opcionalmente `embeddings-{modelo}.parquet`.

O manifesto contém SHA-256, tamanho e contagem de linhas de cada asset. Ele não
lista o próprio checksum, pois isso criaria uma referência recursiva. Nenhum
asset pode exceder 2 GiB; partições maiores são divididas deterministicamente.

Arquivos brutos, PDFs e OCR intermediário só devem ser adicionados quando sua
redistribuição estiver explicitamente autorizada.

## Construção e validação

No NixOS:

```bash
nix develop
uv sync --extra dev
```

Construção publicável:

```bash
uv run assessorai-data build \
  /caminho/para/crawler \
  /caminho/para/ocr \
  --release 2026.08.31 \
  --output dist/2026.08.31

uv run assessorai-data validate-release \
  dist/2026.08.31 \
  --require-publishable
```

Uma prévia de staging pode usar `--allow-pending`, mas o resultado terá
`publishable=false` e não atravessará o workflow de publicação.

## Publicação

O fluxo usa um draft para evitar exposição parcial:

```bash
uv run assessorai-data upload-draft dist/2026.08.31 \
  --repository assessorAI/assessorai-dados
```

Em seguida, o workflow `Validate and publish dataset release`:

1. baixa todos os assets novamente;
2. verifica formatos, checksums e contagens;
3. exige `publishable=true`;
4. converte o draft em release pública e `latest`.

Código, schemas, manifestos e amostras pequenas ficam no Git. Dados completos
ficam no GitHub Releases. Git LFS não é usado.

## PostgreSQL e pgvector

O índice pode ser reconstruído integralmente a partir de uma release:

```bash
uv run assessorai-data migrate
uv run assessorai-data load-db dist/2026.08.31
```

Tabelas principais:

- `propositions`: registro canônico, `tsvector` e embedding opcional;
- `proposition_sources`: proveniência por fonte;
- `proposition_texts`: páginas do texto integral;
- `dataset_sources`: catálogo de fontes;
- `dataset_releases`: manifestos carregados e versão corrente.

Os índices incluem GIN para full-text em português, filtros relacionais e HNSW
para vetores. O usuário de runtime deve possuir somente `CONNECT`, `USAGE` e
`SELECT`; migrações e cargas devem usar uma credencial separada.

## Busca

A busca aplica, nesta ordem:

1. identificadores e filtros estruturados;
2. full-text search em português;
3. similaridade vetorial quando embeddings e credencial estiverem disponíveis;
4. paginação por cursor opaco.

Filtros disponíveis: casa, UF, município, tipo, ano e autor. Resultados sempre
informam a versão corrente do dataset.

## API REST

O contrato interativo fica em `/docs`. Endpoints:

```text
GET /health
GET /v1/propositions
GET /v1/propositions/{id}
GET /v1/propositions/{id}/text
GET /v1/propositions/{id}/related
GET /v1/sources
GET /v1/datasets/releases
GET /v1/datasets/releases/{version}
GET /v1/datasets/releases/{version}/download/{asset_name}
```

`version` aceita uma tag ou `latest`. O endpoint de download não transmite o
arquivo; devolve a URL permanente ou conveniente do GitHub Release.

## MCP

O servidor usa MCP Streamable HTTP, respostas JSON e sessões stateless. O
endpoint publicado é:

```text
https://api-staging-aa9d.up.railway.app/mcp/
```

Durante a inicialização, cliente e servidor negociam a versão do protocolo e
as capacidades. O cliente chama `tools/list`, apresenta as ferramentas ao
modelo e envia `tools/call` quando o modelo precisa consultar o corpus. O
servidor não executa código fornecido pelo agente e não oferece ferramentas de
escrita.

### Ferramentas

#### `search_propositions`

Parâmetros: `query`, `house`, `state`, `municipality`, `proposition_type`,
`year`, `author`, `limit` e `cursor`. Retorna `items`, `next_cursor` e
`release`.

#### `get_proposition`

Recebe `proposition_id` e retorna o registro canônico com proveniência.

#### `read_proposition_text`

Recebe `proposition_id`, `offset` e `max_chars`. O limite máximo por chamada é
20.000 caracteres. Retorna `next_offset` enquanto houver mais texto.

#### `find_related_propositions`

Recebe `proposition_id` e `limit`. Usa similaridade vetorial quando disponível
e full-text como fallback.

#### `list_sources`

Retorna jurisdição, atribuição, licença e status de redistribuição.

#### `get_dataset_release`

Recebe uma versão ou `latest` e retorna o manifesto carregado.

#### `get_dataset_download`

Recebe `asset_name` e uma versão opcional. Só gera links para releases
publicáveis e devolve diretamente uma URL do GitHub.

### Recursos MCP

Também são expostos recursos somente leitura:

```text
assessorai://datasets/catalog
assessorai://datasets/{version}/manifest
assessorai://propositions/{proposition_id}
```

## Limites e segurança

- acesso público: 60 requisições/minuto por IP;
- chaves opcionais: limite maior configurável;
- chaves são comparadas por hashes SHA-256;
- validação de `Host` e `Origin` no transporte MCP;
- API e MCP são somente leitura;
- banco acessado pela rede privada do Railway;
- releases não podem conter usuários, demandas, auditoria, documentos privados
  ou segredos.

Variáveis relevantes:

```text
DATABASE_URL
GITHUB_DATA_REPOSITORY
PUBLIC_RATE_LIMIT_PER_MINUTE
KEY_RATE_LIMIT_PER_MINUTE
PUBLIC_API_KEY_HASHES
MCP_ALLOWED_HOSTS
MCP_ALLOWED_ORIGINS
OPENAI_API_KEY
OPENAI_EMBEDDING_MODEL
```

## Deploy e branches

- `dev`: desenvolvimento e CI;
- `staging`: Railway e validação integrada;
- `production`: serviço público estável.

O fluxo obrigatório é `dev` → `staging` → `production`. Produção só deve ser
promovida após teste explícito de staging. O serviço usa um projeto Railway
independente do backend do Assessoraí.

O entrypoint do container aplica migrações antes do Uvicorn. O PostgreSQL usa
volume persistente e comunicação privada com a API.

## Verificações

```bash
nix develop --command uv run ruff check .
nix develop --command uv run pytest -q
nix develop --command uv build
```

O CI executa lint, testes unitários, teste integrado em PostgreSQL com pgvector
e build do pacote. O workflow de publicação repete a validação usando os
arquivos já enviados ao GitHub.
