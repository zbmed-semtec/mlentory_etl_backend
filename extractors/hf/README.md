# HuggingFace Extractor Module

Modular extraction system for HuggingFace model metadata and related entities.

## Architecture

The HF extractor is organized into independent, reusable modules:

```
extractors/hf/
├── hf_dataset_manager.py      # Low-level HF API interactions
├── hf_extractor.py             # High-level extraction wrapper
├── hf_enrichment.py            # Entity enrichment orchestrator
├── hf_license_extractor.py    # SPDX license metadata
└── entity_identifiers/         # Pluggable entity identifiers
    ├── base.py                 # EntityIdentifier interface
    ├── dataset_identifier.py   # Extract dataset references
    ├── article_identifier.py   # Extract arXiv IDs
    ├── base_model_identifier.py # Extract base model refs
    ├── keyword_identifier.py   # Extract keywords/tags
    └── license_identifier.py   # Extract license IDs
```

## Workflow

### 1. Extract Raw Models
```python
from extractors.hf import HFExtractor

extractor = HFExtractor()
models_json_path = extractor.extract_models(
    num_models=50,
    update_recent=True,
    threads=4
)
# Saves to /data/raw/hf/<timestamp>_hf_models.json
```

### 2. Identify Related Entities
```python
from extractors.hf import HFEnrichment
import pandas as pd

enrichment = HFEnrichment()

# Load models
models_df = pd.read_json(models_json_path)

# Identify related entities
related_entities = enrichment.identify_related_entities(
    models_df,
    entity_types=["datasets", "articles", "base_models", "keywords", "licenses"]
)

# Result:
# {
#     "datasets": {"squad", "glue", "mnist"},
#     "articles": {"2106.09685", "1706.03762"},
#     "base_models": {"bert-base-uncased"},
#     "keywords": {"nlp", "pytorch", "transformers"},
#     "licenses": {"mit", "apache-2.0"}
# }
```

### 3. Extract Entity Metadata
```python
# Download and persist metadata for each entity type
output_paths = enrichment.extract_related_entities(
    related_entities,
    threads=4
)

# Result:
# {
#     "datasets": Path("/data/raw/hf/datasets/<timestamp>_datasets.json"),
#     "articles": Path("/data/raw/hf/articles/<timestamp>_articles.json"),
#     "base_models": Path("/data/raw/hf/base_models/<timestamp>_base_models.json"),
#     "keywords": Path("/data/raw/hf/keywords/<timestamp>_keywords.json"),
#     "licenses": Path("/data/raw/hf/licenses/<timestamp>_licenses.json")
# }
```

### 4. Complete Enrichment (One-Step)
```python
# Or do it all in one call:
output_paths = enrichment.enrich_from_models_json(
    models_json_path="/data/raw/hf/2025-10-13_12-00-00_hf_models.json",
    entity_types=None,  # None = all types
    threads=4
)
```

## Dagster Assets

The HF extraction is exposed as Dagster assets:

### `hf_raw_models`
Extracts raw HF model metadata.

**Configuration (env vars):**
- `HF_NUM_MODELS` (default: 50)
- `HF_UPDATE_RECENT` (default: true)
- `HF_THREADS` (default: 4)

**Output:** Path to models JSON

### `hf_enriched_entities`
Depends on `hf_raw_models`. Identifies and extracts related entities.

**Configuration (env vars):**
- `HF_ENRICHMENT_THREADS` (default: 4)

**Output:** Dict mapping entity type to JSON path

## Adding New Entity Types

To add a new entity identifier:

1. Create a new identifier class in `entity_identifiers/`:

```python
# entity_identifiers/contributor_identifier.py
from .base import EntityIdentifier
import pandas as pd

class ContributorIdentifier(EntityIdentifier):
    @property
    def entity_type(self) -> str:
        return "contributors"
    
    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        contributors = set()
        for _, row in models_df.iterrows():
            author = row.get("author")
            if author:
                contributors.add(author)
        return contributors
```

2. Register it in `hf_enrichment.py`:

```python
from .entity_identifiers import ContributorIdentifier

class HFEnrichment:
    def __init__(self, ...):
        self.identifiers = {
            ...
            "contributors": ContributorIdentifier(),
        }
```

3. Add extraction logic in `extract_related_entities()`:

```python
elif entity_type == "contributors":
    # Fetch contributor metadata from HF or other sources
    df = self._fetch_contributor_metadata(list(entity_ids))
    output_dir = output_base / "contributors"
```

## Data Output Structure

All extracted data is saved under `/data/raw/hf/`:

```
/data/raw/hf/
├── 2025-10-13_12-00-00_hf_models.json      # Raw models
├── datasets/
│   └── 2025-10-13_12-05-00_datasets.json
├── articles/
│   └── 2025-10-13_12-05-00_articles.json
├── base_models/
│   └── 2025-10-13_12-05-00_base_models.json
├── keywords/
│   └── 2025-10-13_12-05-00_keywords.json
└── licenses/
    └── 2025-10-13_12-05-00_licenses.json
```

## Dependencies

Required Python packages:
- `datasets` - HuggingFace datasets library
- `huggingface_hub` - HF Hub API client
- `arxiv` - arXiv API client
- `spdx-lookup` - SPDX license metadata
- `pandas` - Data manipulation

See `pyproject.toml` for version constraints.

