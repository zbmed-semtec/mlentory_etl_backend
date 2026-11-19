"""Review updates write the notebook and the live search document."""

import pytest
from fastapi import HTTPException

from api.services import content_safety_service as service


class _FakeClient:
    def __init__(self, hits):
        self.hits = hits
        self.updates = []

    def search(self, **_kwargs):
        return {"hits": {"hits": self.hits}}

    def update(self, **kwargs):
        self.updates.append(kwargs)


def test_apply_content_safety_writes_store_and_index(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTENT_SAFETY_TOKEN", raising=False)
    graph_id = "https://w3id.org/mlentory/mlentory_graph/abc"
    client = _FakeClient(
        [
            {
                "_index": "hf_models",
                "_id": graph_id,
                "_source": {"mlentory_id": graph_id, "db_identifier": [graph_id]},
            }
        ]
    )
    path = tmp_path / "content_safety.json"
    result = service.apply_content_safety(client, ["hf_models"], "abc", "inappropriate", path)
    assert result == {"model_id": graph_id, "contentSafety": "inappropriate"}
    assert client.updates[0]["doc"] == {"contentSafety": "inappropriate"}
    assert '"inappropriate"' in path.read_text(encoding="utf-8")


def test_apply_content_safety_missing_model(tmp_path):
    client = _FakeClient([])
    with pytest.raises(LookupError):
        service.apply_content_safety(client, ["hf_models"], "missing", "safe", tmp_path / "none.json")


def test_review_token_rejects_missing_configuration(monkeypatch):
    monkeypatch.delenv("CONTENT_SAFETY_TOKEN", raising=False)
    with pytest.raises(HTTPException) as caught:
        service.require_content_safety_token("anything")
    assert caught.value.status_code == 503


def test_review_token_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("CONTENT_SAFETY_TOKEN", "correct-token")
    with pytest.raises(HTTPException) as caught:
        service.require_content_safety_token("wrong-token")
    assert caught.value.status_code == 401
