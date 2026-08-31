from mcp import Client

from assessorai_dados.mcp_server import get_dataset_download, mcp


async def test_mcp_advertises_read_only_tools():
    async with Client(mcp) as client:
        result = await client.list_tools()

    names = {tool.name for tool in result.tools}
    assert names == {
        "find_related_propositions",
        "get_dataset_download",
        "get_dataset_release",
        "get_proposition",
        "list_sources",
        "read_proposition_text",
        "search_propositions",
    }


def test_preview_release_cannot_advertise_public_download(monkeypatch):
    class PreviewRepository:
        def get_release(self, version):
            return {"version": "2026.08.31", "manifest": {"publishable": False}}

    monkeypatch.setattr(
        "assessorai_dados.mcp_server.get_repository", lambda: PreviewRepository()
    )

    assert get_dataset_download("manifest.json") == {
        "error": "release_not_publishable",
        "version": "2026.08.31",
    }


def test_manifest_download_does_not_require_self_referential_asset(monkeypatch):
    class PublishedRepository:
        def get_release(self, version):
            return {
                "version": "2026.08.31",
                "manifest": {"publishable": True, "assets": []},
            }

    monkeypatch.setattr(
        "assessorai_dados.mcp_server.get_repository", lambda: PublishedRepository()
    )

    result = get_dataset_download("manifest.json")
    assert result["url"].endswith("/releases/latest/download/manifest.json")
