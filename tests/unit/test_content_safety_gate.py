"""Search gate hides models explicitly marked inappropriate."""

from api.services.faceted_search import FacetedSearchMixin


def _gate():
    return FacetedSearchMixin._minimum_metadata_bool_filter(None)


def test_inappropriate_models_are_excluded():
    must_not = _gate()["bool"]["must_not"]
    assert {"term": {"contentSafety": "inappropriate"}} in must_not


def test_missing_content_safety_is_not_required():
    must = _gate()["bool"]["must"]
    assert {"exists": {"field": "contentSafety"}} not in must
