"""
End-to-end integration tests for the HuggingFace extraction pipeline.

Tests the complete workflow from model download through entity enrichment.
"""

import pytest
import pandas as pd
import json
from pathlib import Path
import glob

from extractors.hf import HFExtractor, HFEnrichment


@pytest.mark.e2e
@pytest.mark.integration
class TestHFPipelineE2E:
    """
    End-to-end tests for the complete HF extraction and enrichment pipeline.

    Tests specific models to ensure the pipeline works correctly and
    extracts accurate metadata.
    """

    @pytest.fixture(scope="class")
    def temp_data_dir(self, tmp_path_factory):
        """Create a temporary directory for test data."""
        return tmp_path_factory.mktemp("hf_test_data")

    @pytest.fixture(scope="class")
    def extractor(self):
        """Create HFExtractor instance for testing."""
        return HFExtractor()

    @pytest.fixture(scope="class")
    def enrichment(self):
        """Create HFEnrichment instance for testing."""
        return HFEnrichment()

    def test_download_specific_models_kani_tts(self, extractor, temp_data_dir):
        """Test downloading the kani-tts-370m model specifically."""
        model_ids = ["nineninesix/kani-tts-370m"]

        df, json_path = extractor.extract_specific_models(
            model_ids=model_ids,
            output_root=temp_data_dir,
            save_csv=True
        )

        # Verify DataFrame was created
        assert not df.empty, "DataFrame should not be empty"
        assert len(df) == 1, "Should have exactly one model"

        # Verify model metadata
        model_data = df.iloc[0]
        assert model_data["modelId"] == "nineninesix/kani-tts-370m"
        assert model_data["author"] == "nineninesix"
        assert model_data["pipeline_tag"] == "text-generation"
        assert "lfm2" in model_data.get("tags", [])
        assert "text-generation" in model_data.get("tags", [])

        # Verify files were created
        assert json_path.exists(), f"JSON file should exist: {json_path}"
        csv_path = json_path.with_suffix('.csv')
        assert csv_path.exists(), f"CSV file should exist: {csv_path}"

        # Verify JSON content
        with open(json_path, 'r') as f:
            json_data = json.load(f)
            assert len(json_data) == 1
            assert json_data[0]["modelId"] == "nineninesix/kani-tts-370m"

        print(f"✓ Successfully downloaded kani-tts-370m model")
        print(f"  Model ID: {model_data['modelId']}")
        print(f"  Author: {model_data['author']}")
        print(f"  Downloads: {model_data.get('downloads', 'N/A')}")
        print(f"  Pipeline: {model_data['pipeline_tag']}")
        print(f"  Tags: {model_data.get('tags', [])[:5]}...")  # Show first 5 tags

    def test_download_specific_models_granite(self, extractor, temp_data_dir):
        """Test downloading the granite-4.0-h-small model specifically."""
        model_ids = ["ibm-granite/granite-4.0-h-small"]

        df, json_path = extractor.extract_specific_models(
            model_ids=model_ids,
            output_root=temp_data_dir,
            save_csv=True
        )

        # Verify DataFrame was created
        assert not df.empty, "DataFrame should not be empty"
        assert len(df) == 1, "Should have exactly one model"

        # Verify model metadata
        model_data = df.iloc[0]
        assert model_data["modelId"] == "ibm-granite/granite-4.0-h-small"
        assert model_data["author"] == "ibm-granite"
        assert model_data["pipeline_tag"] == "text-generation"
        assert "granite" in model_data.get("tags", [])
        assert "granitemoehybrid" in model_data.get("tags", [])
        assert "conversational" in model_data.get("tags", [])

        # Verify files were created
        assert json_path.exists(), f"JSON file should exist: {json_path}"
        csv_path = json_path.with_suffix('.csv')
        assert csv_path.exists(), f"CSV file should exist: {csv_path}"

        print(f"✓ Successfully downloaded granite-4.0-h-small model")
        print(f"  Model ID: {model_data['modelId']}")
        print(f"  Author: {model_data['author']}")
        print(f"  Downloads: {model_data.get('downloads', 'N/A')}")
        print(f"  Pipeline: {model_data['pipeline_tag']}")
        print(f"  Tags: {model_data.get('tags', [])[:5]}...")  # Show first 5 tags

    def test_entity_identification_kani_tts(self, enrichment, temp_data_dir):
        """Test entity identification from kani-tts-370m model."""
        # First download the model to get its metadata
        extractor = HFExtractor()
        df, _ = extractor.extract_specific_models(
            model_ids=["nineninesix/kani-tts-370m"],
            output_root=temp_data_dir
        )

        # Identify related entities
        related_entities = enrichment.identify_related_entities(df)

        # Verify entities were identified
        assert "datasets" in related_entities, "Should identify datasets"
        assert "articles" in related_entities, "Should identify articles"
        assert "keywords" in related_entities, "Should identify keywords"
        assert "licenses" in related_entities, "Should identify licenses"

        # Check for expected arXiv ID from the model card
        arxiv_ids = related_entities["articles"]
        assert "2505.20506" in arxiv_ids, "Should find arXiv ID 2505.20506 from model card"

        # Check for expected license
        licenses = related_entities["licenses"]
        assert "apache-2.0" in licenses, "Should find apache-2.0 license"

        print(f"✓ Identified entities for kani-tts-370m:")
        print(f"  Articles: {list(arxiv_ids)[:3]}...")  # Show first 3
        print(f"  Keywords: {list(related_entities['keywords'])[:5]}...")  # Show first 5
        print(f"  Licenses: {list(licenses)}")

    def test_entity_identification_granite(self, enrichment, temp_data_dir):
        """Test entity identification from granite-4.0-h-small model."""
        # First download the model to get its metadata
        extractor = HFExtractor()
        df, _ = extractor.extract_specific_models(
            model_ids=["ibm-granite/granite-4.0-h-small"],
            output_root=temp_data_dir
        )

        # Identify related entities
        related_entities = enrichment.identify_related_entities(df)

        # Verify entities were identified
        assert "datasets" in related_entities, "Should identify datasets"
        assert "articles" in related_entities, "Should identify articles"
        assert "keywords" in related_entities, "Should identify keywords"
        assert "licenses" in related_entities, "Should identify licenses"

        # Check for expected license
        licenses = related_entities["licenses"]
        assert "apache-2.0" in licenses, "Should find apache-2.0 license"

        # Check for expected keywords
        keywords = related_entities["keywords"]
        assert "granite" in keywords, "Should find 'granite' keyword"
        assert "text-generation" in keywords, "Should find 'text-generation' keyword"

        print(f"✓ Identified entities for granite-4.0-h-small:")
        print(f"  Articles: {list(related_entities['articles'])[:3]}...")  # Show first 3
        print(f"  Keywords: {list(keywords)[:5]}...")  # Show first 5
        print(f"  Licenses: {list(licenses)}")

    def test_entity_enrichment_kani_tts(self, enrichment, temp_data_dir):
        """Test complete entity enrichment for kani-tts-370m."""
        # First download the model to get its metadata
        extractor = HFExtractor()
        df, _ = extractor.extract_specific_models(
            model_ids=["nineninesix/kani-tts-370m"],
            output_root=temp_data_dir
        )

        # Run complete enrichment
        output_paths = enrichment.enrich_from_models_json(
            models_json_path=temp_data_dir / "raw" / "hf" / "*_hf_models_specific.json",
            entity_types=["articles", "keywords", "licenses"],  # Skip datasets for speed
            output_root=temp_data_dir
        )

        # Verify output files were created
        assert "articles" in output_paths, "Should have articles output"
        assert "keywords" in output_paths, "Should have keywords output"
        assert "licenses" in output_paths, "Should have licenses output"

        # Verify articles were downloaded
        articles_path = Path(output_paths["articles"])
        assert articles_path.exists(), f"Articles file should exist: {articles_path}"

        with open(articles_path, 'r') as f:
            articles_data = json.load(f)
            assert len(articles_data) > 0, "Should have downloaded articles"

            # Check for the expected arXiv paper
            arxiv_ids = [article["arxiv_id"] for article in articles_data]
            assert "2505.20506" in arxiv_ids, "Should have downloaded arXiv:2505.20506"

        # Verify keywords were processed
        keywords_path = Path(output_paths["keywords"])
        assert keywords_path.exists(), f"Keywords file should exist: {keywords_path}"

        with open(keywords_path, 'r') as f:
            keywords_data = json.load(f)
            assert len(keywords_data) > 0, "Should have processed keywords"

        # Verify licenses were processed
        licenses_path = Path(output_paths["licenses"])
        assert licenses_path.exists(), f"Licenses file should exist: {licenses_path}"

        with open(licenses_path, 'r') as f:
            licenses_data = json.load(f)
            assert len(licenses_data) > 0, "Should have processed licenses"

        print(f"✓ Successfully enriched entities for kani-tts-370m")
        print(f"  Articles: {articles_path} ({len(articles_data)} articles)")
        print(f"  Keywords: {keywords_path} ({len(keywords_data)} keywords)")
        print(f"  Licenses: {licenses_path} ({len(licenses_data)} licenses)")

    def test_entity_enrichment_granite(self, enrichment, temp_data_dir):
        """Test complete entity enrichment for granite-4.0-h-small."""
        # First download the model to get its metadata
        extractor = HFExtractor()
        df, _ = extractor.extract_specific_models(
            model_ids=["ibm-granite/granite-4.0-h-small"],
            output_root=temp_data_dir
        )

        # Run complete enrichment
        output_paths = enrichment.enrich_from_models_json(
            models_json_path=temp_data_dir / "raw" / "hf" / "*_hf_models_specific.json",
            entity_types=["keywords", "licenses"],  # Skip articles/datasets for speed
            output_root=temp_data_dir
        )

        # Verify output files were created
        assert "keywords" in output_paths, "Should have keywords output"
        assert "licenses" in output_paths, "Should have licenses output"

        # Verify keywords were processed
        keywords_path = Path(output_paths["keywords"])
        assert keywords_path.exists(), f"Keywords file should exist: {keywords_path}"

        with open(keywords_path, 'r') as f:
            keywords_data = json.load(f)
            assert len(keywords_data) > 0, "Should have processed keywords"

            # Check for expected keywords
            keyword_names = [kw["keyword"] for kw in keywords_data]
            assert "granite" in keyword_names, "Should have 'granite' keyword"
            assert "text-generation" in keyword_names, "Should have 'text-generation' keyword"

        # Verify licenses were processed
        licenses_path = Path(output_paths["licenses"])
        assert licenses_path.exists(), f"Licenses file should exist: {licenses_path}"

        with open(licenses_path, 'r') as f:
            licenses_data = json.load(f)
            assert len(licenses_data) > 0, "Should have processed licenses"

        print(f"✓ Successfully enriched entities for granite-4.0-h-small")
        print(f"  Keywords: {keywords_path} ({len(keywords_data)} keywords)")
        print(f"  Licenses: {licenses_path} ({len(licenses_data)} licenses)")

    def test_keyword_definitions_curated_vs_wikipedia(self, extractor, temp_data_dir):
        """Test that curated keywords are preferred over Wikipedia lookups."""
        # Test keywords that should be in our curated CSV
        keywords = ["nlp", "pytorch", "tensorflow"]

        _, json_path = extractor.extract_keywords(
            keywords=keywords,
            output_root=temp_data_dir
        )

        with open(json_path, 'r') as f:
            keywords_data = json.load(f)

        # Verify we got data for all keywords
        assert len(keywords_data) == len(keywords)

        # Check that curated keywords have expected source
        for kw_data in keywords_data:
            if kw_data["keyword"] in ["nlp", "pytorch", "tensorflow"]:
                assert kw_data["source"] == "curated_csv", f"Keyword {kw_data['keyword']} should be from curated CSV"
                assert kw_data["definition"] is not None, f"Keyword {kw_data['keyword']} should have definition"

        print(f"✓ Curated keywords properly loaded from CSV:")
        for kw_data in keywords_data:
            print(f"  {kw_data['keyword']}: {kw_data['source']} - '{kw_data['definition'][:50]}...'")

    def test_full_pipeline_integration(self, extractor, enrichment, temp_data_dir):
        """Test the complete pipeline: download → identify → enrich."""
        # Step 1: Download both models
        model_ids = ["nineninesix/kani-tts-370m", "ibm-granite/granite-4.0-h-small"]

        models_df, models_path = extractor.extract_specific_models(
            model_ids=model_ids,
            output_root=temp_data_dir
        )

        assert len(models_df) == 2, "Should have downloaded both models"

        # Step 2: Identify related entities
        related_entities = enrichment.identify_related_entities(models_df)

        # Should have entities from both models
        assert len(related_entities["articles"]) > 0, "Should find articles from both models"
        assert len(related_entities["keywords"]) > 0, "Should find keywords from both models"
        assert "apache-2.0" in related_entities["licenses"], "Should find apache-2.0 license"

        # Step 3: Enrich entities
        output_paths = enrichment.enrich_from_models_json(
            models_json_path=models_path,
            entity_types=["keywords", "licenses"],  # Keep it fast
            output_root=temp_data_dir
        )

        # Verify all expected outputs exist
        assert "keywords" in output_paths
        assert "licenses" in output_paths

        # Verify content
        with open(output_paths["keywords"], 'r') as f:
            keywords_data = json.load(f)
            assert len(keywords_data) > 0

        with open(output_paths["licenses"], 'r') as f:
            licenses_data = json.load(f)
            assert len(licenses_data) > 0

        print(f"✓ Full pipeline integration test passed!")
        print(f"  Models downloaded: {len(models_df)}")
        print(f"  Entity types enriched: {list(output_paths.keys())}")
        print(f"  Total keywords processed: {len(keywords_data)}")
        print(f"  Total licenses processed: {len(licenses_data)}")

    @pytest.mark.parametrize("model_id,expected_pipeline,expected_tags", [
        ("nineninesix/kani-tts-370m", "text-generation", ["lfm2", "text-generation"]),
        ("ibm-granite/granite-4.0-h-small", "text-generation", ["granite", "conversational"]),
    ])
    def test_model_metadata_validation(self, extractor, temp_data_dir, model_id, expected_pipeline, expected_tags):
        """Parameterized test to validate specific model metadata."""
        df, _ = extractor.extract_specific_models(
            model_ids=[model_id],
            output_root=temp_data_dir
        )

        assert len(df) == 1
        model_data = df.iloc[0]

        assert model_data["pipeline_tag"] == expected_pipeline

        tags = model_data.get("tags", [])
        for expected_tag in expected_tags:
            assert expected_tag in tags, f"Expected tag '{expected_tag}' not found in {tags}"

