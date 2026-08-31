from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from mcp.server.transport_security import TransportSecuritySettings

from .mcp_server import mcp
from .models import SearchFilters
from .rate_limit import RateLimitMiddleware
from .service import get_repository
from .settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="AssessorAI Dados Legislativos",
    description="API e MCP públicos para proposições legislativas brasileiras.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(RateLimitMiddleware)


@app.get("/health")
def health():
    return {"status": "ok", "release": get_repository().current_release()}


@app.get("/v1/propositions")
def search_propositions(
    query: str | None = None,
    house: str | None = None,
    state: str | None = None,
    municipality: str | None = None,
    proposition_type: Annotated[str | None, Query(alias="type")] = None,
    year: int | None = None,
    author: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
):
    try:
        return get_repository().search(
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/propositions/{proposition_id}")
def get_proposition(proposition_id: str):
    value = get_repository().get_proposition(proposition_id)
    if not value:
        raise HTTPException(status_code=404, detail="proposition_not_found")
    return value


@app.get("/v1/propositions/{proposition_id}/text")
def get_proposition_text(
    proposition_id: str,
    offset: Annotated[int, Query(ge=0)] = 0,
    max_chars: Annotated[int, Query(ge=1, le=20_000)] = 20_000,
):
    value = get_repository().read_text(proposition_id, offset, max_chars)
    if not value:
        raise HTTPException(status_code=404, detail="proposition_not_found")
    return value


@app.get("/v1/propositions/{proposition_id}/related")
def get_related_propositions(proposition_id: str, limit: Annotated[int, Query(ge=1, le=50)] = 10):
    return {"id": proposition_id, "items": get_repository().related(proposition_id, limit)}


@app.get("/v1/sources")
def list_sources():
    return {"sources": get_repository().list_sources()}


@app.get("/v1/datasets/releases")
def list_releases():
    return {"releases": get_repository().list_releases()}


@app.get("/v1/datasets/releases/{version}")
def get_release(version: str):
    value = get_repository().get_release(version)
    if not value:
        raise HTTPException(status_code=404, detail="release_not_found")
    return value


@app.get("/v1/datasets/releases/{version}/download/{asset_name}")
def get_release_download(version: str, asset_name: str):
    release = get_repository().get_release(version)
    if not release:
        raise HTTPException(status_code=404, detail="release_not_found")
    if not release["manifest"].get("publishable", False):
        raise HTTPException(status_code=409, detail="release_not_publishable")
    assets = {item["name"]: item for item in release["manifest"].get("assets", [])}
    if asset_name not in assets:
        raise HTTPException(status_code=404, detail="asset_not_found")
    repository = get_settings().github_data_repository
    tag = "latest" if version == "latest" else release["version"]
    prefix = "releases/latest/download" if tag == "latest" else f"releases/download/{tag}"
    return {**assets[asset_name], "url": f"https://github.com/{repository}/{prefix}/{asset_name}"}


settings = get_settings()
app.mount(
    "/mcp",
    mcp.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=settings.allowed_mcp_hosts,
            allowed_origins=settings.allowed_mcp_origins,
        ),
    ),
)
