# AssessorAI Dados Legislativos

Dados abertos de proposições legislativas brasileiras para pesquisadores,
desenvolvedores e agentes de IA.

## Como usar

Escolha a interface mais adequada:

| Quero... | Use |
|---|---|
| conectar um agente de IA | MCP: `https://api-staging-aa9d.up.railway.app/mcp/` |
| pesquisar pela web ou por código | [API REST e Swagger](https://api-staging-aa9d.up.railway.app/docs) |
| analisar o corpus completo | [GitHub Release mais recente](https://github.com/assessorAI/assessorai-dados/releases/latest) |
| entender arquitetura e formatos | [Especificações técnicas](docs/TECHNICAL.md) |

O acesso é público e somente leitura. Não é necessário fornecer credenciais
para o uso normal.

### Conectar um agente pelo MCP

Adicione este servidor à configuração de um cliente compatível com MCP
Streamable HTTP:

```json
{
  "mcpServers": {
    "assessorai-dados": {
      "type": "http",
      "url": "https://api-staging-aa9d.up.railway.app/mcp/"
    }
  }
}
```

Depois de conectado, o agente passa a enxergar sete ferramentas:

| Ferramenta | Para que serve |
|---|---|
| `search_propositions` | busca por texto, identificador, casa, localidade, tipo, ano ou autor |
| `get_proposition` | retorna metadados e proveniência de uma proposição |
| `read_proposition_text` | lê o texto integral em páginas, sem estourar o contexto do agente |
| `find_related_propositions` | encontra proposições relacionadas |
| `list_sources` | lista casas legislativas, atribuição e situação de redistribuição |
| `get_dataset_release` | retorna versão, cobertura e manifesto do dataset |
| `get_dataset_download` | produz o link público de um arquivo no GitHub Releases |

Exemplos de pedidos que podem ser feitos ao agente:

```text
Encontre projetos de lei sobre dados abertos apresentados em 2024.

Leia o texto do projeto encontrado e me mostre a URL oficial e a versão do dataset.

Quais proposições são relacionadas a este UUID?

Me dê o link do JSONL completo da release mais recente.
```

O fluxo é simples: o agente escolhe uma ferramenta, o MCP consulta o índice
PostgreSQL/pgvector e devolve dados estruturados. Textos longos são paginados.
Arquivos completos não passam pelo servidor: `get_dataset_download` aponta
diretamente para os assets públicos e imutáveis no GitHub.

### Baixar todos os dados

Release atual: [`2026.08.31`](https://github.com/assessorAI/assessorai-dados/releases/tag/2026.08.31),
com 26.816 proposições de 18 fontes.

```bash
# Manifesto, cobertura, fontes e checksums
curl -L -o manifest.json \
  https://github.com/assessorAI/assessorai-dados/releases/latest/download/manifest.json

# Corpus canônico completo em JSON Lines + Zstandard
curl -L -o propositions.jsonl.zst \
  https://github.com/assessorAI/assessorai-dados/releases/latest/download/propositions--part-0000.jsonl.zst

# Metadados tabulares
curl -L -o metadata.csv.zst \
  https://github.com/assessorAI/assessorai-dados/releases/latest/download/metadata--part-0000.csv.zst
```

Os arquivos Parquet são separados deterministicamente por casa e ano e podem
ser baixados na página da release. Comece pelo `manifest.json`: ele contém o
SHA-256, tamanho, formato e número de linhas de cada asset.

### Consultar pela API REST

Busca textual com filtros:

```bash
curl --get 'https://api-staging-aa9d.up.railway.app/v1/propositions' \
  --data-urlencode 'query=dados abertos' \
  --data-urlencode 'year=2024' \
  --data-urlencode 'limit=10'
```

Outros pontos de entrada úteis:

```text
GET /v1/propositions/{id}
GET /v1/propositions/{id}/text?offset=0&max_chars=20000
GET /v1/propositions/{id}/related
GET /v1/sources
GET /v1/datasets/releases
GET /v1/datasets/releases/latest
GET /v1/datasets/releases/latest/download/{asset_name}
```

A paginação de buscas usa `next_cursor`. O texto integral usa `offset` e
`next_offset`. Respostas incluem a versão do dataset e preservam URLs oficiais
e proveniência.

### Limites e licença

- Acesso público: 60 chamadas por minuto por IP.
- Chaves opcionais podem receber limites maiores.
- A compilação é distribuída sob CC BY 4.0.
- Textos legislativos e atos oficiais são tratados conforme o art. 8º, IV, da
  [Lei 9.610/1998](https://www.planalto.gov.br/ccivil_03/leis/l9610.htm).
- Logotipos, fotografias, elementos gráficos e obras de terceiros não fazem
  parte do corpus redistribuído.

Para schemas, construção de releases, busca híbrida, banco, segurança,
variáveis de ambiente e deploy, consulte as
[especificações técnicas](docs/TECHNICAL.md).
