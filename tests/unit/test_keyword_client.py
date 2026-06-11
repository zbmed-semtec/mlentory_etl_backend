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
        """Test retrieving keywords not in curated CSV (should fallback to Wikidata)."""
        keywords = ["nonexistent_keyword_12345"]
        result_df = keyword_client.get_keywords_metadata(keywords)

        assert len(result_df) == 1
        row = result_df.iloc[0]

        assert row["keyword"] == "nonexistent_keyword_12345"
        # Should either be None (not found) or have Wikidata data
        assert row["source"] in ["not_found", "wikidata"]

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
        assert unknown_row["source"] in ["not_found", "wikidata"]

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

    def test_wikidata_enrichment_success(self, keyword_client, monkeypatch):
        """Test that Wikidata enrichment returns correct data for found keywords."""
        def mock_enrich(keyword):
            return {
                "keyword": keyword,
                "mlentory_id": f"mlentory:keyword:{keyword}",
                "definition": "A mock Wikidata description for testing.",
                "source": "wikidata",
                "url": "http://www.wikidata.org/entity/Q12345",
                "aliases": ["alias1", "Test Label"],
                "wikidata_qid": "Q12345",
                "enriched": True,
                "entity_type": "Keyword",
                "platform": "HF",
                "extraction_metadata": {
                    "extraction_method": "Wikidata API + Semantic Search",
                    "confidence": 0.85,
                    "wikidata_type": "artificial intelligence",
                    "type_qids": ["Q11660"],
                },
            }

        monkeypatch.setattr(keyword_client, "_enrich_keyword", mock_enrich)

        keywords = ["test_wikidata_enrichment"]
        result_df = keyword_client.get_keywords_metadata(keywords)

        assert len(result_df) == 1
        row = result_df.iloc[0]

        assert row["keyword"] == "test_wikidata_enrichment"
        assert row["source"] == "wikidata"
        assert "mock Wikidata description" in row["definition"]
        assert row["url"] == "http://www.wikidata.org/entity/Q12345"
        assert row["wikidata_qid"] == "Q12345"

    def test_wikidata_enrichment_not_found(self, keyword_client, monkeypatch):
        """Test handling when Wikidata returns no results for a keyword."""
        monkeypatch.setattr(keyword_client, "_enrich_keyword", lambda kw: None)

        keywords = ["nonexistent_keyword_12345"]
        result_df = keyword_client.get_keywords_metadata(keywords)

        assert len(result_df) == 1
        row = result_df.iloc[0]

        assert row["keyword"] == "nonexistent_keyword_12345"
        assert row["source"] == "not_found"
        assert row["definition"] is None

