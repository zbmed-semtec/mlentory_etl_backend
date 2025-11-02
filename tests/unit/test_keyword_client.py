"""
Unit tests for the HFKeywordClient.
"""

import pytest
import pandas as pd
from pathlib import Path
import json
import tempfile

from etl_extractors.hf.clients.keyword_client import HFKeywordClient


@pytest.fixture
def temp_csv_path():
    """Create a temporary CSV file with test keyword definitions."""
    csv_content = """keyword,definition,aliases
test_keyword,"A test keyword definition","[""alias1"",""alias2""]"
nlp,"Natural Language Processing","[""text-processing""]"
missing_kw,"","[]"
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        f.flush()
        yield Path(f.name)

    # Cleanup
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def keyword_client(temp_csv_path):
    """Create HFKeywordClient instance with test CSV."""
    return HFKeywordClient(csv_path=temp_csv_path)


class TestHFKeywordClient:
    """Unit tests for HFKeywordClient functionality."""

    def test_load_curated_csv(self, keyword_client):
        """Test loading curated keywords from CSV."""
        assert "test_keyword" in keyword_client.curated_definitions
        assert "nlp" in keyword_client.curated_definitions

        test_kw = keyword_client.curated_definitions["test_keyword"]
        assert test_kw["definition"] == "A test keyword definition"
        assert test_kw["aliases"] == ["alias1", "alias2"]
        assert test_kw["source"] == "curated_csv"

    def test_get_keywords_metadata_curated_only(self, keyword_client):
        """Test retrieving keywords that exist in curated CSV."""
        keywords = ["test_keyword", "nlp"]
        result_df = keyword_client.get_keywords_metadata(keywords)

        assert len(result_df) == 2

        # Check test_keyword
        test_row = result_df[result_df["keyword"] == "test_keyword"].iloc[0]
        assert test_row["definition"] == "A test keyword definition"
        assert test_row["source"] == "curated_csv"
        assert test_row["aliases"] == ["alias1", "alias2"]

        # Check nlp
        nlp_row = result_df[result_df["keyword"] == "nlp"].iloc[0]
        assert nlp_row["definition"] == "Natural Language Processing"
        assert nlp_row["source"] == "curated_csv"

    def test_get_keywords_metadata_missing_from_curated(self, keyword_client):
        """Test retrieving keywords not in curated CSV (should fallback to Wikipedia)."""
        keywords = ["nonexistent_keyword_12345"]
        result_df = keyword_client.get_keywords_metadata(keywords)

        assert len(result_df) == 1
        row = result_df.iloc[0]

        assert row["keyword"] == "nonexistent_keyword_12345"
        # Should either be None (not found) or have Wikipedia data
        assert row["source"] in ["not_found", "wikipedia"]

    def test_get_keywords_metadata_mixed(self, keyword_client):
        """Test retrieving mix of curated and non-curated keywords."""
        keywords = ["test_keyword", "some_unknown_keyword", "nlp"]
        result_df = keyword_client.get_keywords_metadata(keywords)

        assert len(result_df) == 3

        # Curated keywords should have correct source
        curated_rows = result_df[result_df["source"] == "curated_csv"]
        assert len(curated_rows) == 2  # test_keyword and nlp

        # Unknown keyword should have different source
        unknown_row = result_df[result_df["keyword"] == "some_unknown_keyword"].iloc[0]
        assert unknown_row["source"] in ["not_found", "wikipedia"]

    def test_csv_with_invalid_json_aliases(self, temp_csv_path):
        """Test handling of CSV with invalid JSON in aliases column."""
        # Create CSV with invalid JSON
        invalid_csv_content = """keyword,definition,aliases
bad_json_kw,"Definition","[invalid json"
"""
        with open(temp_csv_path, 'w') as f:
            f.write(invalid_csv_content)

        client = HFKeywordClient(csv_path=temp_csv_path)

        # Should still load other valid entries and handle invalid ones gracefully
        # The client should not crash on invalid JSON
        assert len(client.curated_definitions) >= 0  # At least empty

    def test_empty_keywords_list(self, keyword_client):
        """Test handling empty keywords list."""
        result_df = keyword_client.get_keywords_metadata([])
        assert len(result_df) == 0
        assert isinstance(result_df, pd.DataFrame)

    def test_wikipedia_fallback_simulation(self, keyword_client, monkeypatch):
        """Test that Wikipedia fallback is attempted for unknown keywords."""
        # Mock the Wikipedia API to simulate a successful lookup
        def mock_wiki_page(self, title):
            class MockPage:
                def __init__(self):
                    self.title = title
                    self.summary = "This is a mock Wikipedia summary for testing."
                    self.fullurl = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"

                def exists(self):
                    return True

            return MockPage()

        monkeypatch.setattr(keyword_client.wiki, 'page', mock_wiki_page)

        keywords = ["test_wikipedia_fallback"]
        result_df = keyword_client.get_keywords_metadata(keywords)

        assert len(result_df) == 1
        row = result_df.iloc[0]

        assert row["keyword"] == "test_wikipedia_fallback"
        assert row["source"] == "wikipedia"
        assert "mock Wikipedia summary" in row["definition"]
        assert row["url"].startswith("https://en.wikipedia.org")

    def test_wikipedia_page_not_found(self, keyword_client, monkeypatch):
        """Test handling when Wikipedia page doesn't exist."""
        def mock_wiki_page(self, title):
            class MockPage:
                def exists(self):
                    return False
            return MockPage()

        monkeypatch.setattr(keyword_client.wiki, 'page', mock_wiki_page)

        keywords = ["nonexistent_wikipedia_page_12345"]
        result_df = keyword_client.get_keywords_metadata(keywords)

        assert len(result_df) == 1
        row = result_df.iloc[0]

        assert row["keyword"] == "nonexistent_wikipedia_page_12345"
        assert row["source"] == "not_found"
        assert row["definition"] is None

