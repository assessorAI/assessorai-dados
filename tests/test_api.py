from fastapi.testclient import TestClient

from assessorai_dados.api import app
from assessorai_dados.models import SearchResult


class FakeRepository:
    def current_release(self):
        return "2026.08.31"

    def search(self, filters):
        return SearchResult(
            items=[{"id": "00000000-0000-0000-0000-000000000001", "title": "PL 1/2026"}],
            release="2026.08.31",
        )

    def get_proposition(self, proposition_id):
        return {"id": proposition_id, "title": "PL 1/2026"}

    def read_text(self, proposition_id, offset, max_chars):
        return {
            "id": proposition_id,
            "text": "Art. 1º",
            "offset": offset,
            "next_offset": None,
            "total_length": 7,
        }

    def related(self, proposition_id, limit):
        return []

    def list_sources(self):
        return [{"id": "source"}]

    def list_releases(self):
        return [{"version": "2026.08.31"}]

    def get_release(self, version):
        return {
            "version": "2026.08.31",
            "manifest": {
                "publishable": True,
                "assets": [{"name": "manifest.json", "sha256": "abc"}],
            },
        }


def test_rest_api(monkeypatch):
    fake = FakeRepository()
    monkeypatch.setattr("assessorai_dados.api.get_repository", lambda: fake)
    with TestClient(app) as client:
        health = client.get("/health")
        search = client.get("/v1/propositions", params={"query": "dados"})
        proposition = client.get("/v1/propositions/id-1")
        text = client.get("/v1/propositions/id-1/text", params={"max_chars": 100})
        download = client.get("/v1/datasets/releases/latest/download/manifest.json")
        fake.get_release = lambda version: {
            "version": "2026.08.31",
            "manifest": {"publishable": False, "assets": [{"name": "manifest.json"}]},
        }
        preview_download = client.get(
            "/v1/datasets/releases/latest/download/manifest.json"
        )

    assert health.json()["release"] == "2026.08.31"
    assert search.json()["items"][0]["title"] == "PL 1/2026"
    assert proposition.status_code == 200
    assert text.json()["text"] == "Art. 1º"
    assert download.json()["url"].endswith("/releases/latest/download/manifest.json")
    assert preview_download.status_code == 409
    assert preview_download.json()["detail"] == "release_not_publishable"
