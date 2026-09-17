"""Tests for Kaggle variation catalog names."""

from __future__ import annotations

import unittest

from etl.assets.kaggle_transformation import normalize_kaggle_instance
from etl_extractors.kaggle.clients.instances_client import KaggleInstancesClient


class TestDisplayName(unittest.TestCase):
    def test_distinctive_slug_includes_parent_framework_and_variation(self):
        assert KaggleInstancesClient._display_name(
            "mini", "Phi-3", "PyTorch"
        ) == "Phi-3 (PyTorch · mini)"

    def test_generic_default_omits_slug(self):
        assert KaggleInstancesClient._display_name(
            "default", "BERT", "TensorFlow2"
        ) == "BERT (TensorFlow2)"

    def test_generic_one_omits_slug(self):
        assert KaggleInstancesClient._display_name("1", "BERT", "Keras") == (
            "BERT (Keras)"
        )

    def test_generic_check_is_case_insensitive(self):
        assert KaggleInstancesClient._display_name(
            "DEFAULT", "BERT", "PyTorch"
        ) == "BERT (PyTorch)"

    def test_base_slug_is_kept(self):
        assert KaggleInstancesClient._display_name(
            "base", "Gemma 2", "PyTorch"
        ) == "Gemma 2 (PyTorch · base)"

    def test_missing_parent_keeps_framework_and_slug(self):
        assert KaggleInstancesClient._display_name("mini", "", "PyTorch") == (
            "PyTorch · mini"
        )

    def test_missing_framework_keeps_parent_and_slug(self):
        assert KaggleInstancesClient._display_name("mini", "Phi-3", "") == (
            "Phi-3 (mini)"
        )


class TestFetchInstanceNames(unittest.TestCase):
    def test_names_land_on_extracted_rows(self):
        client = KaggleInstancesClient({"data": [], "timestamp": "2026-01-01"})
        rows = client.fetch_instances_metadata(
            {
                "ref": "microsoft/phi-3",
                "title": "Phi-3",
                "description": "card",
                "author": "Microsoft",
                "instances": [
                    {
                        "framework": "pyTorch",
                        "slug": "mini",
                        "url": (
                            "https://www.kaggle.com/models/microsoft/"
                            "phi-3/PyTorch/mini"
                        ),
                    },
                    {
                        "framework": "tensorFlow2",
                        "slug": "default",
                        "url": (
                            "https://www.kaggle.com/models/microsoft/"
                            "phi-3/TensorFlow2/default"
                        ),
                    },
                ],
            }
        )
        names = {row["slug"]: row["name"] for row in rows}
        assert names["mini"] == "Phi-3 (PyTorch · mini)"
        assert names["default"] == "Phi-3 (TensorFlow2)"
        assert rows[1]["slug"] == "default"


class TestNormalizeKeepsDisplayName(unittest.TestCase):
    def test_passes_through_composed_name(self):
        mapped = normalize_kaggle_instance(
            {
                "instanceId": "microsoft/phi-3/PyTorch/mini",
                "mlentory_id": "https://w3id.org/mlentory/mlentory_graph/abc",
                "url": "https://www.kaggle.com/models/microsoft/phi-3/PyTorch/mini",
                "name": "Phi-3 (PyTorch · mini)",
                "sharedBy": "Microsoft",
                "frameworkName": "PyTorch",
            }
        )
        assert mapped["name"] == "Phi-3 (PyTorch · mini)"
        assert mapped["extraction_metadata"]["name"]["source_field"] == (
            "title, framework, slug"
        )


class TestNormalizeKaggleSource(unittest.TestCase):
    def test_source_is_kaggle_website_entity(self):
        from etl_extractors.kaggle.kaggle_helper import KaggleHelper

        mapped = normalize_kaggle_instance(
            {
                "instanceId": "microsoft/phi-3/PyTorch/mini",
                "mlentory_id": "https://w3id.org/mlentory/mlentory_graph/abc",
                "url": "https://www.kaggle.com/models/microsoft/phi-3/PyTorch/mini",
                "name": "Phi-3 (PyTorch · mini)",
                "frameworkName": "PyTorch",
            }
        )
        catalog = KaggleHelper.raw_kaggle_catalog_website_records()[0]
        assert mapped["source"] == KaggleHelper.catalog_website_iri()
        assert mapped["source"] == catalog["https://schema.org/identifier"][0]
        assert catalog["https://schema.org/name"] == "Kaggle"
        assert catalog["https://schema.org/url"] == "https://www.kaggle.com/models"
        assert mapped["extraction_metadata"]["source"]["extraction_method"] == (
            "Kaggle_catalog_website"
        )

    def test_merge_sets_source_when_linking_omits_it(self):
        from etl.assets.kaggle_transformation import merge_kaggle_partial_schemas
        from etl_extractors.kaggle.kaggle_helper import KaggleHelper

        merged = merge_kaggle_partial_schemas(
            basic_by_id={"owner/model": {"name": "Model"}},
            entity_linking_data={"owner/model": {}},
            all_model_ids=["owner/model"],
        )
        assert len(merged) == 1
        assert merged[0][1]["source"] == KaggleHelper.catalog_website_iri()
