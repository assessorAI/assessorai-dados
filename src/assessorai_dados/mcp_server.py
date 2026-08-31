from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from .models import SearchFilters
from .service import get_repository
from .settings import get_settings

mcp = MCPServer(
    "AssessorAI Dados Legislativos",
    instructions=(
        "Consulta somente leitura ao corpus público de proposições legislativas brasileiras. "
        "Sempre preserve id, versão do dataset e URLs de fonte ao citar resultados."
    ),
)


def _download_url(version: str, asset_name: str) -> str:
    repository = get_settings().github_data_repository
    if version == "latest":
        return f"https://github.com/{repository}/releases/latest/download/{asset_name}"
    return f"https://github.com/{repository}/releases/download/{version}/{asset_name}"


@mcp.tool()
def search_propositions(
    query: str | None = None,
    house: str | None = None,
    state: str | None = None,
    municipality: str | None = None,
    proposition_type: str | None = None,
    year: int | None = None,
    author: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Search propositions using identifiers, text, semantic similarity and filters."""
    result = get_repository().search(
        SearchFilters(
            query=query,
            house=house,
            state=state,
            municipality=municipality,
            proposition_type=proposition_type,
            year=year,
            author=author,
            limit=limit,
            cursor=cursor,
        )
    )
    return result.model_dump(mode="json")


@mcp.tool()
def get_proposition(proposition_id: str) -> dict[str, Any]:
    """Get canonical metadata and provenance for one proposition UUID."""
    value = get_repository().get_proposition(proposition_id)
    return value or {"error": "not_found", "id": proposition_id}


@mcp.tool()
def read_proposition_text(
    proposition_id: str, offset: int = 0, max_chars: int = 20_000
) -> dict[str, Any]:
    """Read a bounded page of a proposition's full text."""
    value = get_repository().read_text(proposition_id, offset, max_chars)
    return value or {"error": "not_found", "id": proposition_id}


@mcp.tool()
def find_related_propositions(proposition_id: str, limit: int = 10) -> dict[str, Any]:
    """Find propositions related by embeddings or Portuguese full-text similarity."""
    return {"id": proposition_id, "items": get_repository().related(proposition_id, limit)}


@mcp.tool()
def list_sources() -> dict[str, Any]:
    """List data sources, jurisdictions, licenses and redistribution status."""
    return {"sources": get_repository().list_sources()}


@mcp.tool()
def get_dataset_release(version: str = "latest") -> dict[str, Any]:
    """Get a release manifest and its coverage metadata."""
    value = get_repository().get_release(version)
    return value or {"error": "not_found", "version": version}


@mcp.tool()
def get_dataset_download(asset_name: str, version: str = "latest") -> dict[str, Any]:
    """Get a public GitHub Release URL for a named dataset asset."""
    release = get_repository().get_release(version)
    if not release:
        return {"error": "release_not_found", "version": version}
    manifest = release["manifest"]
    assets = {item["name"]: item for item in manifest.get("assets", [])}
    if asset_name not in assets:
        return {"error": "asset_not_found", "asset_name": asset_name, "available": sorted(assets)}
    resolved_version = "latest" if version == "latest" else release["version"]
    return {**assets[asset_name], "url": _download_url(resolved_version, asset_name)}


@mcp.resource("assessorai://datasets/catalog")
def dataset_catalog() -> dict[str, Any]:
    """Catalog of published dataset releases."""
    return {"releases": get_repository().list_releases()}


@mcp.resource("assessorai://datasets/{version}/manifest")
def dataset_manifest(version: str) -> dict[str, Any]:
    """Manifest for a specific dataset release."""
    return get_dataset_release(version)


@mcp.resource("assessorai://propositions/{proposition_id}")
def proposition_resource(proposition_id: str) -> dict[str, Any]:
    """Canonical proposition metadata resource."""
    return get_proposition(proposition_id)
