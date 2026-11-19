"""Search and detail lookups hide models explicitly marked inappropriate."""

from api.services.elasticsearch_service import ElasticsearchService
from api.services.faceted_search import FacetedSearchMixin


def _gate():
    return FacetedSearchMixin._minimum_metadata_bool_filter(None)


def test_inappropriate_models_are_excluded():
    must_not = _gate()["bool"]["must_not"]
    assert {"term": {"contentSafety": "inappropriate"}} in must_not


def test_missing_content_safety_is_not_required():
    must = _gate()["bool"]["must"]
    assert {"exists": {"field": "contentSafety"}} not in must


class _FakeElasticsearch:
    def __init__(self, source):
        self.source = source

    def search(self, **_kwargs):
        return {
            "hits": {
                "total": {"value": 1},
                "hits": [{"_source": self.source}],
            }
        }


def _service(source):
    service = ElasticsearchService.__new__(ElasticsearchService)
    service.client = _FakeElasticsearch(source)
    service._model_search_indices = lambda: ["hf_models"]
    return service


def test_detail_lookup_hides_inappropriate_model():
    source = {
        "db_identifier": ["https://w3id.org/mlentory/mlentory_graph/abc"],
        "name": "hidden",
        "contentSafety": "inappropriate",
    }
    assert _service(source).get_model_by_id("abc") is None


def test_detail_lookup_returns_model_without_content_safety():
    source = {
        "db_identifier": ["https://w3id.org/mlentory/mlentory_graph/abc"],
        "name": "visible",
        "description": "ok",
        "shared_by": "someone",
        "license": "mit",
        "ml_tasks": [],
        "keywords": [],
    }
    model = _service(source).get_model_by_id("abc")
    assert model is not None
    assert model.name == "visible"
