# HuggingFace Extraction Modes

## Overview

The HuggingFace extraction pipeline now supports two complementary extraction modes that can be used together to gather model metadata:

1. **Latest N Models**: Automatically extract the most recent models from HuggingFace Hub
2. **File-based Models**: Extract specific models listed in a configuration file

Both modes run in parallel and their results are automatically merged, with duplicate models removed.

## Architecture

### Dagster Asset Flow

```
hf_run_folder
    ├── hf_raw_models_latest (extracts latest N models)
    └── hf_raw_models_from_file (extracts models from file)
            └── hf_raw_models (merges both sources)
                    ├── hf_identified_datasets
                    ├── hf_identified_articles
                    ├── hf_identified_base_models
                    ├── hf_identified_keywords
                    └── hf_identified_licenses
```

### Assets

#### 1. `hf_raw_models_latest`
- **Purpose**: Extract the latest N models from HuggingFace Hub
- **Configuration**: 
  - `HF_NUM_MODELS`: Number of models to extract (default: 50)
  - `HF_UPDATE_RECENT`: Whether to prioritize recently updated models (default: true)
  - `HF_THREADS`: Parallel threads for extraction (default: 4)
- **Returns**: DataFrame of model metadata + run folder path
- **Group**: `hf`

#### 2. `hf_raw_models_from_file`
- **Purpose**: Extract specific models listed in a configuration file
- **Configuration**:
  - `HF_MODELS_FILE_PATH`: Path to model IDs file (default: `/data/config/hf_model_ids.txt`)
  - `HF_THREADS`: Parallel threads for extraction (default: 4)
- **File Format**: One model ID per line, supports comments (#) and empty lines
- **Returns**: DataFrame of model metadata + run folder path (or None if no models found)
- **Group**: `hf`

#### 3. `hf_raw_models` (Merge Asset)
- **Purpose**: Combine models from both sources and remove duplicates
- **Inputs**: Results from both `hf_raw_models_latest` and `hf_raw_models_from_file`
- **Deduplication**: Based on model ID (uses `id` or `modelId` column)
- **Returns**: Path to merged JSON file + run folder path
- **Group**: `hf`

## Usage

### Basic Setup

1. **Create model IDs file** (optional):
   ```bash
   cd /data/config
   cp hf_model_ids.txt.example hf_model_ids.txt
   ```

2. **Add model IDs** to the file:
   ```
   # Example models
   bert-base-uncased
   gpt2
   facebook/bart-large
   google/flan-t5-base
   ```

3. **Configure environment variables** (optional):
   ```bash
   export HF_NUM_MODELS=100
   export HF_MODELS_FILE_PATH=/data/config/hf_model_ids.txt
   export HF_THREADS=8
   ```

### Scenarios

#### Scenario 1: Latest Models Only
If the model IDs file doesn't exist or is empty, only the latest N models will be extracted:
- `hf_raw_models_latest` → extracts 50 models (or HF_NUM_MODELS)
- `hf_raw_models_from_file` → returns None (skipped)
- `hf_raw_models` → saves latest models only

#### Scenario 2: File-based Models Only
Set `HF_NUM_MODELS=0` to skip latest extraction and only use file-based:
- `hf_raw_models_latest` → extracts 0 models (empty DataFrame)
- `hf_raw_models_from_file` → extracts models from file
- `hf_raw_models` → saves file-based models only

#### Scenario 3: Combined (Recommended)
Use both modes to get comprehensive coverage:
- `hf_raw_models_latest` → extracts latest 50 models
- `hf_raw_models_from_file` → extracts 20 specific models
- `hf_raw_models` → merges both, removes duplicates → ~70 unique models

## Recursive Base Model Enrichment

The `hf_enriched_base_models` asset now performs iterative enrichment to follow
base-model references discovered during extraction. Each iteration downloads
metadata for newly discovered base models and inspects the results for further
references, avoiding duplicate downloads.

- Controlled by the `HF_BASE_MODEL_ITERATIONS` environment variable (default: 1)
- Set to `0` to disable recursive base-model lookups entirely
- Each iteration reuses `HF_THREADS` for parallel requests and deduplicates
  results before persisting `hf_models_specific.json`

## File Format

### Model IDs File (`hf_model_ids.txt`)

```
# Comments start with # and are ignored
# Empty lines are also ignored

# Format: organization/model-name or just model-name
bert-base-uncased
gpt2

# You can organize by category
# Vision Models
google/vit-base-patch16-224
microsoft/resnet-50

# Language Models
facebook/bart-large
google/flan-t5-base
meta-llama/Llama-2-7b-hf
```

## Environment Variables Reference

| Variable | Description | Default |
|----------|-------------|---------|
| `HF_NUM_MODELS` | Number of latest models to extract | `50` |
| `HF_UPDATE_RECENT` | Prioritize recently updated models | `true` |
| `HF_THREADS` | Parallel threads for model extraction | `4` |
| `HF_MODELS_FILE_PATH` | Path to model IDs file | `/data/config/hf_model_ids.txt` |
| `HF_ENRICHMENT_THREADS` | Threads for enrichment tasks | `4` |
| `HF_BASE_MODEL_ITERATIONS` | Iterations for recursive base model enrichment | `1` |
