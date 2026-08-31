# AssessorAI Dados Legislativos

Corpus, API REST e servidor MCP públicos para proposições legislativas
brasileiras. O GitHub Releases é a fonte dos snapshots imutáveis; o PostgreSQL
com pgvector é um índice reconstruível usado para consultas.

## Arquitetura

```text
crawler JSON ─┐
OCR exports ──┼─> canonicalização ─> GitHub Release ─> PostgreSQL/pgvector
pgvector dump ┘        │                    │                   │
                  reconciliação       Parquet/JSONL/CSV      REST + MCP
```

O pipeline nunca lê tabelas operacionais de usuários, mandatos, demandas ou
auditoria. Cada entrada termina classificada como `published`, `deduplicated`
ou `quarantined` no arquivo `reconciliation.jsonl.zst`.

## Ambiente local no NixOS

```bash
nix develop
uv sync --extra dev
```

## Construir uma prévia local

Fontes novas começam com `redistribution_status=pending`. A opção
`--allow-pending` existe somente para validação em staging e não autoriza a
publicação. As fontes legislativas atualmente cadastradas foram revisadas sob
o art. 8º, IV, da Lei 9.610/1998, que exclui atos oficiais da proteção autoral.

```bash
uv run assessorai-data build \
  /home/markun/devel/legisla/assessorai-pdftomd/data \
  /home/markun/devel/legisla/assessorai-crawler/storage/output \
  --release 2026.08.31 \
  --output dist/2026.08.31 \
  --allow-pending

uv run assessorai-data validate-release dist/2026.08.31
```

Para um release publicável, atualize `config/sources.json` com a base de
redistribuição, atribuição, revisor e um status explícito `allowed` ou
`metadata_only`, depois construa sem `--allow-pending`.

## Publicar no GitHub Releases

1. Gere e valide o diretório do release.
2. Crie um draft e envie os assets:

   ```bash
   uv run assessorai-data upload-draft dist/2026.08.31 \
     --repository assessorAI/assessorai-dados
   ```

3. Execute manualmente o workflow `Validate and publish dataset release` com a
   tag. O workflow baixa novamente os assets, valida formatos, contagens e
   checksums e somente então publica o release como `latest`.

Assets maiores devem ser particionados para permanecer abaixo de 2 GiB. Dados
grandes não são commitados e Git LFS não é usado.

## Banco de busca

```bash
uv run assessorai-data migrate
uv run assessorai-data load-db dist/2026.08.31
```

A aplicação utiliza `DATABASE_URL`. O usuário usado pela API/MCP em produção
deve possuir apenas `CONNECT`, `USAGE` no schema e `SELECT` nas tabelas.
O entrypoint do container aplica migrações antes de iniciar a API; em produção,
use uma credencial de migração no deploy e troque a credencial de runtime por
um usuário somente leitura após a carga do release.

## API REST

```bash
uv run uvicorn assessorai_dados.api:app --reload
```

Principais endpoints:

- `GET /v1/propositions`
- `GET /v1/propositions/{id}`
- `GET /v1/propositions/{id}/text`
- `GET /v1/propositions/{id}/related`
- `GET /v1/sources`
- `GET /v1/datasets/releases`
- `GET /v1/datasets/releases/{version}`

Consultas públicas recebem 60 requisições por minuto por IP. Chaves opcionais
são enviadas em `X-API-Key`; o ambiente armazena somente seus hashes SHA-256 em
`PUBLIC_API_KEY_HASHES`.

## MCP

O endpoint Streamable HTTP fica em `http://localhost:8000/mcp`. Ferramentas:

- `search_propositions`
- `get_proposition`
- `read_proposition_text`
- `find_related_propositions`
- `list_sources`
- `get_dataset_release`
- `get_dataset_download`

Exemplo de configuração:

```json
{
  "mcpServers": {
    "assessorai-dados": {
      "type": "http",
      "url": "https://SEU-DOMINIO/mcp"
    }
  }
}
```

Resultados carregam o UUID, a versão do dataset, proveniência e URLs oficiais
para que agentes possam citar a fonte original.

## Branches e deploy

- `dev`: desenvolvimento.
- `staging`: validação Railway e releases de prévia.
- `production`: serviço público estável.

Não promova `staging` para `production` sem teste explícito do ambiente de
staging. O serviço deve usar um projeto/serviço Railway separado do backend do
Assessoraí.
