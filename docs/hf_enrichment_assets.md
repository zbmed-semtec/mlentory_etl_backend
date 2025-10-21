# HuggingFace Enrichment Assets

## Overview

The HF enrichment pipeline is now broken down into individual Dagster assets for each entity type, allowing for:
- **Independent execution**: Each entity type can be processed separately
- **Clear dependencies**: Assets explicitly declare their dependencies
- **Better observability**: Track progress of each enrichment stage independently
- **Easier debugging**: Isolate issues to specific entity types

## Asset Dependency Graph

```
hf_raw_models (group: hf)
    │
    ├─► hf_identified_datasets ──► hf_enriched_datasets
    │                                      │
    ├─► hf_identified_articles ──► hf_enriched_articles
    │
    ├─► hf_identified_base_models ──► hf_enriched_base_models
    │                                  (depends on hf_enriched_datasets)
    ├─► hf_identified_keywords ──► hf_enriched_keywords
    │
    └─► hf_identified_licenses ──► hf_enriched_licenses
```

## Asset Groups

### `hf` Group
- **hf_raw_models**: Extracts raw model metadata from HuggingFace

### `hf_enrichment` Group
All enrichment assets are in this group for better organization.

#### Identification Assets (Lightweight)
These assets parse the models JSON and identify entity references:

1. **hf_identified_datasets**: Identifies dataset references from model tags
2. **hf_identified_articles**: Identifies arXiv article IDs from model tags
3. **hf_identified_base_models**: Identifies base model references
4. **hf_identified_keywords**: Extracts keywords, tags, pipeline_tag, library_name
5. **hf_identified_licenses**: Identifies license IDs from model metadata

#### Enrichment Assets (Heavy I/O)
These assets fetch actual metadata from HuggingFace/arXiv:

1. **hf_enriched_datasets**: Downloads dataset metadata
2. **hf_enriched_articles**: Downloads arXiv article metadata
3. **hf_enriched_base_models**: Downloads base model metadata (depends on datasets)
4. **hf_enriched_keywords**: Downloads keyword/tag metadata
5. **hf_enriched_licenses**: Downloads license metadata

## Dependencies Between Entities

### Base Models → Datasets
`hf_enriched_base_models` depends on `hf_enriched_datasets` because:
- Base models may reference the same datasets as the original models
- We want to ensure dataset metadata is available before processing base models
- This creates a natural ordering for the enrichment pipeline

### Future Dependencies
As the pipeline evolves, you can add more cross-entity dependencies:
- Articles might reference datasets
- Keywords might be extracted from articles
- Licenses might have relationships to specific model types

## Configuration

All enrichment assets use the `HFEnrichmentConfig` for thread configuration:

```python
@dataclass
class HFEnrichmentConfig:
    threads: int = int(os.getenv("HF_ENRICHMENT_THREADS", "4"))
```

Set `HF_ENRICHMENT_THREADS` environment variable to control parallelism.

## Running the Pipeline

### Run all enrichment assets
```bash
dagster asset materialize --select "hf_enrichment/*"
```

### Run specific entity type
```bash
# Just datasets
dagster asset materialize --select "hf_identified_datasets hf_enriched_datasets"

# Just articles
dagster asset materialize --select "hf_identified_articles hf_enriched_articles"
```

### Run with dependencies
```bash
# This will automatically run hf_raw_models first
dagster asset materialize --select "hf_enriched_datasets+"
```

## Output Format

All enriched assets return either:
- **Identification assets**: `Set[str]` - Set of entity IDs
- **Enrichment assets**: `str` - Path to the saved JSON file (or empty string if no entities)

Empty string is returned when there are no entities to extract, making downstream assets safe to run.

