# HuggingFace Enrichment Assets

## Overview

The HF enrichment pipeline is now broken down into individual Dagster assets for each entity type, allowing for:
- **Independent execution**: Each entity type can be processed separately
- **Clear dependencies**: Assets explicitly declare their dependencies
- **Better observability**: Track progress of each enrichment stage independently
- **Easier debugging**: Isolate issues to specific entity types
- **Run-grouped outputs**: All files from a single materialization are stored in the same timestamped folder

## Output Organization

All assets from a single Dagster run are saved together in a shared folder:

```
/data/raw/hf/
  ├── 2025-10-21_14-30-45_a1b2c3d4/    # Run from timestamp + run_id
  │   ├── hf_models.json
  │   ├── hf_datasets_specific.json
  │   ├── arxiv_articles.json
  │   ├── hf_models_specific.json      # base_models
  │   ├── keywords.json
  │   └── licenses.json
  └── 2025-10-21_16-15-22_e5f6g7h8/    # Different run
      ├── hf_models.json
      └── ...
```

This makes it easy to:
- Track which files belong to the same extraction run
- Compare outputs across different runs
- Clean up or archive complete runs

## Asset Dependency Graph

```
hf_run_folder (group: hf)
    │
    └─► hf_raw_models (group: hf)
           │
           ├─► hf_identified_datasets ──► hf_enriched_datasets
           │                                      
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
- **hf_run_folder**: Creates a unique run folder for this materialization (e.g., `2025-10-21_14-30-45_a1b2c3d4/`)
- **hf_raw_models**: Extracts raw model metadata from HuggingFace and saves to the run folder

### `hf_enrichment` Group
All enrichment assets are in this group for better organization.

#### Identification Assets (Lightweight)
These assets parse the models JSON and identify entity references. They receive the run folder path and pass it downstream:

1. **hf_identified_datasets**: Identifies dataset references from model tags
2. **hf_identified_articles**: Identifies arXiv article IDs from model tags
3. **hf_identified_base_models**: Identifies base model references
4. **hf_identified_keywords**: Extracts keywords, tags, pipeline_tag, library_name
5. **hf_identified_licenses**: Identifies license IDs from model metadata

#### Enrichment Assets (Heavy I/O)
These assets fetch actual metadata from HuggingFace/arXiv and save to the run folder:

1. **hf_enriched_datasets**: Downloads dataset metadata → `hf_datasets_specific.json`
2. **hf_enriched_articles**: Downloads arXiv article metadata → `arxiv_articles.json`
3. **hf_enriched_base_models**: Downloads base model metadata → `hf_models_specific.json`
4. **hf_enriched_keywords**: Downloads keyword/tag metadata → `keywords.json`
5. **hf_enriched_licenses**: Downloads license metadata → `licenses.json`

## How Run Folder Propagation Works

The run folder is created once and propagated through the asset graph:

1. **hf_run_folder** creates a unique folder (e.g., `2025-10-21_14-30-45_a1b2c3d4/`)
2. **hf_raw_models** receives the folder path and returns `(models_json_path, run_folder)`
3. **All identification assets** receive `models_data=(models_json_path, run_folder)` and return `(entity_ids, run_folder)`
4. **All enrichment assets** receive `entity_data=(entity_ids, run_folder)` and save files to that folder

This design ensures:
- No context dependency (pure data flow)
- All outputs from one run grouped together
- Run folder path is explicit in the asset signatures

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

Asset return values:
- **hf_run_folder**: `str` - Path to the run folder
- **hf_raw_models**: `Tuple[str, str]` - (models_json_path, run_folder)
- **Identification assets**: `Tuple[Set[str], str]` - (entity_ids, run_folder)
- **Enrichment assets**: `str` - Path to the saved JSON file (or empty string if no entities)

Empty string is returned when there are no entities to extract, making downstream assets safe to run.

## Implementation Notes

### Why Tuples?
Assets return tuples to propagate the run folder through the graph. This allows:
- Each asset to know where to save its outputs
- No need for Dagster execution context
- Pure data flow that's easy to test

### File Naming
Files are saved with clean, consistent names in the run folder:
- `hf_models.json` (raw models)
- `hf_datasets_specific.json` (datasets)
- `arxiv_articles.json` (articles)
- `hf_models_specific.json` (base models)
- `keywords.json` (keywords)
- `licenses.json` (licenses)

No timestamps in filenames since the folder already has the timestamp.

