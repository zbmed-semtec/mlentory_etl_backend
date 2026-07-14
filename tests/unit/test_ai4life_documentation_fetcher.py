"""Unit tests for AI4Life documentation fetching in AI4LifeHelper."""

from unittest.mock import MagicMock, patch

from etl_extractors.ai4life.ai4life_helper import AI4LifeHelper


class TestFetchDocumentationText:
    @patch("etl_extractors.ai4life.ai4life_helper.requests.get")
    def test_fetch_documentation_text_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "# Model docs\n\nSome content."
        mock_response.encoding = "utf-8"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        result = AI4LifeHelper.fetch_documentation_text(
            "https://hypha.aicell.io/bioimage-io/artifacts/good-microbe/files/documentation.md"
        )

        assert result == "# Model docs\n\nSome content."
        mock_get.assert_called_once()

    @patch("etl_extractors.ai4life.ai4life_helper.requests.get")
    def test_fetch_documentation_text_failure(self, mock_get):
        mock_get.side_effect = RuntimeError("network error")

        result = AI4LifeHelper.fetch_documentation_text("https://example.com/documentation.md")

        assert result is None


class TestResolveAbstractContent:
    def test_uses_persisted_documentation_content(self):
        raw_model = {
            "documentation_content": "# Stored docs",
            "readme_file": "https://example.com/documentation.md",
        }

        assert AI4LifeHelper.resolve_abstract_content(raw_model) == "# Stored docs"

    @patch.object(AI4LifeHelper, "fetch_documentation_text")
    def test_fetches_from_readme_when_content_missing(self, mock_fetch):
        mock_fetch.return_value = "# Fetched docs"
        raw_model = {
            "readme_file": "https://example.com/documentation.md",
        }

        assert AI4LifeHelper.resolve_abstract_content(raw_model) == "# Fetched docs"
        mock_fetch.assert_called_once_with("https://example.com/documentation.md", timeout=15)

    def test_returns_none_without_readme(self):
        assert AI4LifeHelper.resolve_abstract_content({}) is None


class TestEnrichModelsWithDocumentation:
    @patch.object(AI4LifeHelper, "fetch_documentation_text")
    def test_enrich_models_with_documentation(self, mock_fetch):
        mock_fetch.return_value = "# Full readme"
        models = [
            {
                "modelId": "good-microbe",
                "readme_file": (
                    "https://hypha.aicell.io/bioimage-io/artifacts/good-microbe/files/documentation.md"
                ),
            }
        ]

        AI4LifeHelper.enrich_models_with_documentation(models, max_workers=1)

        assert models[0]["documentation_content"] == "# Full readme"

    @patch.object(AI4LifeHelper, "fetch_documentation_text")
    def test_skips_fetch_when_content_already_present(self, mock_fetch):
        models = [
            {
                "modelId": "cached-model",
                "readme_file": "https://example.com/documentation.md",
                "documentation_content": "# Already fetched",
            }
        ]

        AI4LifeHelper.enrich_models_with_documentation(models, max_workers=1)

        assert models[0]["documentation_content"] == "# Already fetched"
        mock_fetch.assert_not_called()
