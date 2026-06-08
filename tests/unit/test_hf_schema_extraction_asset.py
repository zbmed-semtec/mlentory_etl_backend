"""
Unit tests for HF schema extraction Dagster asset helpers.
"""

from __future__ import annotations

import json
from pathlib import Path

from etl.assets.hf_schema_extraction import build_preprocessed_model_cards


SAMPLE_MODELS = [
    {
        "modelId": "org/demo-model",
        "card": """# Demo

## Description
A text-generation model.

```python
print("skip me")
```

## Training
Fine-tuned on custom data.
""",
    }
]


def test_build_preprocessed_model_cards_from_json(tmp_path: Path):
    models_path = tmp_path / "hf_models_with_ancestors.json"
    with open(models_path, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_MODELS, f)

    result = build_preprocessed_model_cards(models_path)

    assert "org/demo-model" in result
    text = result["org/demo-model"]
    assert "text-generation model" in text
    assert 'print("skip me")' not in text
