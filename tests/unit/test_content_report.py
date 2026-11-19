"""Visitor reports are stored and do not change the safety mark."""

import json

import pytest

from api.services.content_report_service import accept_content_report, submit_content_report


class _FakeClient:
    def __init__(self, hits):
        self.hits = hits
        self.updates = []

    def search(self, **_kwargs):
        return {"hits": {"hits": self.hits}}

    def update(self, **kwargs):
        self.updates.append(kwargs)


def _hit():
    graph_id = "https://w3id.org/mlentory/mlentory_graph/abc"
    return {
        "_index": "hf_models",
        "_id": graph_id,
        "_source": {"mlentory_id": graph_id, "db_identifier": [graph_id]},
    }


def test_report_is_saved_without_changing_the_model(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPORTS_REPO", raising=False)
    monkeypatch.delenv("GITHUB_REPORTS_TOKEN", raising=False)
    client = _FakeClient([_hit()])
    result = submit_content_report(
        client,
        ["hf_models"],
        "abc",
        "https://mlentory.example/models/abc",
        "This page shows an inappropriate image",
        tmp_path,
    )
    saved = json.loads((tmp_path / f"{result['report_id']}.json").read_text(encoding="utf-8"))
    assert saved["model_id"] == "https://w3id.org/mlentory/mlentory_graph/abc"
    assert saved["reason"] == "This page shows an inappropriate image"
    assert result["status"] == "received"
    assert result["github_issue"] is None
    assert client.updates == []


def test_report_requires_a_reason(tmp_path):
    client = _FakeClient([_hit()])
    with pytest.raises(ValueError):
        submit_content_report(client, ["hf_models"], "abc", "https://example.test/m", "  ", tmp_path)


def test_accepting_a_report_hides_the_model(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPORTS_TOKEN", raising=False)
    client = _FakeClient([_hit()])
    created = submit_content_report(
        client,
        ["hf_models"],
        "abc",
        "https://mlentory.example/models/abc",
        "inappropriate image",
        tmp_path,
    )
    accepted = accept_content_report(
        client,
        ["hf_models"],
        created["report_id"],
        tmp_path,
        tmp_path / "decisions.json",
    )
    saved = json.loads((tmp_path / f"{created['report_id']}.json").read_text(encoding="utf-8"))
    assert accepted["status"] == "accepted"
    assert accepted["contentSafety"] == "inappropriate"
    assert saved["status"] == "accepted"
    assert client.updates[-1]["doc"] == {"contentSafety": "inappropriate"}


def test_report_for_missing_model(tmp_path):
    client = _FakeClient([])
    with pytest.raises(LookupError):
        submit_content_report(
            client,
            ["hf_models"],
            "missing",
            "https://example.test/missing",
            "cannot find it",
            tmp_path,
        )
