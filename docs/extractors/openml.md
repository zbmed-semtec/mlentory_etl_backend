# OpenML Extractor

Complete guide to extracting ML model metadata from OpenML, a platform for machine learning experiments, datasets, and model flows.

---

## OpenML Platform Overview

**OpenML** is an open platform for sharing and organizing ML experiments. It provides:

- **Runs:** Individual ML experiments with results
- **Flows:** ML algorithms/models (reusable across experiments)
- **Datasets:** Training and test datasets
- **Tasks:** ML problem definitions (classification, regression, etc.)

### Why Extract from OpenML?

- **Experiment Data:** Real ML experiment results and performance metrics
- **Reproducibility:** Detailed experiment configurations
- **Model Flows:** Reusable ML algorithm definitions
- **Dataset Metadata:** Rich dataset descriptions and statistics
- **Task Definitions:** Standardized ML problem descriptions

### OpenML Data Model

**Runs** are the central entity:
- Each run represents one ML experiment
- A run uses a **flow** (model/algorithm) on a **dataset** for a **task**
- Runs contain performance metrics and configurations

**Example:**
```
Run #12345
  ├── Flow: Random Forest (model/algorithm)
  ├── Dataset: iris (training data)
  ├── Task: Classification (problem type)
  └── Results: Accuracy = 0.95
```

---

## Extraction Process

### Step 1: Extract Runs

**What happens:**
1. Connect to OpenML Python API
2. Fetch N most recent runs
3. Extract run metadata (flow ID, dataset ID, task ID, results)
4. Store raw JSON files

**Output:**
- `/data/raw/openml/<timestamp>_<uuid>/runs.json`

**Example data:**
```json
[
  {
    "run_id": 12345,
    "flow_id": 6789,
    "dataset_id": 61,
    "task_id": 1,
    "setup_string": "weka.RandomForest -I 100",
    "upload_time": "2024-01-15T10:30:00Z"
  }
]
```

### Step 2: Identify Related Entities

**What happens:**
1. Scan runs to identify unique datasets, flows, and tasks
2. Extract entity IDs from run metadata
3. Build entity ID sets

**Entity Types Identified:**
- **Datasets:** Training/test datasets referenced in runs
- **Flows:** ML algorithms/models used in runs
- **Tasks:** ML problem definitions

**Example:**
```
Runs contain:
  - dataset_id: 61 (iris)
  - flow_id: 6789 (Random Forest)
  - task_id: 1 (Classification)

Identified entities:
  - Datasets: {61, 62, 63}
  - Flows: {6789, 6790, 6791}
  - Tasks: {1, 2, 3}
```

### Step 3: Extract Related Entities

**What happens:**
1. Take identified entity IDs
2. Fetch full metadata from OpenML API
3. Optionally scrape additional statistics from website
4. Store enriched entity data

**Output:**
- `/data/raw/openml/<timestamp>_<uuid>/datasets.json`
- `/data/raw/openml/<timestamp>_<uuid>/flows.json`
- `/data/raw/openml/<timestamp>_<uuid>/tasks.json`

---

## Extraction Methods

### 1. API-based Extraction (Primary)

**How it works:**
- Uses OpenML Python package (`openml` library)
- Direct API calls to OpenML server
- Fast and reliable
- Handles pagination automatically

**What's extracted:**
- Run metadata (flow, dataset, task IDs, results)
- Dataset metadata (name, description, features, instances)
- Flow metadata (algorithm name, parameters, version)
- Task metadata (task type, evaluation measures)

### 2. Web Scraping (Optional)

**How it works:**
- Selenium-based browser automation
- Scrapes dataset statistics from OpenML website
- Used when data isn't available via API

**What's scraped:**
- Dataset statistics (downloads, likes, issues)
- Additional metadata not in API

**When to use:**
- Need dataset statistics (downloads, likes)
- Data not available via API
- ⚠️ **Warning:** Much slower than API extraction

**Enable scraping:**
```bash
OPENML_ENABLE_SCRAPING=true
```

**Limitations:**
- ⚠️ Very slow (browser automation)
- ⚠️ May break if website structure changes
- ⚠️ Requires Chrome/Chromium browser
- ⚠️ Can be unreliable

**Recommendation:** Only enable if you specifically need scraped statistics.

---

## Architecture

The OpenML extractor follows a modular architecture:

### Client Layer

Low-level API interactions:

```
clients/
├── openml_runs_client.py      # Fetches run metadata
├── openml_datasets_client.py  # Fetches dataset metadata
├── openml_flows_client.py      # Fetches flow (model) metadata
└── openml_tasks_client.py      # Fetches task metadata
```

**Responsibilities:**
- Make API calls via OpenML Python package
- Handle pagination
- Parse API responses
- Manage rate limiting

### Entity Identifiers

Extract entity references from runs:

```
entity_identifiers/
├── base.py                    # Abstract base class
├── dataset_identifier.py     # Identifies datasets from runs
├── flow_identifier.py        # Identifies flows from runs
└── task_identifier.py        # Identifies tasks from runs
```

**How they work:**
- Scan runs for dataset_id, flow_id, task_id
- Extract unique entity IDs
- Return sets of entity IDs

### Web Scraper (Optional)

Selenium-based scraping for additional data:

```
scrapers/
└── openml_web_scraper.py     # Scrapes dataset statistics
```

**Features:**
- Thread-safe browser pool
- Exponential backoff and retry logic
- Auto-disables on connection failures

### High-Level Extractor

Coordinates the extraction process:

```python
from etl_extractors.openml import OpenMLExtractor

extractor = OpenMLExtractor(enable_scraping=False)
runs_df, runs_path = extractor.extract_runs(
    num_instances=50,
    threads=4
)
```

---

## Dagster Assets

The OpenML extraction is exposed as Dagster assets:

### Extraction Assets

**`openml_run_folder`**
- Creates unique run folder for this materialization
- Returns: Path to run folder

**`openml_raw_runs`**
- Extracts runs from OpenML
- Depends on: `openml_run_folder`
- Returns: Tuple of (runs_json_path, run_folder)

### Enrichment Assets

**Identification Assets:**
- `openml_identified_datasets` - Identifies dataset references
- `openml_identified_flows` - Identifies flow references
- `openml_identified_tasks` - Identifies task references

**Enrichment Assets:**
- `openml_enriched_datasets` - Fetches full dataset metadata
- `openml_enriched_flows` - Fetches full flow metadata
- `openml_enriched_tasks` - Fetches full task metadata

### Asset Dependency Graph

```
openml_run_folder
    ↓
openml_raw_runs
    ↓
    ├─→ openml_identified_datasets → openml_enriched_datasets
    ├─→ openml_identified_flows → openml_enriched_flows
    └─→ openml_identified_tasks → openml_enriched_tasks
```

---

## Configuration

All configuration is via environment variables:

### Extraction Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENML_NUM_INSTANCES` | Number of runs to extract | `50` |
| `OPENML_OFFSET` | Pagination offset | `0` |
| `OPENML_THREADS` | Parallel threads for extraction | `4` |

### Enrichment Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENML_ENRICHMENT_THREADS` | Threads for entity extraction | `4` |
| `OPENML_ENABLE_SCRAPING` | Enable web scraping for stats | `false` |

### Web Scraping Configuration

When `OPENML_ENABLE_SCRAPING=true`:
- Uses Selenium browser automation
- Scrapes dataset statistics (downloads, likes, issues)
- Much slower than API extraction
- Requires Chrome/Chromium browser

---

## Output Structure

All extracted data is saved in run-specific folders:

```
/data/raw/openml/
└── 2025-01-15_12-00-00_abc123/    # Run folder
    ├── runs.json                   # Raw run metadata
    ├── datasets.json               # Enriched dataset metadata
    ├── flows.json                  # Enriched flow (model) metadata
    └── tasks.json                  # Enriched task metadata
```

### Metadata Format

OpenML extractor wraps fields with extraction metadata:

```json
{
  "dataset_id": [
    {
      "data": 61,
      "extraction_method": "openml_python_package",
      "confidence": 1.0,
      "extraction_time": "2025-01-15T12:00:00Z"
    }
  ],
  "downloads": [
    {
      "data": 15000,
      "extraction_method": "web_scraping",
      "confidence": 0.9,
      "extraction_time": "2025-01-15T12:05:00Z"
    }
  ]
}
```

**Benefits:**
- Track extraction method (API vs scraping)
- Confidence scores for data quality
- Provenance information

---

## Usage Examples

### Via Dagster UI

1. Open Dagster UI (http://localhost:3000)
2. Navigate to Assets tab
3. Find `openml_raw_runs` asset
4. Click "Materialize"
5. Watch progress in real-time

### Via Command Line

**Extract runs:**
```bash
dagster asset materialize -m etl.repository -a openml_raw_runs
```

**Extract with enrichment:**
```bash
dagster asset materialize -m etl.repository -a openml_enriched_datasets+
```

**Extract all OpenML assets:**
```bash
dagster asset materialize -m etl.repository --select "openml*"
```

### Programmatic Usage

**Standalone (without Dagster):**
```python
from etl_extractors.openml import OpenMLExtractor, OpenMLEnrichment

# Extract runs
extractor = OpenMLExtractor(enable_scraping=False)
runs_df, runs_path = extractor.extract_runs(
    num_instances=50,
    threads=4
)

# Enrich entities
enrichment = OpenMLEnrichment(extractor=extractor)
entity_paths = enrichment.enrich_from_runs_json(
    runs_path,
    threads=4
)
```

---

## Entity Details

### Runs

**What they represent:**
- Individual ML experiments
- Link flows (models) to datasets and tasks
- Contain performance metrics and configurations

**Key fields:**
- `run_id`: Unique run identifier
- `flow_id`: Algorithm/model used
- `dataset_id`: Dataset used
- `task_id`: Task/problem type
- `setup_string`: Algorithm configuration
- `upload_time`: When experiment was uploaded

### Datasets

**What they represent:**
- Training and test datasets
- Used in ML experiments

**Key fields:**
- `dataset_id`: Unique dataset identifier
- `name`: Dataset name
- `version`: Dataset version
- `status`: Dataset status (active, deactivated)
- `number_of_features`: Number of features
- `number_of_instances`: Number of instances
- `number_of_classes`: Number of classes (for classification)

**Optional scraped fields:**
- `downloads`: Number of downloads
- `likes`: Number of likes
- `issues`: Number of issues

### Flows (Models)

**What they represent:**
- ML algorithms/models
- Reusable across multiple experiments

**Key fields:**
- `flow_id`: Unique flow identifier
- `name`: Flow name
- `version`: Flow version
- `external_version`: External tool version
- `uploader`: Who uploaded the flow

### Tasks

**What they represent:**
- ML problem definitions
- Standardized task descriptions

**Key fields:**
- `task_id`: Unique task identifier
- `task_type`: Type of task (classification, regression, etc.)
- `evaluation_measure`: How to evaluate (accuracy, F1, etc.)

---

## Differences from HuggingFace

| Aspect | HuggingFace | OpenML |
|--------|-------------|--------|
| **Primary Entity** | Models | Runs (experiments) |
| **Data Model** | Model-centric | Experiment-centric |
| **Metadata** | Model cards, descriptions | Experiment results, metrics |
| **Enrichment** | Datasets, papers, base models | Datasets, flows, tasks |
| **Scraping** | Not used | Optional (for statistics) |
| **Use Case** | Model discovery | Experiment reproducibility |

---

## Troubleshooting

### API Connection Errors

**Problem:** Cannot connect to OpenML API

**Solutions:**
- Check internet connection
- Verify OpenML server is accessible
- Check firewall settings
- Review API rate limits

### Scraping Failures

**Problem:** Web scraping fails

**Solutions:**
- Ensure Chrome/Chromium is installed
- Check `OPENML_ENABLE_SCRAPING=true` is set
- Review browser logs
- Consider disabling scraping (use API only)

### Missing Entity Data

**Problem:** Some entities not found

**Solutions:**
- Verify entity IDs are valid
- Check OpenML server status
- Review logs for specific errors
- Partial failures are OK (continues with successful entities)

### Performance Issues

**Problem:** Extraction is slow

**Solutions:**
- Disable web scraping (if enabled)
- Reduce `OPENML_NUM_INSTANCES`
- Increase `OPENML_THREADS` (if not rate-limited)
- Process in smaller batches

---

## Key Takeaways

1. **OpenML** focuses on ML experiments (runs), not just models
2. **Runs link** flows (models), datasets, and tasks together
3. **Optional web scraping** for additional statistics
4. **Modular architecture** similar to HuggingFace extractor
5. **Metadata wrapping** tracks extraction method and provenance
6. **Experiment-centric** data model vs model-centric (HuggingFace)

---

## Next Steps

- See [HuggingFace Extractor](huggingface.md) - Model repository extraction
- Check [AI4Life Extractor](ai4life.md) - Biomedical AI models
- Learn [Adding a New Extractor](adding-extractor.md) - How to add new sources
- Explore [Transformers](../transformers/overview.md) - How extracted data is transformed

---

## Resources

- **OpenML:** [https://www.openml.org/](https://www.openml.org/)
- **OpenML Python Package:** [https://github.com/openml/openml-python](https://github.com/openml/openml-python)
- **OpenML API:** [https://www.openml.org/api_docs](https://www.openml.org/api_docs)
