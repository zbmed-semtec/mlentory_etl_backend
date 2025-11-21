# AI4Life Extractor

Complete guide to extracting ML model metadata from AI4Life, a platform for biomedical AI models and datasets.

---

## AI4Life Platform Overview

**AI4Life** (Artificial Intelligence for Life Sciences) is a platform focused on biomedical AI models and datasets, particularly in:
- **Bioimaging:** Image analysis models for microscopy, medical imaging
- **Life Sciences:** Models for biological data analysis
- **Biomedical Research:** AI tools for healthcare and research

### Why Extract from AI4Life?

- **Specialized Domain:** Biomedical and life sciences focus
- **Bioimaging Models:** Models for image analysis in biology/medicine
- **Research Tools:** AI models for scientific research
- **Complementary Data:** Different domain from HuggingFace/OpenML

### AI4Life Data Model

AI4Life uses the **Hypha** platform for artifact management:
- **Artifacts:** Models, datasets, and other research artifacts
- **Parent-Child Structure:** Artifacts organized in hierarchies
- **Metadata:** Rich descriptions and metadata for each artifact

---

## Extraction Process

### Step 1: Fetch Records

**What happens:**
1. Connect to AI4Life Hypha API
2. Request artifact list from specified parent
3. Fetch metadata for N models
4. Store raw JSON files

**Output:**
- `/data/raw/ai4life/<timestamp>_<uuid>/ai4life_records.json`

**Configuration:**
- `AI4LIFE_NUM_MODELS`: Number of models to extract (default: 50)
- `AI4LIFE_BASE_URL`: API base URL (default: https://hypha.aicell.io)
- `AI4LIFE_PARENT_ID`: Parent ID for extraction (default: bioimage-io/bioimage.io)

### Step 2: Wrap with Metadata

**What happens:**
- Each field is wrapped with extraction metadata
- Tracks extraction method, confidence, timestamp
- Follows same pattern as OpenML extractor

**Metadata Format:**
```json
{
  "field_name": [
    {
      "data": <value>,
      "extraction_method": "hypha_api",
      "confidence": 1.0,
      "extraction_time": "2025-01-15T12:00:00Z"
    }
  ]
}
```

**Benefits:**
- Provenance tracking
- Extraction method documentation
- Confidence scores for data quality

---

## Architecture

The AI4Life extractor uses a simpler architecture than HuggingFace/OpenML:

### Extractor Class

Single extractor class handles all extraction:

```python
from etl_extractors.ai4life import AI4LifeExtractor

extractor = AI4LifeExtractor(
    base_url="https://hypha.aicell.io",
    parent_id="bioimage-io/bioimage.io"
)
```

**Responsibilities:**
- Fetch records from Hypha API
- Wrap fields with extraction metadata
- Handle errors and retries

### No Entity Enrichment

Unlike HuggingFace and OpenML, AI4Life extractor:
- Does not perform entity enrichment
- Extracts model records directly
- Simpler data model (no relationships to discover)

---

## Dagster Assets

The AI4Life extraction is exposed as Dagster assets:

### Extraction Assets

**`ai4life_run_folder`**
- Creates unique run folder for this materialization
- Returns: Path to run folder

**`ai4life_raw_records`**
- Fetches records from AI4Life API
- Depends on: `ai4life_run_folder`
- Returns: Tuple of (records_json_path, run_folder)

### Transformation Assets

**`ai4life_normalized_models`**
- Normalizes AI4Life records to FAIR4ML
- Depends on: `ai4life_raw_records`
- Returns: Path to normalized models JSON

**`ai4life_normalized_datasets`**
- Normalizes AI4Life datasets to FAIR4ML
- Depends on: `ai4life_raw_records`
- Returns: Path to normalized datasets JSON

**`ai4life_normalized_papers`**
- Normalizes AI4Life papers to FAIR4ML
- Depends on: `ai4life_raw_records`
- Returns: Path to normalized papers JSON

### Asset Dependency Graph

```
ai4life_run_folder
    ↓
ai4life_raw_records
    ↓
    ├─→ ai4life_normalized_models
    ├─→ ai4life_normalized_datasets
    └─→ ai4life_normalized_papers
```

---

## Configuration

All configuration is via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `AI4LIFE_NUM_MODELS` | Number of models to extract | `50` |
| `AI4LIFE_BASE_URL` | API base URL | `https://hypha.aicell.io` |
| `AI4LIFE_PARENT_ID` | Parent ID for extraction | `bioimage-io/bioimage.io` |

---

## Output Structure

All extracted data is saved in run-specific folders:

```
/data/raw/ai4life/
└── 2025-01-15_12-00-00_abc123/    # Run folder
    └── ai4life_records.json        # Raw records with metadata wrapping
```

### Metadata Wrapping

All fields are wrapped with extraction metadata:

```json
{
  "name": [
    {
      "data": "Model Name",
      "extraction_method": "hypha_api",
      "confidence": 1.0,
      "extraction_time": "2025-01-15T12:00:00Z"
    }
  ],
  "description": [
    {
      "data": "Model description...",
      "extraction_method": "hypha_api",
      "confidence": 1.0,
      "extraction_time": "2025-01-15T12:00:00Z"
    }
  ]
}
```

---

## Usage Examples

### Via Dagster UI

1. Open Dagster UI (http://localhost:3000)
2. Navigate to Assets tab
3. Find `ai4life_raw_records` asset
4. Click "Materialize"
5. Watch progress in real-time

### Via Command Line

**Extract records:**
```bash
dagster asset materialize -m etl.repository -a ai4life_raw_records
```

**Extract with normalization:**
```bash
dagster asset materialize -m etl.repository -a ai4life_normalized_models+
```

**Extract all AI4Life assets:**
```bash
dagster asset materialize -m etl.repository --select "ai4life*"
```

### Programmatic Usage

**Standalone (without Dagster):**
```python
from etl_extractors.ai4life import AI4LifeExtractor

extractor = AI4LifeExtractor(
    base_url="https://hypha.aicell.io",
    parent_id="bioimage-io/bioimage.io"
)

records = extractor.fetch_records(num_models=50)
wrapped_records = [
    extractor.wrap_record_with_metadata(record)
    for record in records
]
```

---

## Differences from Other Extractors

| Aspect | HuggingFace | OpenML | AI4Life |
|--------|-------------|--------|---------|
| **Domain** | General ML | ML Experiments | Biomedical AI |
| **Enrichment** | Extensive (7 entity types) | Moderate (3 entity types) | None |
| **Metadata Wrapping** | No | Yes | Yes |
| **Complexity** | High | Medium | Low |
| **Primary Focus** | Models | Experiments | Biomedical artifacts |

---

## Troubleshooting

### API Connection Errors

**Problem:** Cannot connect to AI4Life API

**Solutions:**
- Check internet connection
- Verify `AI4LIFE_BASE_URL` is correct
- Check firewall settings
- Verify API endpoint is accessible

### No Records Returned

**Problem:** Extraction returns empty results

**Solutions:**
- Check `AI4LIFE_PARENT_ID` is correct
- Verify parent exists in AI4Life
- Increase `AI4LIFE_NUM_MODELS`
- Review API response for errors

### Missing Fields

**Problem:** Some expected fields are missing

**Solutions:**
- Check AI4Life data structure
- Review raw JSON output
- Some fields may be optional
- Check extraction metadata for confidence scores

---

## Key Takeaways

1. **AI4Life** focuses on biomedical AI models
2. **Simpler architecture** than HuggingFace/OpenML (no entity enrichment)
3. **Metadata wrapping** tracks extraction provenance
4. **Hypha platform** provides artifact management
5. **Specialized domain** complements general ML repositories

---

## Next Steps

- See [HuggingFace Extractor](huggingface.md) - Most comprehensive extractor
- Check [OpenML Extractor](openml.md) - ML experiments platform
- Learn [Adding a New Extractor](adding-extractor.md) - How to add new sources
- Explore [Transformers](../transformers/overview.md) - How extracted data is transformed

---

## Resources

- **AI4Life:** [https://ai4life.eu/](https://ai4life.eu/)
- **Hypha Platform:** [https://hypha.aicell.io/](https://hypha.aicell.io/)
- **BioImage.IO:** [https://bioimage.io/](https://bioimage.io/)
