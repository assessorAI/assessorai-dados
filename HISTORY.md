# Histórico

## 2026-08-31T14:00:25Z

- Criado o projeto independente de dados legislativos, com pipeline canônico,
  releases reprodutíveis, API REST, MCP somente leitura e publicação por
  GitHub Releases.
- A publicação de dados reais permanece condicionada ao cadastro da licença e
  do status de redistribuição de cada fonte.
- Validada uma prévia real com 26.816 proposições únicas, 3.256 duplicatas
  reconciliadas, 18 casas legislativas, 121 assets e 65,6 MB. Todas as 18
  fontes continuam marcadas como `pending`, e o guard de publicação bloqueou a
  promoção como esperado.
- Validada a reconstrução do índice em PostgreSQL 17 com pgvector, incluindo
  migrações, carga, busca, paginação de texto, fontes e resolução de releases.

## 2026-08-31T14:15:22Z

- Preparado o ambiente isolado de staging no Railway, com serviço de API,
  PostgreSQL e domínio público próprios, sem alterar o Assessoraí existente.
- O container agora normaliza URLs PostgreSQL do Railway para o driver
  Psycopg 3 e aplica migrações pela rede privada antes de iniciar a API.
- Migrada a configuração de deploy para Railway Config as Code e validado o
  novo entrypoint com lint, testes e build local do container.
- O primeiro smoke test de staging detectou que o CLI instalado resolvia um
  diretório de migrações vazio. O entrypoint passou a usar o caminho absoluto
  do container, e a ausência de SQLs agora interrompe o deploy explicitamente.
- Carregada no índice isolado de staging a prévia validada com 26.816
  proposições. REST e MCP recusam links de download para releases ainda não
  publicáveis, evitando anunciar assets inexistentes ou sem licença aprovada.
- Após os smoke tests, a carga temporária foi removida do PostgreSQL público de
  staging porque todas as fontes continuam com redistribuição pendente. Os
  assets validados permanecem locais e permitem reconstruir o índice.

## 2026-08-31T15:00:00Z

- Aprovada editorialmente a redistribuição dos textos legislativos das 18
  fontes com fundamento no art. 8º, IV, da Lei 9.610/1998, mantendo atribuição
  aos órgãos e excluindo logotipos, elementos gráficos e obras de terceiros.
- Completado o registro das 12 fontes antes descobertas dinamicamente para que
  futuros releases não dependam de políticas implícitas.

## 2026-08-31T15:09:36Z

- Publicado no GitHub Releases o snapshot `2026.08.31` com 26.816 proposições,
  18 fontes, 122 arquivos públicos e 66,8 MB, após validação independente pelo
  workflow de publicação.
- O release público foi carregado no PostgreSQL/pgvector de staging e ficou
  disponível para consulta pela API REST e pelo MCP.
- REST e MCP passaram a resolver `manifest.json` explicitamente, já que o
  manifesto não pode conter o próprio checksum sem criar uma referência
  recursiva.
