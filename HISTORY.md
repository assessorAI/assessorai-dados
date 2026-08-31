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
