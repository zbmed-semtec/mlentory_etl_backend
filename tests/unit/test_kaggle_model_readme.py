"""Tests for Kaggle model README selection, fallback docs, and mapping."""

from __future__ import annotations

import unittest

from etl.assets.kaggle_transformation import normalize_kaggle_instance
from etl_extractors.kaggle.model_readme import (
    compose_model_documentation,
    select_readme_file,
    split_instance_ref,
)


class TestSelectReadmeFile(unittest.TestCase):
    def test_picks_top_level_readme(self):
        picked = select_readme_file(
            [
                {"name": "weights.bin", "size": 99},
                {"name": "README.md", "size": 1200},
                {"name": "docs/README.md", "size": 400},
            ]
        )
        assert picked == {"name": "README.md", "size": 1200}

    def test_case_insensitive_and_nested_fallback(self):
        picked = select_readme_file([{"name": "Notes/ReadMe.md", "size": 80}])
        assert picked["name"] == "Notes/ReadMe.md"

    def test_skips_oversized_file(self):
        picked = select_readme_file(
            [{"name": "README.md", "size": 9_000_000}],
            max_bytes=1000,
        )
        assert picked is None

    def test_empty_list(self):
        assert select_readme_file([]) is None


class TestComposeModelDocumentation(unittest.TestCase):
    def test_readme_wins(self):
        text = compose_model_documentation(
            parent_card="parent card",
            overview="overview",
            usage="usage",
            readme_markdown="# Model README\n\nFP8 notes",
        )
        assert text.startswith("# Model README")
        assert "parent card" not in text

    def test_fallback_joins_parent_and_extras(self):
        text = compose_model_documentation(
            parent_card="Shared card",
            overview="Variation overview",
            usage="pip install",
        )
        assert text == "Shared card\n\nVariation overview\n\npip install"

    def test_skips_overview_already_in_parent(self):
        text = compose_model_documentation(
            parent_card="Card with Variation overview inside",
            overview="Variation overview",
            usage="extra usage",
        )
        assert text == "Card with Variation overview inside\n\nextra usage"

    def test_empty(self):
        assert compose_model_documentation() == ""


class TestSplitInstanceRef(unittest.TestCase):
    def test_plain_ref(self):
        assert split_instance_ref("google/bert/TensorFlow2/default") == (
            "google",
            "bert",
            "TensorFlow2",
            "default",
        )

    def test_url_path(self):
        assert split_instance_ref(
            "https://www.kaggle.com/models/google/bert/TensorFlow2/default"
        ) == ("google", "bert", "TensorFlow2", "default")

    def test_invalid(self):
        assert split_instance_ref("google/bert") is None


class TestNormalizeKaggleInstanceDocs(unittest.TestCase):
    def _base(self, **overrides):
        rec = {
            "instanceId": "owner/model/PyTorch/default",
            "mlentory_id": "https://w3id.org/mlentory/mlentory_graph/abc",
            "parent_mlentory_id": "https://w3id.org/mlentory/mlentory_graph/parent",
            "url": "https://www.kaggle.com/models/owner/model/PyTorch/default",
            "name": "default",
            "sharedBy": "owner",
            "description": "short overview",
            "usage": "example use",
            "parent_description": "Parent model card",
            "frameworkName": "PyTorch",
            "license": "Apache 2.0",
            "contentSize": "12",
        }
        rec.update(overrides)
        return rec

    def test_readme_fills_description_and_abstract(self):
        mapped = normalize_kaggle_instance(
            self._base(readme_markdown="# Combined card and extras")
        )
        assert mapped["description"] == "# Combined card and extras"
        assert mapped["abstract"] == "# Combined card and extras"
        assert mapped["extraction_metadata"]["description"]["source_field"] == (
            "model README.md"
        )
        assert mapped["usageInstructions"] == "example use"

    def test_fallback_without_readme(self):
        mapped = normalize_kaggle_instance(self._base())
        assert mapped["description"] == (
            "Parent model card\n\nshort overview\n\nexample use"
        )
        assert mapped["abstract"] == mapped["description"]
        assert mapped["extraction_metadata"]["abstract"]["source_field"] == (
            "parent description, overview, usage"
        )

    def test_parent_container_is_not_base_model(self):
        mapped = normalize_kaggle_instance(self._base())
        assert mapped["baseModel"] == []


class TestInheritParentCatalogFields(unittest.TestCase):
    def test_copies_keywords_source_inlanguage(self):
        from etl.assets.kaggle_transformation import inherit_parent_catalog_fields

        mapped = {"extraction_metadata": {}}
        inherit_parent_catalog_fields(
            mapped,
            {
                "keywords": ["kw-1"],
                "source": "src-1",
                "inLanguage": ["lang-1"],
                "dateCreated": "2024-01-01",
                "extraction_metadata": {
                    "keywords": {"extraction_method": "Kaggle_models_endpoint"},
                    "source": {"extraction_method": "Kaggle_catalog_website"},
                },
            },
        )
        assert mapped["keywords"] == ["kw-1"]
        assert mapped["source"] == "src-1"
        assert mapped["inLanguage"] == ["lang-1"]
        assert mapped["dateCreated"] == "2024-01-01"
        assert mapped["extraction_metadata"]["keywords"]["extraction_method"] == (
            "Kaggle_models_endpoint"
        )

    def test_does_not_overwrite_existing_dates(self):
        from etl.assets.kaggle_transformation import inherit_parent_catalog_fields

        mapped = {"dateCreated": "2020-01-01", "extraction_metadata": {}}
        inherit_parent_catalog_fields(
            mapped, {"dateCreated": "2024-01-01"}
        )
        assert mapped["dateCreated"] == "2020-01-01"
