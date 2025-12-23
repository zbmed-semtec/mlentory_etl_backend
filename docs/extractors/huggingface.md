# HuggingFace Extractor

Complete guide to extracting ML model metadata from HuggingFace Hub, the largest repository of machine learning models.

---

## HuggingFace Hub Overview

**HuggingFace Hub** is the largest platform for sharing and discovering ML models, datasets, and papers. It hosts millions of models across various domains:
- **Natural Language Processing:** BERT, GPT, T5, and thousands more
- **Computer Vision:** Vision Transformers, ResNet, and image models
- **Audio:** Speech recognition and generation models
- **Multimodal:** Models that work with multiple data types

### Why Extract from HuggingFace?

- **Largest Repository:** Millions of models available
- **Rich Metadata:** Model cards, datasets, papers, licenses
- **Active Community:** Constantly updated with new models
- **Standardized Format:** Consistent API and data structure
- **Related Entities:** Models reference datasets, papers, base models

---

## Extraction Modes

The HuggingFace extractor supports two complementary modes that work together:

### 1. Latest N Models (Automatic)

Extracts the most recent models from HuggingFace Hub.

**How it works:**
- Uses HuggingFace's model cards dataset
- Fetches latest models sorted by modification date
- Optionally updates with recently modified models
- Configurable number of models to extract

**Configuration:**
- `HF_NUM_MODELS`: Number of models to extract (default: 50)
- `HF_UPDATE_RECENT`: Prioritize recently updated models (default: true)
- `HF_THREADS`: Parallel threads for extraction (default: 4)

**Use case:**
- Discover new models
- Keep repository up-to-date
- Extract trending models

### 2. File-based Models (Targeted)

Extracts specific models listed in a configuration file.

**How it works:**
- Reads model IDs from `/data/refs/hf_model_ids.txt`
- Extracts metadata for each listed model
- Works alongside latest models extraction
- Results are automatically merged

**Configuration:**
- `HF_MODELS_FILE_PATH`: Path to model IDs file (default: `/data/refs/hf_model_ids.txt`)
- `HF_THREADS`: Parallel threads for extraction (default: 4)

**Use case:**
- Extract specific models of interest
- Reproduce specific model sets
- Test with known models
- Extract models not in latest N

### Combined Mode (Recommended)

Both modes run in parallel and results are automatically merged:

```
Latest N Models (50 models)
    +
File-based Models (20 models)
    ↓
Merged Results (~70 unique models, duplicates removed)
```

**Benefits:**
- Comprehensive coverage (latest + specific)
- No duplicates (automatic deduplication)
- Flexible (can use either or both modes)

---

## File Format for Model IDs

Create a file at `/data/refs/hf_model_ids.txt` with one model ID per line:

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

# Full URLs are also supported (automatically converted)
https://huggingface.co/bert-base-uncased
```

**Rules:**
- One model ID per line
- Comments start with `#`
- Empty lines are ignored
- Full URLs are automatically converted to model IDs
- Supports both `organization/model` and `model` formats

---

## Extraction Process

### Step 1: Extract Raw Models

**What happens:**
1. Connect to HuggingFace Hub API
2. Fetch model metadata (name, author, tasks, description, etc.)
3. Handle rate limiting and pagination
4. Store raw JSON files

**Output:**
- `/data/raw/hf/<timestamp>_<uuid>/hf_models.json`

**Example data:**
```json
[
  {
    "modelId": "bert-base-uncased",
    "author": "google",
    "pipeline_tag": "fill-mask",
    "tags": ["pytorch", "transformers", "bert"],
    "downloads": 5000000,
    "library_name": "transformers",
    "last_modified": "2024-01-15T10:30:00Z"
  }
]
```

### Step 2: Identify Related Entities

**What happens:**
1. Scan model metadata for references
2. Extract dataset names, arXiv IDs, base model references
3. Identify keywords, licenses, languages, tasks
4. Build entity ID sets

**Entity Types Identified:**
- **Datasets:** Training/evaluation datasets (e.g., "squad", "glue")
- **Articles:** arXiv papers (e.g., "2106.09685")
- **Base Models:** Models this was fine-tuned from (e.g., "bert-base-uncased")
- **Keywords:** Tags and keywords (e.g., "nlp", "pytorch")
- **Licenses:** License identifiers (e.g., "mit", "apache-2.0")
- **Languages:** Natural languages (e.g., "en", "de")
- **Tasks:** ML tasks (e.g., "fill-mask", "text-classification")

**Output:**
- Entity ID mappings stored in memory
- Used for enrichment step

### Step 3: Enrich Related Entities

**What happens:**
1. Take identified entity IDs
2. Fetch full metadata from HuggingFace/arXiv APIs
3. Store enriched entity data

**Example:**
- Identified "squad" dataset → Fetch full SQuAD metadata → Store in `hf_datasets_specific.json`
- Identified "2106.09685" paper → Fetch from arXiv API → Store in `arxiv_articles.json`

**Output:**
- `/data/raw/hf/<timestamp>_<uuid>/hf_datasets_specific.json`
- `/data/raw/hf/<timestamp>_<uuid>/arxiv_articles.json`
- `/data/raw/hf/<timestamp>_<uuid>/keywords.json`
- `/data/raw/hf/<timestamp>_<uuid>/licenses.json`
- And more...

### Step 4: Recursive Base Model Enrichment

**What happens:**
1. Extract base model references from models
2. Fetch metadata for base models
3. Check base models for further base model references
4. Repeat up to `HF_BASE_MODEL_ITERATIONS` times

**Example:**
```
Model A → based_on → Model B
Model B → based_on → Model C
Model C → based_on → Model D
```

With `HF_BASE_MODEL_ITERATIONS=2`, we extract:
- Iteration 1: Model B, Model C
- Iteration 2: Model D

**Configuration:**
- `HF_BASE_MODEL_ITERATIONS`: Number of iterations (default: 1)
- Set to `0` to disable recursive enrichment

---

## Architecture

The HuggingFace extractor uses a **modular architecture**:

### Client Layer

Low-level API interactions:

```
clients/
├── models_client.py      # Model metadata from HF Hub
├── datasets_client.py    # Dataset metadata (Croissant format)
├── arxiv_client.py      # arXiv paper metadata
├── license_client.py    # SPDX license metadata
├── keyword_client.py    # Keyword/tag metadata
├── languages_client.py  # Language metadata
└── tasks_client.py      # ML task metadata
```

**Responsibilities:**
- Make HTTP requests to APIs
- Handle authentication (API tokens)
- Parse API responses
- Manage rate limiting

### Entity Identifiers

Extract entity references from models:

```
entity_identifiers/
├── base.py                 # Abstract interface
├── dataset_identifier.py  # Extract dataset references
├── article_identifier.py   # Extract arXiv IDs
├── base_model_identifier.py # Extract base model refs
├── keyword_identifier.py   # Extract keywords/tags
├── license_identifier.py   # Extract license IDs
├── languages_identifier.py # Extract language codes
└── tasks_identifier.py     # Extract ML tasks
```

**How they work:**
- Scan model metadata (description, tags, model card)
- Use regex patterns and heuristics
- Extract entity IDs (dataset names, arXiv IDs, etc.)
- Return sets of unique entity IDs

### Enrichment Layer

Orchestrates entity identification and extraction:

```python
from etl_extractors.hf import HFEnrichment

enrichment = HFEnrichment()

# Identify entities
related_entities = enrichment.identify_related_entities(models_df)

# Extract entity metadata
output_paths = enrichment.extract_related_entities(related_entities)
```

### High-Level Extractor

Coordinates the entire extraction process:

```python
from etl_extractors.hf import HFExtractor

extractor = HFExtractor()

# Extract models
models_df, json_path = extractor.extract_models(
    num_models=50,
    update_recent=True,
    threads=4
)
```

---

## Dagster Assets

The HuggingFace extraction is exposed as Dagster assets for orchestration:

### Extraction Assets

**`hf_run_folder`**
- Creates unique run folder for this materialization
- Returns: Path to run folder (e.g., `/data/1_raw/hf/2025-01-15_12-00-00_abc123/`)

**`hf_raw_models_latest`**
- Extracts latest N models from HuggingFace Hub
- Depends on: `hf_run_folder`
- Returns: Tuple of (DataFrame, run_folder)

**`hf_raw_models_from_file`**
- Extracts models from configuration file
- Depends on: `hf_run_folder`
- Returns: Tuple of (DataFrame, run_folder) or (None, run_folder) if no file

**`hf_raw_models`**
- Merges models from both sources
- Depends on: `hf_raw_models_latest`, `hf_raw_models_from_file`
- Removes duplicates based on model ID
- Returns: Tuple of (merged_json_path, run_folder)

**`hf_add_ancestor_models`**
- Recursively extracts base models
- Depends on: `hf_raw_models`
- Returns: Tuple of (models_with_ancestors_json_path, run_folder)

### Enrichment Assets

**Identification Assets:**
- `hf_identified_datasets` - Identifies dataset references
- `hf_identified_articles` - Identifies arXiv paper references
- `hf_identified_base_models` - Identifies base model references
- `hf_identified_keywords` - Identifies keywords/tags
- `hf_identified_licenses` - Identifies license references
- `hf_identified_languages` - Identifies language codes
- `hf_identified_tasks` - Identifies ML task references

**Enrichment Assets:**
- `hf_enriched_datasets` - Fetches full dataset metadata
- `hf_enriched_articles` - Fetches full paper metadata from arXiv
- `hf_enriched_base_models` - Fetches base model metadata
- `hf_enriched_keywords` - Fetches keyword metadata
- `hf_enriched_licenses` - Fetches license metadata
- `hf_enriched_languages` - Fetches language metadata
- `hf_enriched_tasks` - Fetches task metadata

### Asset Dependency Graph

```
hf_run_folder
    ↓
    ├─→ hf_raw_models_latest
    └─→ hf_raw_models_from_file
            ↓
        hf_raw_models (merges both)
            ↓
        hf_add_ancestor_models
            ↓
            ├─→ hf_identified_datasets → hf_enriched_datasets
            ├─→ hf_identified_articles → hf_enriched_articles
            ├─→ hf_identified_base_models → hf_enriched_base_models
            ├─→ hf_identified_keywords → hf_enriched_keywords
            ├─→ hf_identified_licenses → hf_enriched_licenses
            ├─→ hf_identified_languages → hf_enriched_languages
            └─→ hf_identified_tasks → hf_enriched_tasks
```

---

## Configuration

All configuration is via environment variables:

### Extraction Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HF_NUM_MODELS` | Number of latest models to extract | `50` |
| `HF_UPDATE_RECENT` | Prioritize recently updated models | `true` |
| `HF_THREADS` | Parallel threads for model extraction | `4` |
| `HF_MODELS_FILE_PATH` | Path to model IDs file | `/data/refs/hf_model_ids.txt` |
| `HF_TOKEN` | HuggingFace API token (optional) | (none) |

### Enrichment Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HF_ENRICHMENT_THREADS` | Threads for enrichment tasks | `4` |
| `HF_BASE_MODEL_ITERATIONS` | Recursive base model depth | `1` |

### API Token (Optional but Recommended)

**Why use an API token?**
- Higher rate limits (more requests per hour)
- Access to private models (if you have access)
- Better reliability and performance

**How to get a token:**
1. Go to https://huggingface.co/settings/tokens
2. Create a new token (read access is sufficient)
3. Set `HF_TOKEN` environment variable

**Without token:**
- Works for public models
- Lower rate limits
- May hit rate limits with large extractions

---

## Output Structure

All extracted data is saved in run-specific folders:

```
/data/raw/hf/
└── 2025-01-15_12-00-00_abc123/    # Run folder (timestamp + UUID)
    ├── hf_models.json              # Merged models (latest + file-based)
    ├── hf_models_with_ancestors.json # Models + base models
    ├── hf_datasets_specific.json   # Enriched datasets
    ├── arxiv_articles.json         # Enriched papers
    ├── keywords.json               # Enriched keywords
    ├── licenses.json               # Enriched licenses
    ├── languages.json              # Enriched languages
    └── tasks.json                  # Enriched tasks
```

**Benefits of run folders:**
- All outputs from one run grouped together
- Easy to track and compare runs
- No file conflicts between runs
- Easy cleanup or archiving

---

## Usage Examples

### Via Dagster UI

1. Open Dagster UI (http://localhost:3000)
2. Navigate to Assets tab
3. Find `hf_raw_models` asset
4. Click "Materialize"
5. Watch progress in real-time

### Via Command Line

**Extract latest models:**
```bash
dagster asset materialize -m etl.repository -a hf_raw_models
```

**Extract with dependencies:**
```bash
# This automatically runs hf_run_folder, hf_raw_models_latest, etc.
dagster asset materialize -m etl.repository -a hf_enriched_datasets+
```

**Extract all HF assets:**
```bash
dagster asset materialize -m etl.repository --select "hf*"
```

### Programmatic Usage

**Standalone (without Dagster):**
```python
from etl_extractors.hf import HFExtractor, HFEnrichment

# Extract models
extractor = HFExtractor()
models_df, models_path = extractor.extract_models(
    num_models=50,
    update_recent=True,
    threads=4
)

# Enrich entities
enrichment = HFEnrichment(extractor=extractor)
output_paths = enrichment.enrich_from_models_json(
    models_json_path=models_path,
    entity_types=None,  # All entity types
    threads=4
)
```

---

## Entity Enrichment Details

### Datasets

**Source:** HuggingFace Hub Datasets API

**What's extracted:**
- Dataset metadata (name, description, size)
- Croissant ML format (structured dataset description)
- Dataset statistics and splits

**Example:**
```json
{
  "id": "squad",
  "name": "SQuAD",
  "description": "Stanford Question Answering Dataset",
  "splits": ["train", "validation"],
  "downloads": 100000
}
```

### Articles (Papers)

**Source:** arXiv API

**What's extracted:**
- Paper metadata (title, authors, abstract)
- Publication date
- Categories and subjects

**Example:**
```json
{
  "arxiv_id": "1810.04805",
  "title": "BERT: Pre-training of Deep Bidirectional Transformers",
  "authors": ["Jacob Devlin", "Ming-Wei Chang", ...],
  "published": "2018-10-11"
}
```

### Base Models

**Source:** HuggingFace Hub API

**What's extracted:**
- Base model metadata
- Recursive extraction (follows base model chain)
- Creates model lineage

**Example:**
```
Model: bert-large-finetuned-squad
  ↓ based_on
Model: bert-large-uncased
  ↓ based_on
Model: bert-base-uncased
```

### Keywords

**Source:** Extracted from model tags and descriptions

**What's extracted:**
- Keywords/tags mentioned in models
- Organized by category

### Licenses

**Source:** SPDX License List + HuggingFace metadata

**What's extracted:**
- License identifiers (MIT, Apache-2.0, etc.)
- License metadata from SPDX

### Languages

**Source:** Extracted from model metadata + pycountry

**What's extracted:**
- Language codes (ISO 639-1)
- Language names and metadata

### Tasks

**Source:** HuggingFace Tasks API

**What's extracted:**
- ML task definitions
- Task categories and descriptions

---

## Troubleshooting

### Rate Limit Errors

**Problem:** Too many API requests

**Solutions:**
- Use HuggingFace API token (`HF_TOKEN`)
- Reduce `HF_THREADS` (fewer parallel requests)
- Reduce `HF_NUM_MODELS` (extract fewer models)
- Add delays between requests

### Missing Models

**Problem:** Some models not found

**Solutions:**
- Check model IDs are correct
- Verify models exist on HuggingFace Hub
- Check API token has access (for private models)
- Review logs for specific errors

### Entity Enrichment Failures

**Problem:** Some entities fail to enrich

**Solutions:**
- Check entity IDs are valid
- Verify APIs are accessible
- Review logs for specific errors
- Partial failures are OK (continues with successful entities)

### File Not Found Errors

**Problem:** Model IDs file not found

**Solutions:**
- Check `HF_MODELS_FILE_PATH` is correct
- Create file if it doesn't exist
- Ensure file has correct permissions
- File is optional (extraction works without it)

---

## Performance Tips

### Optimize Thread Count

- **Too few threads:** Slow extraction
- **Too many threads:** Rate limit errors
- **Recommended:** Start with 4, adjust based on rate limits

### Use API Token

- Significantly higher rate limits
- More reliable extraction
- Access to private models

### Incremental Extraction

- Only extract new/updated models
- Use `HF_UPDATE_RECENT=true` to prioritize recent models
- Reduces extraction time

### Batch Processing

- Process models in batches
- Extract related entities separately
- Better error isolation

---

## Key Takeaways

1. **Two extraction modes** (latest N + file-based) work together
2. **Entity enrichment** discovers and fetches related entities
3. **Modular architecture** makes it easy to understand and extend
4. **Dagster assets** orchestrate the extraction pipeline
5. **Run folders** organize outputs from single extraction runs
6. **Recursive base models** follow model lineage automatically

---

## Next Steps

- See [OpenML Extractor](openml.md) - ML experiments platform
- Check [AI4Life Extractor](ai4life.md) - Biomedical AI models
- Learn [Adding a New Extractor](adding-extractor.md) - How to add new sources
- Explore [Transformers](../transformers/overview.md) - How extracted data is transformed

---

## Resources

- **HuggingFace Hub:** [https://huggingface.co/](https://huggingface.co/)
- **HuggingFace API Docs:** [https://huggingface.co/docs/hub/api](https://huggingface.co/docs/hub/api)
- **HuggingFace Datasets:** [https://huggingface.co/docs/datasets/](https://huggingface.co/docs/datasets/)
- **arXiv API:** [https://arxiv.org/help/api](https://arxiv.org/help/api)
