"""
Integration tests for temporal MLModel metadata graph reconstruction.

Tests the ability to reconstruct MLModel states at specific points in time
using the temporal metadata property graph with validity intervals.
"""

import os
import pytest
import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from etl_loaders.metadata_graph import (
    ensure_metadata_graph_constraints,
    write_mlmodel_metadata,
    write_mlmodel_metadata_batch,
    reconstruct_mlmodel_at,
    cleanup_metadata_graph,
    cleanup_model_metadata,
    build_and_export_metadata_rdf,
)
from etl_loaders.rdf_store import Neo4jConfig
from etl_loaders.load_helpers import LoadHelpers


@pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI environment variable not set - skipping Neo4j integration tests"
)
class TestTemporalMetadataGraph:
    """Test metadata graph reconstruction functionality."""

    @pytest.fixture(scope="class")
    def neo4j_config(self) -> Neo4jConfig:
        """Neo4j configuration from environment."""
        return Neo4jConfig.from_env()

    @pytest.fixture(scope="class", autouse=True)
    def setup_constraints(self, neo4j_config):
        """Ensure metadata graph constraints exist and clean up after tests."""
        ensure_metadata_graph_constraints(neo4j_config)
        yield
        # Clean up after all tests
        cleanup_metadata_graph(neo4j_config)

    @pytest.fixture
    def sample_model_v1(self) -> Dict[str, Any]:
        """Sample model version 1 - initial extraction."""
        return {
            "https://schema.org/identifier": ["https://huggingface.co/test/model-v1"],
            "https://schema.org/name": "Test Model V1",
            "https://schema.org/url": "https://huggingface.co/test/model-v1",
            "https://schema.org/author": "test_author",
            "https://w3id.org/fair4ml/trainedOn": ["https://huggingface.co/datasets/dataset1"],
            "https://w3id.org/mlentory/mlentory_graph/meta/": {
                "https://schema.org/name": {
                    "extraction_method": "parsed_from_readme",
                    "confidence": 0.9,
                    "notes": "Extracted from model card title"
                },
                "https://w3id.org/fair4ml/trainedOn": {
                    "extraction_method": "inferred_from_config",
                    "confidence": 0.8,
                    "notes": "Inferred from training config"
                }
            }
        }

    @pytest.fixture
    def sample_model_v2(self) -> Dict[str, Any]:
        """Sample model version 2 - name changed, dataset added."""
        return {
            "https://schema.org/identifier": ["https://huggingface.co/test/model-v1"],
            "https://schema.org/name": "Test Model V2 - Updated",  # Changed
            "https://schema.org/url": "https://huggingface.co/test/model-v1",
            "https://schema.org/author": "test_author",
            "https://w3id.org/fair4ml/trainedOn": [
                "https://huggingface.co/datasets/dataset1",
                "https://huggingface.co/datasets/dataset2"  # Added
            ],
            "https://w3id.org/mlentory/mlentory_graph/meta/": {
                "https://schema.org/name": {
                    "extraction_method": "parsed_from_readme",
                    "confidence": 0.95,
                    "notes": "Updated extraction with better parser"
                },
                "https://w3id.org/fair4ml/trainedOn": {
                    "extraction_method": "parsed_from_config",
                    "confidence": 0.9,
                    "notes": "Found additional dataset in config"
                }
            }
        }

    def test_single_valued_property_change_over_time(self, neo4j_config, sample_model_v1, sample_model_v2):
        """Test reconstructing a model where a single-valued property changed over time."""
        model_uri = LoadHelpers.mint_subject(sample_model_v1)
        cleanup_model_metadata(model_uri, neo4j_config)

        # Write metadata for version 1 (earlier timestamp)
        ts1 = datetime(2024, 1, 1, 10, 0, 0)
        write_mlmodel_metadata(sample_model_v1, ts1, neo4j_config)

        # Write metadata for version 2 (later timestamp)
        ts2 = datetime(2024, 1, 2, 10, 0, 0)
        write_mlmodel_metadata(sample_model_v2, ts2, neo4j_config)

        # Reconstruct at time just after ts1
        reconstructed_v1 = reconstruct_mlmodel_at(model_uri, ts1 + timedelta(minutes=1), neo4j_config)

        # Should have the original name
        assert "https://schema.org/name" in reconstructed_v1
        assert reconstructed_v1["https://schema.org/name"] == ["Test Model V1"]

        # Reconstruct at time just after ts2
        reconstructed_v2 = reconstruct_mlmodel_at(model_uri, ts2 + timedelta(minutes=1), neo4j_config)

        # Should have the updated name
        assert "https://schema.org/name" in reconstructed_v2
        assert reconstructed_v2["https://schema.org/name"] == ["Test Model V2 - Updated"]

        # Both should have the same URI
        assert "https://schema.org/identifier" in reconstructed_v1
        assert "https://schema.org/identifier" in reconstructed_v2
        assert reconstructed_v1["https://schema.org/identifier"] == ["https://huggingface.co/test/model-v1"]
        assert reconstructed_v2["https://schema.org/identifier"] == ["https://huggingface.co/test/model-v1"]

    def test_multi_valued_property_at_same_timestamp(self, neo4j_config, sample_model_v2):
        """Test reconstructing a model with multi-valued properties at the latest timestamp."""
        model_uri = LoadHelpers.mint_subject(sample_model_v2)
        cleanup_model_metadata(model_uri, neo4j_config)

        # Write metadata once
        ts = datetime(2024, 1, 1, 10, 0, 0)
        write_mlmodel_metadata(sample_model_v2, ts, neo4j_config)

        # Reconstruct at a later time
        reconstructed = reconstruct_mlmodel_at(model_uri, ts + timedelta(hours=1), neo4j_config)

        # Should have both datasets in trainedOn
        assert "https://w3id.org/fair4ml/trainedOn" in reconstructed
        trained_on = reconstructed["https://w3id.org/fair4ml/trainedOn"]
        assert len(trained_on) == 2
        assert "https://huggingface.co/datasets/dataset1" in trained_on
        assert "https://huggingface.co/datasets/dataset2" in trained_on

        # Should have the name
        assert "https://schema.org/name" in reconstructed
        assert reconstructed["https://schema.org/name"] == ["Test Model V2 - Updated"]

    def test_reconstruct_before_any_data(self, neo4j_config, sample_model_v1):
        """Test reconstructing a model before any metadata was written."""
        model_uri = LoadHelpers.mint_subject(sample_model_v1)
        cleanup_model_metadata(model_uri, neo4j_config)

        # Try to reconstruct before any data exists
        early_time = datetime(2023, 1, 1, 10, 0, 0)
        reconstructed = reconstruct_mlmodel_at(model_uri, early_time, neo4j_config)

        # Should return empty dict
        assert reconstructed == {}

    def test_reconstruct_nonexistent_model(self, neo4j_config):
        """Test reconstructing a model that doesn't exist."""
        fake_uri = "https://w3id.org/mlentory/model/fake123"

        ts = datetime(2024, 1, 1, 10, 0, 0)
        reconstructed = reconstruct_mlmodel_at(fake_uri, ts, neo4j_config)

        # Should return empty dict
        assert reconstructed == {}

    def test_change_only_behavior_same_model_twice(self, neo4j_config, sample_model_v1):
        """Test that writing the same model twice doesn't create duplicate relationships."""
        model_uri = LoadHelpers.mint_subject(sample_model_v1)

        # Write metadata once
        ts1 = datetime(2024, 1, 1, 10, 0, 0)
        count1 = write_mlmodel_metadata(sample_model_v1, ts1, neo4j_config)

        # Write the same model again
        ts2 = datetime(2024, 1, 1, 11, 0, 0)
        count2 = write_mlmodel_metadata(sample_model_v1, ts2, neo4j_config)

        # Second write should create 0 new relationships (no changes)
        assert count1 > 0  # First write should create relationships
        assert count2 == 0  # Second write should create no new relationships

        # Reconstruction should work the same at both timestamps
        reconstructed_1 = reconstruct_mlmodel_at(model_uri, ts1 + timedelta(minutes=1), neo4j_config)
        reconstructed_2 = reconstruct_mlmodel_at(model_uri, ts2 + timedelta(minutes=1), neo4j_config)

        assert reconstructed_1 == reconstructed_2
        assert "https://schema.org/name" in reconstructed_1
        assert reconstructed_1["https://schema.org/name"] == ["Test Model V1"]

    def test_metadata_change_creates_new_snapshot(self, neo4j_config, sample_model_v1):
        """Test that only metadata changes create new snapshots."""
        model_uri = LoadHelpers.mint_subject(sample_model_v1)
        cleanup_model_metadata(model_uri, neo4j_config)

        # Write initial metadata
        ts1 = datetime(2024, 1, 1, 10, 0, 0)
        count1 = write_mlmodel_metadata(sample_model_v1, ts1, neo4j_config)

        # Create model with same values but different metadata
        model_with_changed_metadata = sample_model_v1.copy()
        model_with_changed_metadata["https://w3id.org/mlentory/mlentory_graph/meta/"] = {
            "https://schema.org/name": {
                "extraction_method": "parsed_from_readme",
                "confidence": 0.95,  # Changed from 0.9
                "notes": "Updated confidence score"  # Also changed
            },
            "https://w3id.org/fair4ml/trainedOn": {
                "extraction_method": "inferred_from_config",
                "confidence": 0.8,
                "notes": "Inferred from training config"
            }
        }

        # Write updated metadata
        ts2 = datetime(2024, 1, 1, 11, 0, 0)
        count2 = write_mlmodel_metadata(model_with_changed_metadata, ts2, neo4j_config)

        # Should create new snapshots only for properties where metadata actually changed
        assert count1 > 0
        assert count2 == 1  # Only the name property should create a new snapshot (confidence + notes changed)

    def test_property_removal_closes_validity_intervals(self, neo4j_config, sample_model_v2):
        """Test that removing properties closes validity intervals."""
        model_uri = LoadHelpers.mint_subject(sample_model_v2)
        cleanup_model_metadata(model_uri, neo4j_config)

        # Write full model
        ts1 = datetime(2024, 1, 1, 10, 0, 0)
        write_mlmodel_metadata(sample_model_v2, ts1, neo4j_config)

        # Create model with one property removed
        model_with_removed_property = {
            "https://schema.org/identifier": ["https://huggingface.co/test/model-v1"],
            "https://schema.org/name": "Test Model V2 - Updated",
            "https://schema.org/url": "https://huggingface.co/test/model-v1",
            "https://schema.org/author": "test_author",
            # Removed: "https://w3id.org/fair4ml/trainedOn"
            "https://w3id.org/mlentory/mlentory_graph/meta/": {
                "https://schema.org/name": {
                    "extraction_method": "parsed_from_readme",
                    "confidence": 0.95,
                    "notes": "Updated extraction with better parser"
                }
            }
        }

        # Write model with removed property
        ts2 = datetime(2024, 1, 1, 11, 0, 0)
        write_mlmodel_metadata(model_with_removed_property, ts2, neo4j_config)

        # Reconstruct at time after ts1 but before ts2 - should have trainedOn
        reconstructed_after_ts1 = reconstruct_mlmodel_at(model_uri, ts1 + timedelta(minutes=1), neo4j_config)
        assert "https://w3id.org/fair4ml/trainedOn" in reconstructed_after_ts1

        # Reconstruct at time after ts2 - should not have trainedOn
        reconstructed_after_ts2 = reconstruct_mlmodel_at(model_uri, ts2 + timedelta(minutes=1), neo4j_config)
        assert "https://w3id.org/fair4ml/trainedOn" not in reconstructed_after_ts2

    def test_rdf_export_with_validity_intervals(self, neo4j_config, sample_model_v1):
        """Test that RDF export works with the new temporal metadata schema."""
        model_uri = LoadHelpers.mint_subject(sample_model_v1)
        cleanup_model_metadata(model_uri, neo4j_config)

        # Write some metadata
        ts = datetime(2024, 1, 1, 10, 0, 0)
        write_mlmodel_metadata(sample_model_v1, ts, neo4j_config)

        # Export RDF
        result = build_and_export_metadata_rdf(cfg=neo4j_config)

        # Should have exported some triples
        assert result["triples_added"] > 0
        assert result["timestamp"] is not None

    def test_reconstruct_across_multiple_temporal_changes(self, neo4j_config, sample_model_v1):
        """Test reconstruction of a model across multiple temporal changes, including boundaries."""
        model_uri = LoadHelpers.mint_subject(sample_model_v1)
        cleanup_model_metadata(model_uri, neo4j_config)

        # Version 1 (baseline) - from sample_model_v1
        v1 = copy.deepcopy(sample_model_v1)

        # Version 2 - name and trainedOn change (add dataset2), URL unchanged
        v2 = copy.deepcopy(sample_model_v1)
        v2["https://schema.org/name"] = "Test Model V2"
        v2["https://w3id.org/fair4ml/trainedOn"] = [
            "https://huggingface.co/datasets/dataset1",
            "https://huggingface.co/datasets/dataset2",
        ]
        v2["https://w3id.org/mlentory/mlentory_graph/meta/"] = {
            "https://schema.org/name": {
                "extraction_method": "parsed_from_readme",
                "confidence": 0.95,
                "notes": "Name updated from new model card",
            },
            "https://w3id.org/fair4ml/trainedOn": {
                "extraction_method": "parsed_from_config",
                "confidence": 0.9,
                "notes": "Detected additional dataset in config",
            },
        }

        # Version 3 - URL changes, trainedOn removes dataset1, adds dataset3
        v3 = copy.deepcopy(v2)
        v3["https://schema.org/url"] = "https://huggingface.co/test/model-v1-renamed"
        v3["https://w3id.org/fair4ml/trainedOn"] = [
            "https://huggingface.co/datasets/dataset2",
            "https://huggingface.co/datasets/dataset3",
        ]
        v3["https://w3id.org/mlentory/mlentory_graph/meta/"]["https://schema.org/url"] = {
            "extraction_method": "parsed_from_readme",
            "confidence": 0.9,
            "notes": "URL updated after repository rename",
        }

        # Write all versions at different times
        ts1 = datetime(2024, 1, 1, 10, 0, 0)
        ts2 = datetime(2024, 1, 2, 10, 0, 0)
        ts3 = datetime(2024, 1, 3, 10, 0, 0)

        write_mlmodel_metadata(v1, ts1, neo4j_config)
        write_mlmodel_metadata(v2, ts2, neo4j_config)
        write_mlmodel_metadata(v3, ts3, neo4j_config)

        # Helper to sort lists in reconstruction for comparison
        def get_vals(reconstructed: Dict[str, Any], key: str) -> list[str]:
            return sorted(reconstructed.get(key, []))

        # Just after ts1 -> should reflect v1
        r_after_ts1 = reconstruct_mlmodel_at(model_uri, ts1 + timedelta(minutes=1), neo4j_config)
        assert r_after_ts1["https://schema.org/name"] == ["Test Model V1"]
        assert get_vals(r_after_ts1, "https://w3id.org/fair4ml/trainedOn") == [
            "https://huggingface.co/datasets/dataset1"
        ]
        assert r_after_ts1["https://schema.org/url"] == ["https://huggingface.co/test/model-v1"]

        # Just before ts2 -> still v1
        r_before_ts2 = reconstruct_mlmodel_at(
            model_uri, ts2 - timedelta(seconds=1), neo4j_config
        )
        assert r_before_ts2["https://schema.org/name"] == ["Test Model V1"]
        assert get_vals(r_before_ts2, "https://w3id.org/fair4ml/trainedOn") == [
            "https://huggingface.co/datasets/dataset1"
        ]

        # Exactly at ts2 -> v2 should be active (valid_from inclusive, valid_to exclusive)
        r_at_ts2 = reconstruct_mlmodel_at(model_uri, ts2, neo4j_config)
        assert r_at_ts2["https://schema.org/name"] == ["Test Model V2"]
        assert get_vals(r_at_ts2, "https://w3id.org/fair4ml/trainedOn") == [
            "https://huggingface.co/datasets/dataset1",
            "https://huggingface.co/datasets/dataset2",
        ]
        assert r_at_ts2["https://schema.org/url"] == ["https://huggingface.co/test/model-v1"]

        # Between ts2 and ts3 -> still v2
        r_between_ts2_ts3 = reconstruct_mlmodel_at(
            model_uri, ts2 + timedelta(hours=1), neo4j_config
        )
        assert r_between_ts2_ts3["https://schema.org/name"] == ["Test Model V2"]
        assert get_vals(r_between_ts2_ts3, "https://w3id.org/fair4ml/trainedOn") == [
            "https://huggingface.co/datasets/dataset1",
            "https://huggingface.co/datasets/dataset2",
        ]

        # Exactly at ts3 -> v3 becomes active
        r_at_ts3 = reconstruct_mlmodel_at(model_uri, ts3, neo4j_config)
        assert r_at_ts3["https://schema.org/url"] == [
            "https://huggingface.co/test/model-v1-renamed"
        ]
        assert get_vals(r_at_ts3, "https://w3id.org/fair4ml/trainedOn") == [
            "https://huggingface.co/datasets/dataset2",
            "https://huggingface.co/datasets/dataset3",
        ]

        # After ts3 -> still v3
        r_after_ts3 = reconstruct_mlmodel_at(
            model_uri, ts3 + timedelta(hours=1), neo4j_config
        )
        assert r_after_ts3["https://schema.org/url"] == [
            "https://huggingface.co/test/model-v1-renamed"
        ]
        assert get_vals(r_after_ts3, "https://w3id.org/fair4ml/trainedOn") == [
            "https://huggingface.co/datasets/dataset2",
            "https://huggingface.co/datasets/dataset3",
        ]

    def test_hash_based_change_detection(self, neo4j_config, sample_model_v1):
        """Test that hash-based change detection works correctly."""
        from etl_loaders.metadata_graph import _generate_snapshot_hash, _extract_property_snapshots

        model_uri = LoadHelpers.mint_subject(sample_model_v1)

        # Clean up any existing metadata for this model to ensure clean test state
        cleanup_model_metadata(model_uri, neo4j_config)

        # Extract snapshots from the model
        extraction_meta = sample_model_v1.get("https://w3id.org/mlentory/mlentory_graph/meta/", {})
        snapshots1 = _extract_property_snapshots(sample_model_v1, extraction_meta)

        # Create identical model
        model_identical = sample_model_v1.copy()
        snapshots2 = _extract_property_snapshots(model_identical, extraction_meta)

        # Hashes should be identical for identical snapshots
        for s1, s2 in zip(snapshots1, snapshots2):
            assert s1["snapshot_hash"] == s2["snapshot_hash"]

        # Write initial metadata
        ts1 = datetime(2024, 1, 1, 10, 0, 0)
        count1 = write_mlmodel_metadata(sample_model_v1, ts1, neo4j_config)

        # Write identical model - should create 0 new relationships
        ts2 = datetime(2024, 1, 1, 11, 0, 0)
        count2 = write_mlmodel_metadata(sample_model_v1, ts2, neo4j_config)

        assert count1 > 0
        assert count2 == 0  # No changes, so no new snapshots created

        # Create model with one metadata change
        model_changed = sample_model_v1.copy()
        model_changed["https://w3id.org/mlentory/mlentory_graph/meta/"] = {
            "https://schema.org/name": {
                "extraction_method": "parsed_from_readme",
                "confidence": 0.95,  # Changed from 0.9
                "notes": "Updated confidence score"
            },
            # Keep trainedOn metadata identical to ensure only the name property changes
            "https://w3id.org/fair4ml/trainedOn": {
                "extraction_method": "inferred_from_config",
                "confidence": 0.8,
                "notes": "Inferred from training config"
            },
        }

        # Write changed model
        ts3 = datetime(2024, 1, 1, 12, 0, 0)
        count3 = write_mlmodel_metadata(model_changed, ts3, neo4j_config)

        # Should create exactly 1 new snapshot (only name changed)
        assert count3 == 1

    def test_batch_metadata_write(self, neo4j_config, sample_model_v1, sample_model_v2):
        """Test writing metadata for multiple models in a batch."""

        # Prepare batch
        model1 = sample_model_v1
        # Make model2 different from model1
        model2 = copy.deepcopy(sample_model_v2)
        model2["https://schema.org/identifier"] = ["https://huggingface.co/test/model-batch-2"]
        model2["https://schema.org/url"] = "https://huggingface.co/test/model-batch-2"
        
        uri1 = LoadHelpers.mint_subject(model1)
        uri2 = LoadHelpers.mint_subject(model2)
        
        cleanup_model_metadata(uri1, neo4j_config)
        cleanup_model_metadata(uri2, neo4j_config)

        ts1 = datetime(2024, 1, 1, 10, 0, 0)
        
        # Write batch
        count = write_mlmodel_metadata_batch([model1, model2], ts1, neo4j_config)
        
        # Should create relationships for both models
        assert count > 0
        
        # Verify both exist
        r1 = reconstruct_mlmodel_at(uri1, ts1, neo4j_config)
        r2 = reconstruct_mlmodel_at(uri2, ts1, neo4j_config)
        
        assert r1["https://schema.org/name"] == ["Test Model V1"]
        assert r2["https://schema.org/name"] == ["Test Model V2 - Updated"]
        
        # Verify updating in batch works
        model1_v2 = copy.deepcopy(model1)
        model1_v2["https://schema.org/name"] = "Test Model V1 Updated"
        
        ts2 = datetime(2024, 1, 2, 10, 0, 0)
        
        # Pass both again, but only one changed
        count_update = write_mlmodel_metadata_batch([model1_v2, model2], ts2, neo4j_config)
        
        assert count_update > 0
        
        r1_updated = reconstruct_mlmodel_at(uri1, ts2, neo4j_config)
        assert r1_updated["https://schema.org/name"] == ["Test Model V1 Updated"]
