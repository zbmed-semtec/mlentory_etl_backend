"""Unit tests for AI4Life MLModel transformation."""

from unittest.mock import patch

from etl_extractors.ai4life.ai4life_helper import AI4LifeHelper
from etl_transformers.ai4life.transform_mlmodel import map_ai4life_basic_properties


class TestMapAI4LifeBasicProperties:
    @patch.object(AI4LifeHelper, "resolve_abstract_content")
    def test_maps_abstract_from_documentation_content(self, mock_resolve_abstract):
        mock_resolve_abstract.return_value = "# 2D UNETR for mitochondria segmentation in EM"
        raw_model = {
            "modelId": "good-microbe",
            "mlentory_id": "https://w3id.org/mlentory/mlentory_graph/model/good-microbe",
            "url": "https://bioimage.io/#/artifacts/good-microbe",
            "name": "good-microbe",
            "sharedBy": "Daniel Franco-Barranco",
            "author": '[{"name": "Daniel Franco-Barranco"}]',
            "modelArchitecture": "UNETR",
            "intendedUse": "Mitochondria segmentation for electron microscopy.",
            "dateCreated": "2024-01-01",
            "dateModified": "2024-01-02",
            "datePublished": "2024-01-01",
            "readme_file": (
                "https://hypha.aicell.io/bioimage-io/artifacts/good-microbe/files/documentation.md"
            ),
            "documentation_content": "# 2D UNETR for mitochondria segmentation in EM",
        }

        result = map_ai4life_basic_properties(raw_model)

        assert result["abstract"] == "# 2D UNETR for mitochondria segmentation in EM"
        assert result["readme"] == (
            "https://hypha.aicell.io/bioimage-io/artifacts/good-microbe/files/documentation.md"
        )
        assert result["description"] == "Mitochondria segmentation for electron microscopy."
        assert result["extraction_metadata"]["abstract"].source_field == "readme_file"
