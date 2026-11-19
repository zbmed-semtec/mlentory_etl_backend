"""Content safety decisions survive outside the Elasticsearch index."""

from etl_loaders.content_safety_store import (
    decision_for,
    load_decisions,
    record_decision,
)


def test_missing_store_has_no_decisions(tmp_path):
    assert load_decisions(tmp_path / "missing.json") == {}


def test_record_and_reload_decision(tmp_path):
    path = tmp_path / "moderation" / "content_safety.json"
    record_decision("https://w3id.org/mlentory/mlentory_graph/abc", "inappropriate", path)
    record_decision("https://w3id.org/mlentory/mlentory_graph/abc", "safe", path)
    assert load_decisions(path) == {
        "https://w3id.org/mlentory/mlentory_graph/abc": "safe",
    }


def test_decision_for_checks_each_identifier():
    decisions = {"https://w3id.org/mlentory/mlentory_graph/abc": "inappropriate"}
    assert decision_for(decisions, "other", "https://w3id.org/mlentory/mlentory_graph/abc") == "inappropriate"
    assert decision_for(decisions, "missing") is None
