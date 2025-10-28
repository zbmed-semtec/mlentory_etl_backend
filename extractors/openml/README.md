# OpenML Extractor

Modular extraction pipeline for OpenML run, dataset, flow, and task metadata.

## Architecture

This extractor follows the same modular pattern as the HuggingFace extractor:

```
openml/
├── clients/                    # API clients for each entity type
│   ├── openml_runs_client.py      # Fetches run metadata
│   ├── openml_datasets_client.py  # Fetches dataset metadata
│   ├── openml_flows_client.py     # Fetches flow (model) metadata
│   └── openml_tasks_client.py     # Fetches task metadata
├── entity_identifiers/         # Extract entity references from runs
│   ├── base.py                    # Abstract base class
│   ├── dataset_identifier.py     # Identifies datasets from runs
│   ├── flow_identifier.py        # Identifies flows from runs
│   └── task_identifier.py        # Identifies tasks from runs
├── scrapers/                   # Optional web scraping
│   └── openml_web_scraper.py     # Selenium-based scraper for stats
├── openml_extractor.py         # High-level extractor coordinator
└── openml_enrichment.py        # Enrichment orchestrator
```

## Data Flow

1. **Extract Runs** → `runs.json`
   - Fetches N most recent runs from OpenML
   - Each run contains references to dataset, flow, and task

2. **Identify Entities**
   - Scans runs to identify unique datasets, flows, and tasks
   
3. **Extract Related Entities**
   - **Datasets** → `datasets.json` (with optional web-scraped stats)
   - **Flows** → `flows.json`
   - **Tasks** → `tasks.json`

## Output Structure

All outputs are saved to `/data/raw/openml/<timestamp>_<uuid>/`:

```
/data/raw/openml/2025-10-24_14-30-00_a1b2c3d4/
├── runs.json      # Raw run metadata
├── datasets.json  # Dataset metadata (with optional scraped stats)
├── flows.json     # Flow (model) metadata
└── tasks.json     # Task metadata
```

## Configuration

Environment variables (set in `.env`):

### Runs Extraction
- `OPENML_NUM_INSTANCES` (default: `50`) - Number of runs to fetch
- `OPENML_OFFSET` (default: `0`) - Pagination offset
- `OPENML_THREADS` (default: `4`) - Threads for parallel processing

### Entity Enrichment
- `OPENML_ENRICHMENT_THREADS` (default: `4`) - Threads for entity extraction
- `OPENML_ENABLE_SCRAPING` (default: `false`) - Enable web scraping for dataset stats

## Web Scraping

By default, web scraping is **disabled** for faster extraction. When enabled, the scraper:

- Uses a thread-safe browser pool (Selenium)
- Scrapes dataset stats: status, downloads, likes, issues
- Implements exponential backoff and retry logic
- Auto-disables on connection failures

**Enable scraping:**
```bash
OPENML_ENABLE_SCRAPING=true
```

**Note:** Scraping is slow and may be unreliable. Use only when stats are critical.

## Dagster Assets

The extraction pipeline is orchestrated via Dagster assets in `etl/assets/openml_extraction.py`:

**Asset Graph:**
```
openml_run_folder
    ↓
openml_raw_runs
    ↓ ↓ ↓
    ├─→ openml_identified_datasets → openml_enriched_datasets
    ├─→ openml_identified_flows → openml_enriched_flows
    └─→ openml_identified_tasks → openml_enriched_tasks
```

**Asset Groups:**
- `openml` - Core extraction (run folder, runs)
- `openml_enrichment` - Entity identification and extraction

## Usage

### Standalone Usage

```python
from extractors.openml import OpenMLExtractor, OpenMLEnrichment

# Extract runs
extractor = OpenMLExtractor(enable_scraping=False)
runs_df, runs_path = extractor.extract_runs(num_instances=10, threads=4)

# Identify and extract related entities
enrichment = OpenMLEnrichment(extractor=extractor)
entity_paths = enrichment.enrich_from_runs_json(runs_path, threads=4)

# Clean up
extractor.close()
```

### Via Dagster

Materialize assets in the Dagster UI or via CLI:

```bash
# Materialize all OpenML assets
dagster asset materialize -m etl.repository -a openml_raw_runs

# Materialize with enrichment
dagster asset materialize -m etl.repository -a openml_enriched_datasets
```

## Metadata Format

All metadata values are wrapped in a standard format:

```json
{
  "field_name": [
    {
      "data": <value>,
      "extraction_method": "openml_python_package" | "web_scraping",
      "confidence": 1,
      "extraction_time": "2025-10-24T14:30:00.000000"
    }
  ]
}
```

This enables tracking of data provenance and extraction method.

## Error Handling

- **API Errors:** Logged and skipped (returns `None`)
- **Scraping Errors:** Retries with exponential backoff, then falls back to API
- **Browser Pool:** Auto-cleanup via `__del__` and `finally` blocks
- **Empty Entities:** Logs warning and returns empty string for paths

## Testing

Test with a small number of instances first:

```bash
export OPENML_NUM_INSTANCES=5
export OPENML_ENABLE_SCRAPING=false
dagster asset materialize -m etl.repository -a openml_raw_runs
```

For scraping tests (slow):

```bash
export OPENML_NUM_INSTANCES=2
export OPENML_ENABLE_SCRAPING=true
dagster asset materialize -m etl.repository -a openml_enriched_datasets
```

## Dependencies

- `openml` - OpenML Python API
- `pandas` - Data manipulation
- `selenium` - Web scraping (optional)
- `dagster` - Orchestration


