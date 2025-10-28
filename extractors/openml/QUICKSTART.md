# OpenML Extractor - Quick Start Guide

## 🚀 Get Started in 30 Seconds

### 1. Configure (Optional - Has Defaults)
```bash
export OPENML_NUM_INSTANCES=50        # How many runs to extract
export OPENML_ENABLE_SCRAPING=false   # Enable web scraping (slow)
```

### 2. Run Extraction
```bash
dagster asset materialize -m etl.repository -a openml_raw_runs
```

### 3. Run Enrichment (Extract Related Entities)
```bash
dagster asset materialize -m etl.repository -a openml_enriched_datasets
dagster asset materialize -m etl.repository -a openml_enriched_flows
dagster asset materialize -m etl.repository -a openml_enriched_tasks
```

### 4. Check Output
```bash
ls /data/raw/openml/
# Shows: 2025-10-24_14-30-00_a1b2c3d4/

ls /data/raw/openml/2025-10-24_14-30-00_a1b2c3d4/
# Shows: runs.json  datasets.json  flows.json  tasks.json
```

## 📦 What You Get

```
/data/raw/openml/<timestamp>_<uuid>/
├── runs.json      ← 50 OpenML runs with metadata
├── datasets.json  ← Unique datasets used in those runs
├── flows.json     ← Unique ML models/algorithms (flows)
└── tasks.json     ← Unique tasks (classification, regression, etc.)
```

## ⚙️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENML_NUM_INSTANCES` | `50` | Number of runs to extract |
| `OPENML_OFFSET` | `0` | Pagination offset |
| `OPENML_THREADS` | `4` | Parallel threads for runs |
| `OPENML_ENRICHMENT_THREADS` | `4` | Parallel threads for entities |
| `OPENML_ENABLE_SCRAPING` | `false` | Enable web scraping ⚠️ slow |

## 🎯 Common Use Cases

### Extract 10 Runs (Fast Test)
```bash
export OPENML_NUM_INSTANCES=10
dagster asset materialize -m etl.repository -a openml_raw_runs
```

### Extract with Enrichment
```bash
export OPENML_NUM_INSTANCES=50
dagster asset materialize -m etl.repository -a openml_enriched_datasets
```

### Extract with Web Scraping (Slow)
```bash
export OPENML_NUM_INSTANCES=5
export OPENML_ENABLE_SCRAPING=true
dagster asset materialize -m etl.repository -a openml_enriched_datasets
```

### High-Performance Extraction (More Threads)
```bash
export OPENML_THREADS=8
export OPENML_ENRICHMENT_THREADS=8
dagster asset materialize -m etl.repository -a openml_raw_runs
```

## 🐍 Python API

```python
from extractors.openml import OpenMLExtractor, OpenMLEnrichment
from pathlib import Path

# Quick extraction
extractor = OpenMLExtractor(enable_scraping=False)
runs_df, runs_path = extractor.extract_runs(num_instances=10)
extractor.close()

# With enrichment
enrichment = OpenMLEnrichment()
entity_paths = enrichment.enrich_from_runs_json(runs_path)
```

## 📊 Asset Graph

```
openml_run_folder
    ↓
openml_raw_runs
    ↓ ↓ ↓
    ├─→ openml_identified_datasets → openml_enriched_datasets
    ├─→ openml_identified_flows → openml_enriched_flows
    └─→ openml_identified_tasks → openml_enriched_tasks
```

## ⚠️ Important Notes

### Web Scraping
- **Disabled by default** - API-only is fast
- **Enable only if needed** - Scraping is slow (1-3 sec per dataset)
- **Requires Chrome/Chromium** - Install browser if scraping enabled
- **May be unreliable** - Falls back to API on failures

### Performance
- **API-only:** ~10 runs/sec (fast)
- **With scraping:** ~0.3 datasets/sec (slow)
- **Recommendation:** Start without scraping, enable only if stats needed

### Output Format
All metadata wrapped for provenance:
```json
{
  "dataset_id": [{
    "data": 123,
    "extraction_method": "openml_python_package",
    "confidence": 1,
    "extraction_time": "2025-10-24T14:30:00"
  }]
}
```

## 🔧 Troubleshooting

### "No browser available from pool"
→ Scraping enabled but Chrome not installed
```bash
export OPENML_ENABLE_SCRAPING=false
```

### Empty datasets.json
→ Normal if runs don't reference datasets. Check logs:
```
INFO - Identified 0 unique datasets
```

### Slow extraction
→ Disable scraping for speed:
```bash
export OPENML_ENABLE_SCRAPING=false
```

## 📚 More Documentation

- **Architecture:** `README.md`
- **Migration Guide:** `MIGRATION.md`
- **Full Summary:** `/OPENML_IMPLEMENTATION_SUMMARY.md`
- **Source Code:** `extractors/openml/`

## 🎉 That's It!

You're ready to extract OpenML data. Start with:
```bash
export OPENML_NUM_INSTANCES=5
dagster asset materialize -m etl.repository -a openml_raw_runs
```


