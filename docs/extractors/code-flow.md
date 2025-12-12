#Code Flow

This guide explains how the extraction system works, using HuggingFace as a concrete example. You'll learn how control flows through the system and how Dagster assets are created.

---

## Overview: The Big Picture

Extraction in MLentory follows a clear pattern:

1. **Dagster orchestrates** the extraction through assets
2. **Extractor classes** handle the actual data fetching
3. **Raw data is saved** to organized folders
4. **Entity enrichment** discovers and fetches related entities

Let's trace through this flow step by step using HuggingFace as our example.

---

## Control Flow: How Execution Happens

### Step-by-Step Execution Flow

When you trigger an extraction in Dagster, here's exactly what happens:

#### 1. User Action
User clicks "Materialize" on `hf_raw_models` asset in Dagster UI.

#### 2. Dagster Dependency Resolution
Dagster analyzes the asset dependency graph:

```
hf_raw_models depends on:
  ├── hf_raw_models_latest
  └── hf_raw_models_from_file
  
Both depend on:
  └── hf_run_folder
```

Dagster determines execution order:

1. `hf_run_folder` (no dependencies - runs first)
2. `hf_raw_models_latest` and `hf_raw_models_from_file` (run in parallel)
3. `hf_raw_models` (waits for both to complete)

#### 3. Asset Execution
Each asset executes in order:

**Step 3a: hf_run_folder executes**
```python
# Dagster calls this function
def hf_run_folder() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]
    run_folder_name = f"{timestamp}_{run_id}"
    
    run_folder = Path("/data/1_raw/hf") / run_folder_name
    run_folder.mkdir(parents=True, exist_ok=True)
    
    return str(run_folder)  # Returns: "/data/1_raw/hf/2025-01-15_12-00-00_abc123"
```

**Step 3b: hf_raw_models_latest executes (parallel with hf_raw_models_from_file)**
```python
# Dagster passes the output from hf_run_folder as input
def hf_raw_models_latest(run_folder: str) -> Tuple[Optional[pd.DataFrame], str]:
    # run_folder = "/data/1_raw/hf/2025-01-15_12-00-00_abc123"
    
    config = get_hf_config()  # Load configuration
    extractor = HFExtractor()  # Create extractor instance
    
    # Call extractor to fetch data
    df, output_path = extractor.extract_models(
        num_models=config.num_models,
        update_recent=config.update_recent,
        threads=config.threads,
        output_root=Path(run_folder).parent.parent,  # /data
    )
    
    return (df, run_folder)  # Return DataFrame and folder path
```

**Step 3c: hf_raw_models executes (after both dependencies complete)**
```python
# Dagster passes outputs from both dependencies
def hf_raw_models(
    latest_data: Tuple[Optional[pd.DataFrame], str],
    file_data: Tuple[Optional[pd.DataFrame], str],
) -> Tuple[str, str]:
    latest_df, run_folder = latest_data
    file_df, _ = file_data
    
    # Merge both DataFrames
    merged_df = pd.concat([latest_df, file_df], ignore_index=True)
    
    # Save to run folder
    final_path = Path(run_folder) / "hf_models.json"
    merged_df.to_json(str(final_path), orient="records", indent=2)
    
    return (str(final_path), run_folder)
```

#### 4. Downstream Assets Execute
After `hf_raw_models` completes, downstream assets execute:

- `hf_add_ancestor_models` (adds base models)
- `hf_identified_datasets` (finds dataset references)
- `hf_enriched_datasets` (fetches dataset metadata)
- And so on...

---

## How Assets Are Created: Complete Example

Let's see how a complete asset is created, from definition to execution.

### Asset Definition Pattern

Every extraction asset follows this pattern:

```python
@asset(
    group_name="hf",                    # Groups related assets
    ins={"input_name": AssetIn("upstream_asset_name")},  # Dependencies
    tags={"pipeline": "hf_etl"}         # Metadata tags
)
def asset_function_name(input_name: Type) -> ReturnType:
    """
    Docstring explaining what this asset does.
    
    Args:
        input_name: Description of input
        
    Returns:
        Description of output
    """
    # 1. Load configuration
    config = get_hf_config()
    
    # 2. Create extractor/enrichment instance
    extractor = HFExtractor()
    
    # 3. Process data
    result = extractor.some_method(input_name)
    
    # 4. Save to run folder
    output_path = Path(run_folder) / "output_file.json"
    result.to_json(str(output_path))
    
    # 5. Return path for downstream assets
    return str(output_path)
```

### Real Example: hf_raw_models_latest

Here's the complete implementation:

```51:103:etl/assets/hf_extraction.py
@asset(group_name="hf", tags={"pipeline": "hf_etl"})
def hf_run_folder() -> str:
    """
    Create a unique run folder for this materialization.
    
    All assets in this run will save outputs to this folder, ensuring
    that outputs from a single run are grouped together.
    
    Returns:
        Path to the run-specific output directory
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]
    run_folder_name = f"{timestamp}_{run_id}"
    
    run_folder = Path("/data/1_raw/hf") / run_folder_name
    run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created run folder: {run_folder}")
    return str(run_folder)


@asset(
    group_name="hf",
    ins={"run_folder": AssetIn("hf_run_folder")},
    tags={"pipeline": "hf_etl"}
)
def hf_raw_models_latest(run_folder: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Extract the latest N HF models using get_model_metadata_dataset.
    
    Args:
        run_folder: Path to the run-specific output directory
    
    Returns:
        Tuple of (models_dataframe, run_folder) to pass to merge asset
    """
    config = get_hf_config()
    extractor = HFExtractor()
    
    output_root = Path(run_folder).parent.parent  # Go up to /data
    df, output_path = extractor.extract_models(
        num_models=config.num_models,
        update_recent=config.update_recent,
        threads=config.threads,
        output_root=output_root,
    )
    
    # Clean up the temporary file created by extractor
    Path(output_path).unlink(missing_ok=True)
    
    logger.info(f"Extracted {len(df)} latest models")
    return (df, run_folder)
```

**Breaking Down the Asset:**

1. **Decorator:** `@asset(...)` marks this as a Dagster asset

   - `group_name="hf"` - Groups all HF assets together in UI
   - `ins={"run_folder": AssetIn("hf_run_folder")}` - Declares dependency
   - `tags={"pipeline": "hf_etl"}` - Adds metadata for filtering

2. **Function Signature:**

   - `run_folder: str` - Input from `hf_run_folder` asset
   - `-> Tuple[Optional[pd.DataFrame], str]` - Returns DataFrame and folder

3. **Function Body:**

   - Loads configuration
   - Creates extractor instance
   - Calls extractor method
   - Returns data for downstream assets

### Real Example: hf_raw_models (Merge Asset)

This asset shows how to handle multiple dependencies:

```146:206:etl/assets/hf_extraction.py
@asset(
    group_name="hf",
    ins={
        "latest_data": AssetIn("hf_raw_models_latest"),
        "file_data": AssetIn("hf_raw_models_from_file"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_raw_models(
    latest_data: Tuple[Optional[pd.DataFrame], str],
    file_data: Tuple[Optional[pd.DataFrame], str],
) -> Tuple[str, str]:
    """
    Merge models from both extraction modes (latest N + file-based).
    
    Combines models from both sources, removing duplicates based on model ID.
    
    Args:
        latest_data: Tuple of (models_df, run_folder) from latest extraction
        file_data: Tuple of (models_df, run_folder) from file-based extraction
    
    Returns:
        Tuple of (merged_models_json_path, run_folder) to pass to downstream assets
    """
    latest_df, run_folder = latest_data
    file_df, _ = file_data
    
    # Collect non-None dataframes
    dfs_to_merge = []
    if latest_df is not None and not latest_df.empty:
        dfs_to_merge.append(latest_df)
        logger.info(f"Including {len(latest_df)} models from latest extraction")
    
    if file_df is not None and not file_df.empty:
        dfs_to_merge.append(file_df)
        logger.info(f"Including {len(file_df)} models from file extraction")
    
    # Merge and deduplicate
    if not dfs_to_merge:
        logger.warning("No models extracted from either source!")
        # Create an empty dataframe with expected structure
        merged_df = pd.DataFrame()
    elif len(dfs_to_merge) == 1:
        merged_df = dfs_to_merge[0]
    else:
        merged_df = pd.concat(dfs_to_merge, ignore_index=True)
        # Remove duplicates based on model_id (assuming 'id' or 'modelId' column exists)
        id_column = 'id' if 'id' in merged_df.columns else 'modelId'
        if id_column in merged_df.columns:
            before_count = len(merged_df)
            merged_df = merged_df.drop_duplicates(subset=[id_column], keep='first')
            after_count = len(merged_df)
            logger.info(f"Removed {before_count - after_count} duplicate models")
    
    # Save merged dataframe to run folder
    run_folder_path = Path(run_folder)
    final_path = run_folder_path / "hf_models.json"
    merged_df.to_json(path_or_buf=str(final_path), orient="records", indent=2, date_format="iso")
    
    logger.info(f"Merged {len(merged_df)} total models saved to {final_path}")
    return (str(final_path), run_folder)
```

**Key Points:**

- Multiple dependencies via `ins={}` dictionary
- Handles optional/None inputs gracefully
- Merges and deduplicates data
- Saves to run folder
- Returns path for downstream assets

---

## How Extractors Work: Inside the Extractor Class

### Extractor Class Structure

The `HFExtractor` class encapsulates all HuggingFace-specific logic:

```25:61:etl_extractors/hf/hf_extractor.py
class HFExtractor:
    """
    High-level wrapper around HFDatasetManager to extract raw artifacts
    and persist them to the data volume under /data/raw/hf.
    """

    def __init__(
        self,
        models_client: Optional[HFModelsClient] = None,
        datasets_client: Optional[HFDatasetsClient] = None,
        arxiv_client: Optional[HFArxivClient] = None,
        license_client: Optional[HFLicenseClient] = None,
        keyword_client: Optional[HFKeywordClient] = None,
        languages_client: Optional[HFLanguagesClient] = None,
        tasks_client: Optional[HFTasksClient] = None,
    ) -> None:
        self.models_client = models_client or HFModelsClient()
        self.datasets_client = datasets_client or HFDatasetsClient()
        self.arxiv_client = arxiv_client or HFArxivClient()
        self.license_client = license_client or HFLicenseClient()
        self.keyword_client = keyword_client or HFKeywordClient()
        self.languages_client = languages_client or HFLanguagesClient()
        self.tasks_client = tasks_client or HFTasksClient()

    def extract_models(
        self,
        num_models: int = 50,
        update_recent: bool = True,
        threads: int = 4,
        output_root: Path | None = None,
        save_csv: bool = False,
    ) -> (pd.DataFrame, Path):
        df = self.models_client.get_model_metadata_dataset(
            update_recent=update_recent, limit=num_models, threads=threads
        )
        json_path = self.save_dataframe_to_json(df, output_root=output_root, save_csv=save_csv, suffix="hf_models")
        return df, json_path
```

**How It Works:**

1. **Initialization:** Creates API client instances for different entity types
2. **Extraction Method:** Calls the appropriate client to fetch data
3. **Data Persistence:** Saves data to JSON file
4. **Returns:** DataFrame and file path

### Client Layer: Low-Level API Interactions

The clients handle actual API calls:

```python
# Simplified example of what HFModelsClient does
class HFModelsClient:
    def get_model_metadata_dataset(self, limit: int, threads: int) -> pd.DataFrame:
        # 1. Make API call to HuggingFace
        response = requests.get("https://huggingface.co/api/models", params={"limit": limit})
        
        # 2. Parse response
        models = response.json()
        
        # 3. Convert to DataFrame
        df = pd.DataFrame(models)
        
        # 4. Return DataFrame
        return df
```

---

## Entity Identification and Enrichment Flow

### Step 1: Entity Identification

After extracting models, the system identifies related entities:

```249:271:etl/assets/hf_extraction.py
@asset(
    group_name="hf_enrichment",
    ins={"models_data": AssetIn("hf_add_ancestor_models")},
    tags={"pipeline": "hf_etl"}
)
def hf_identified_datasets(models_data: Tuple[str, str]) -> Tuple[Dict[str, List[str]], str]:
    """
    Identify dataset references per model from raw HF models.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Tuple of ({model_id: [dataset_names]}, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)

    model_datasets = enrichment.identifiers["datasets"].identify_per_model(models_df)
    logger.info(f"Identified datasets for {len(model_datasets)} models")

    return (model_datasets, run_folder)
```

**What Happens:**

1. Loads models from JSON file
2. Creates `HFEnrichment` instance
3. Uses `DatasetIdentifier` to scan models for dataset references
4. Returns mapping: `{"model1": ["squad", "glue"], "model2": ["imagenet"]}`

### Step 2: Entity Enrichment

Once entities are identified, fetch their full metadata:

```274:310:etl/assets/hf_extraction.py
@asset(
    group_name="hf_enrichment",
    ins={"datasets_data": AssetIn("hf_identified_datasets")},
    tags={"pipeline": "hf_etl"}
)
def hf_enriched_datasets(datasets_data: Tuple[Dict[str, List[str]], str]) -> str:
    """
    Extract metadata for identified datasets from HuggingFace.
    
    Args:
        datasets_data: Tuple of (dataset_names, run_folder)
        
    Returns:
        Path to the saved datasets JSON file
    """
    model_datasets_dict, run_folder = datasets_data
    dataset_names = set()
    for model_id, datasets in model_datasets_dict.items():
        dataset_names.update(datasets)
    
    config = get_hf_config()
    extractor = HFExtractor()
    
    if not dataset_names:
        logger.info("No datasets to extract")
        return ""
    
    # Extract datasets
    df, output_path = extractor.extract_specific_datasets(
        dataset_names=list(dataset_names),
        threads=config.enrichment_threads,
        output_root=Path(run_folder).parent.parent,
    )
    
    # Move to run folder
    final_path = Path(run_folder) / "hf_datasets_specific.json"
    df.to_json(path_or_buf=str(final_path), orient="records", indent=2, date_format="iso")
    
    logger.info(f"Extracted {len(df)} datasets, saved to {final_path}")
    return str(final_path)
```

**What Happens:**

1. Collects unique dataset names from the mapping
2. Creates extractor instance
3. Calls `extract_specific_datasets()` to fetch metadata
4. Saves enriched datasets to run folder
5. Returns file path

---

## Complete Asset Dependency Graph

Here's the complete dependency graph for HuggingFace extraction:

```
hf_run_folder
    ├── hf_raw_models_latest (parallel)
    └── hf_raw_models_from_file (parallel)
            └── hf_raw_models (merges both)
                    └── hf_add_ancestor_models (adds base models)
                            ├── hf_identified_datasets
                            ├── hf_identified_articles
                            ├── hf_identified_base_models
                            ├── hf_identified_keywords
                            ├── hf_identified_licenses
                            ├── hf_identified_languages
                            └── hf_identified_tasks
                                    ├── hf_enriched_datasets
                                    ├── hf_enriched_articles
                                    ├── hf_enriched_base_models
                                    └── hf_enriched_tasks
```

**Execution Order:**

1. `hf_run_folder` runs first (creates folder)
2. `hf_raw_models_latest` and `hf_raw_models_from_file` run in parallel
3. `hf_raw_models` runs after both complete (merges data)
4. `hf_add_ancestor_models` runs (adds base models)
5. All identification assets run in parallel
6. All enrichment assets run in parallel

---

## Key Concepts for Beginners

### What is a Dagster Asset?

An asset is a Python function decorated with `@asset` that:

- **Produces data:** Creates a file, database record, or other artifact
- **Has dependencies:** Can depend on other assets via `ins={}`
- **Is tracked:** Dagster monitors its execution and status
- **Is materializable:** Can be executed on demand or on schedule

**Example:**
```python
@asset(group_name="hf")
def hf_run_folder() -> str:
    """Creates a folder for this run."""
    folder = Path("/data/1_raw/hf") / "2025-01-15_12-00-00_abc123"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder)
```

### What is an Extractor Class?

An extractor class:

- **Encapsulates platform logic:** Knows how to talk to a specific platform's API
- **Handles data fetching:** Makes API calls, handles pagination, rate limiting
- **Saves data:** Writes data to files in a consistent format
- **Is called by assets:** Assets use extractors to do the actual work

**Example:**
```python
class HFExtractor:
    def extract_models(self, num_models: int) -> (pd.DataFrame, Path):
        # Fetch from API
        models = self.client.get_models(limit=num_models)
        # Save to file
        path = self.save_to_json(models)
        return models, path
```

### Why Separate Assets and Extractors?

**Separation of Concerns:**

- **Assets** = Orchestration (when, what order, dependencies)
- **Extractors** = Implementation (how to fetch data)

**Benefits:**

- Test extractors independently (without Dagster)
- Reuse extractors in different contexts
- Change orchestration without changing extraction logic
- Clear separation makes code easier to understand

### How Do Dependencies Work?

**Dependency Declaration:**
```python
@asset(
    ins={"run_folder": AssetIn("hf_run_folder")}  # Declares dependency
)
def hf_raw_models_latest(run_folder: str) -> ...:
    # run_folder contains the output from hf_run_folder
    pass
```

**Dependency Resolution:**

1. Dagster sees `hf_raw_models_latest` depends on `hf_run_folder`
2. Dagster ensures `hf_run_folder` runs first
3. Dagster passes `hf_run_folder`'s return value to `hf_raw_models_latest`
4. If `hf_run_folder` fails, `hf_raw_models_latest` doesn't run

**Multiple Dependencies:**

```python
@asset(
    ins={
        "latest": AssetIn("hf_raw_models_latest"),
        "file": AssetIn("hf_raw_models_from_file"),
    }
)
def hf_raw_models(latest: ..., file: ...) -> ...:
    # Both dependencies must complete before this runs
    pass
```

---

## Common Patterns

### Pattern 1: Run Folder Creation

Every extraction starts with a run folder:

```python
@asset(group_name="platform")
def platform_run_folder() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]
    run_folder = Path("/data/1_raw/platform") / f"{timestamp}_{run_id}"
    run_folder.mkdir(parents=True, exist_ok=True)
    return str(run_folder)
```

### Pattern 2: Extraction Asset

Extract data and save to run folder:

```python
@asset(
    group_name="platform",
    ins={"run_folder": AssetIn("platform_run_folder")}
)
def platform_raw_models(run_folder: str) -> Tuple[str, str]:
    config = get_platform_config()
    extractor = PlatformExtractor()
    
    df, _ = extractor.extract_models(
        num_models=config.num_models,
        output_root=Path(run_folder).parent.parent,
    )
    
    final_path = Path(run_folder) / "models.json"
    df.to_json(final_path, orient='records', indent=2)
    
    return (str(final_path), run_folder)
```

### Pattern 3: Entity Identification

Identify related entities:

```python
@asset(
    group_name="platform",
    ins={"models_data": AssetIn("platform_raw_models")}
)
def platform_identified_datasets(models_data: Tuple[str, str]) -> Tuple[Dict, str]:
    models_path, run_folder = models_data
    
    with open(models_path, 'r') as f:
        models = json.load(f)
    
    # Identify datasets (customize for your platform)
    model_datasets = {}
    for model in models:
        # Your identification logic here
        datasets = find_datasets_in_model(model)
        model_datasets[model['id']] = datasets
    
    return (model_datasets, run_folder)
```

### Pattern 4: Entity Enrichment

Fetch full metadata for entities:

```python
@asset(
    group_name="platform",
    ins={"datasets_data": AssetIn("platform_identified_datasets")}
)
def platform_enriched_datasets(datasets_data: Tuple[Dict, str]) -> str:
    model_datasets, run_folder = datasets_data
    
    # Collect unique dataset names
    all_datasets = set()
    for datasets in model_datasets.values():
        all_datasets.update(datasets)
    
    # Fetch metadata
    extractor = PlatformExtractor()
    df, _ = extractor.extract_datasets(list(all_datasets))
    
    # Save to run folder
    final_path = Path(run_folder) / "datasets.json"
    df.to_json(final_path, orient='records', indent=2)
    
    return str(final_path)
```

---

## Debugging Tips

### View Asset Dependencies in Dagster UI

1. Open Dagster UI: http://localhost:3000
2. Navigate to Assets tab
3. Click on an asset to see:
   - Upstream dependencies (what it depends on)
   - Downstream dependencies (what depends on it)
   - Execution history
   - Logs and errors

### Check Run Folders

Inspect extracted data:

```bash
# List all runs
ls /data/1_raw/hf/

# View a specific run
cat /data/1_raw/hf/2025-01-15_12-00-00_abc123/hf_models.json | head -20
```

### Test Extractors Independently

Test without Dagster:

```python
from etl_extractors.hf import HFExtractor

extractor = HFExtractor()
df, path = extractor.extract_models(num_models=10)
print(f"Extracted {len(df)} models")
print(f"Saved to {path}")
```

### Read Logs

Check Dagster logs:

```bash
# Docker logs
docker compose logs dagster-webserver

# Or in Python
import logging
logging.basicConfig(level=logging.INFO)
```

---

## Next Steps

- See [HuggingFace Extractor](huggingface.md) for detailed HuggingFace-specific documentation
- Check [Adding a New Extractor](adding-extractor.md) for comprehensive step-by-step guide
- Explore [Extractors Overview](overview.md) for high-level concepts
- Review [Architecture Overview](../architecture/overview.md) to see how extractors fit into the system
