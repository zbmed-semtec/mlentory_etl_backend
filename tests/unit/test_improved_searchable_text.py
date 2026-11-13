"""Text used by the improved vector index."""

from etl_loaders.vector_index_manager import (
    _extracted_data_from_indexed_model,
    build_improved_searchable_text,
)


def test_improved_text_uses_label_lines_and_keeps_the_description():
    description = "D" * 800
    model_data = {
        "name": "bert-base-uncased",
        "shared_by": "google-bert",
        "ml_tasks": ["fill-mask", "feature-extraction"],
        "keywords": ["transformers", "pytorch"],
        "datasets": ["wikipedia", "bookcorpus"],
        "domain": "natural language processing",
        "model_category": ["bert", "encoder"],
        "modalities": ["text"],
        "description": description,
        "license": "apache-2.0",
        "parameter_count": "110M",
        "data_splits": "train/test",
        "adaption_techniques": "pre-training",
    }
    text = build_improved_searchable_text(
        model_data, _extracted_data_from_indexed_model(model_data)
    )

    assert text == "\n".join(
        [
            "name: bert-base-uncased",
            "author: google-bert",
            "task: fill-mask, feature-extraction",
            "keywords: transformers, pytorch",
            "datasets: wikipedia, bookcorpus",
            "domain: natural language processing",
            "architecture: bert, encoder",
            "modalities: text",
            f"description: {description}",
        ]
    )
    assert "apache-2.0" not in text
    assert "110M" not in text
    assert "train/test" not in text
    assert "pre-training" not in text
    assert "The model name is" not in text


def test_improved_text_skips_empty_and_placeholder_fields():
    text = build_improved_searchable_text(
        {
            "name": "unet",
            "shared_by": "Unknown",
            "keywords": [],
            "description": "Cell segmentation model",
            "datasets": ["information not found", "BioSR"],
        }
    )
    assert text == "\n".join(
        [
            "name: unet",
            "datasets: BioSR",
            "description: Cell segmentation model",
        ]
    )
