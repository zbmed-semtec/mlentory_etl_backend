# Dagster Basics: Orchestrating Data Pipelines

Dagster is the orchestration framework that manages the MLentory ETL pipeline. Understanding Dagster is crucial for anyone who wants to run pipelines, debug issues, or extend the system. This guide explains Dagster concepts in depth, showing how they apply to MLentory and why Dagster is the right choice for data pipelines.

---

## What is Dagster and Why Do We Need It?

Building a data pipeline involves many moving parts: extracting data from multiple sources, transforming it through multiple stages, loading it into multiple systems, handling errors, tracking progress, and ensuring dependencies are satisfied. Managing all of this manually would be a nightmare.

**Dagster** is a data orchestration platform designed specifically for data pipelines. Unlike general workflow tools that treat pipelines as sequences of tasks, Dagster understands that data pipelines are about **data artifacts**—files, database records, API responses—and how they flow through the system.

Think of Dagster as a conductor for an orchestra. Just as a conductor coordinates musicians to create harmonious music, Dagster coordinates data processing steps to create reliable pipelines. The conductor doesn't play an instrument—they ensure everyone plays at the right time, in the right order, with the right dependencies.

![Dagster Orchestration](images/dagster-orchestration.png)
*Figure 1: Dagster orchestrates data processing steps, ensuring dependencies are satisfied and providing observability into pipeline execution.*

### Why Dagster Over Other Tools?

**Built for Data:** Unlike general workflow tools (like Airflow), Dagster understands data pipelines. It tracks data artifacts (not just tasks), understands data dependencies, and provides data lineage. This makes it easier to reason about pipelines and debug issues.

**Great Observability:** Dagster provides a web UI that shows pipeline status in real-time. You can see what's running, what succeeded, what failed, and why. You can view data lineage to understand where data came from and how it was processed. This observability is crucial for debugging and monitoring.

**Developer-Friendly:** Dagster is Python-native, meaning you write pipelines in Python (not YAML or XML). This makes pipelines easier to write, test, and maintain. Type-safe data passing catches errors early, and the Python ecosystem provides rich tooling.

**Automatic Dependency Management:** Dagster automatically handles dependencies between steps. If step B depends on step A, Dagster ensures A runs before B. If A fails, B doesn't run. This eliminates manual ordering and reduces errors.

---

## Core Concepts: Understanding Dagster's Model

Dagster uses a unique model that's different from traditional workflow tools. Understanding this model is key to using Dagster effectively.

### Assets: Data Artifacts, Not Just Tasks

**Assets** are the fundamental concept in Dagster. An asset represents a piece of data that gets created or updated—a file, a database record, an API response. This is different from traditional workflow tools that think in terms of tasks.

**Why this matters:** In data pipelines, you care about data, not just tasks. You want to know "is the normalized models file ready?" not just "did the transformation task complete?" Assets make this explicit.

**Example:**
```python
@asset
def hf_raw_models() -> str:
    """Extract raw HuggingFace models."""
    # ... extraction logic ...
    return "/data/raw/hf/models.json"
```

This asset represents the raw models JSON file. When you materialize this asset, Dagster runs the code to produce that file. The asset is the data, not just the task that creates it.

**Key characteristics:**
- Assets are **data artifacts**—they represent actual data (files, database records, etc.)
- Each asset has a unique name that identifies it
- Assets can depend on other assets (creating a dependency graph)
- Dagster tracks when assets were last updated (materialized)

### Materialization: Creating or Updating Assets

**Materialization** is the process of creating or updating an asset. When you "materialize" an asset, Dagster runs the code that produces that data.

**In the Dagster UI:** You can click "Materialize" on any asset to run it. You see status in real-time (running, succeeded, failed), view logs as they're generated, and see outputs when complete.

**Automatic Materialization:** If you materialize an asset that depends on other assets, Dagster automatically materializes those dependencies first. For example, if you materialize `hf_normalized_models` which depends on `hf_raw_models`, Dagster automatically runs `hf_raw_models` first. This ensures dependencies are always satisfied.

**Idempotency:** Materialization is idempotent—running the same asset multiple times produces the same result (assuming inputs haven't changed). This makes it safe to re-run assets for debugging or reprocessing.

### Dependencies: Automatic Ordering

**Dependencies** define relationships between assets. When asset B depends on asset A, Dagster ensures A runs before B. This automatic ordering eliminates manual coordination.

**Example:**
```python
@asset
def hf_raw_models() -> str:
    return "/data/raw/hf/models.json"

@asset(ins={"models": AssetIn("hf_raw_models")})
def hf_normalized_models(models: str) -> str:
    # This asset depends on hf_raw_models
    # Dagster ensures hf_raw_models runs first
    # The 'models' parameter receives the output of hf_raw_models
    return "/data/normalized/hf/models.json"
```

**Benefits:**
- **No manual ordering:** You don't need to think about execution order—Dagster handles it
- **Parallel execution:** When possible, Dagster runs independent assets in parallel
- **Automatic retry:** If a dependency fails and is retried, dependent assets automatically re-run

**Dependency graphs:** Dagster builds a dependency graph from your asset definitions. This graph shows all assets and their relationships, making it easy to understand the pipeline structure.

### Jobs: Grouping Related Assets

**Jobs** are collections of assets that run together. You can define jobs to run multiple assets in sequence, schedule periodic runs, or group related assets for organization.

**Example:**
```python
@job
def hf_etl_job():
    hf_raw_models()
    hf_normalized_models()
    hf_load_to_neo4j()
```

This job defines a sequence of assets that form a complete ETL pipeline. When you run the job, Dagster materializes all assets in the correct order based on dependencies.

**Job benefits:**
- **Logical grouping:** Related assets are grouped together
- **Scheduling:** Jobs can be scheduled to run periodically
- **Execution control:** You can run entire pipelines with a single command
- **Monitoring:** Track job-level metrics and status

### Resources: Shared Connections and Configuration

**Resources** are shared connections or configurations used by multiple assets. Instead of each asset creating its own database connection or API client, resources provide shared instances.

**Example:**
```python
@resource
def neo4j_connection():
    return Neo4jDriver(uri="bolt://localhost:7687")

@asset(required_resource_keys={"neo4j"})
def load_to_neo4j(context):
    driver = context.resources.neo4j
    # Use driver to load data
```

**Common resources:**
- **Database connections:** Neo4j, Elasticsearch, PostgreSQL
- **API clients:** HuggingFace Hub client, OpenML client
- **Configuration settings:** Environment variables, feature flags

**Resource benefits:**
- **Connection reuse:** Avoid creating multiple connections
- **Centralized configuration:** Change connection settings in one place
- **Testing:** Easy to swap resources for testing (e.g., use mock database)
- **Resource management:** Proper cleanup and lifecycle management

---

## Asset Groups: Organizing the Pipeline

**Asset Groups** organize related assets together. In MLentory, we use groups to organize assets by source and stage:

- `hf` - HuggingFace extraction assets
- `hf_transformation` - HuggingFace transformation assets
- `hf_loading` - HuggingFace loading assets
- `openml` - OpenML extraction assets
- `ai4life` - AI4Life extraction assets

**Benefits:**
- **Logical organization:** Related assets are grouped together, making the pipeline easier to understand
- **UI filtering:** In the Dagster UI, you can filter assets by group, focusing on what you need
- **Batch operations:** You can materialize all assets in a group together
- **Clear structure:** Groups make the pipeline structure explicit and navigable

---

## Dagster UI: Visualizing and Controlling Pipelines

The Dagster UI is a web interface that provides comprehensive observability and control over your pipelines. It's one of Dagster's strongest features, making pipelines visible and manageable.

### Asset Graph: Seeing the Big Picture

The **Asset Graph** provides a visual representation of all assets and their dependencies. This graph shows:

- **All assets** in the pipeline, organized by groups
- **Dependencies** between assets (shown as arrows)
- **Status** of each asset (color-coded: green = succeeded, red = failed, yellow = running)
- **Last materialization time** for each asset

This visual representation makes it easy to understand the pipeline structure, see what depends on what, and identify bottlenecks or issues.

### Asset Details: Deep Dive into Individual Assets

Clicking on an asset shows detailed information:

- **Last materialization time:** When this asset was last successfully created/updated
- **Dependencies:** Which assets this one depends on
- **Dependents:** Which assets depend on this one
- **Logs:** Complete logs from the last materialization
- **Outputs:** What data was produced
- **Metadata:** Additional information about the asset

This detailed view helps you understand what each asset does, how it fits into the pipeline, and what went wrong if it failed.

### Materialization: Running Assets

The UI makes it easy to materialize assets:

1. **Select assets** you want to run (can select multiple)
2. **Click "Materialize"** to start execution
3. **Watch progress** in real-time as assets run
4. **View logs** as they're generated
5. **See results** when complete

You can materialize individual assets, assets with their dependencies (using the `+` notation), or entire groups. This flexibility makes it easy to run exactly what you need.

### Run History: Learning from the Past

**Run History** shows all past materializations, allowing you to:

- **See what ran when:** Complete history of all asset materializations
- **Filter by status:** Find failed runs, successful runs, or running jobs
- **Filter by date:** See runs from specific time periods
- **Filter by asset:** See all runs of a specific asset
- **Compare runs:** See how different runs performed

This history is invaluable for debugging (what changed between successful and failed runs?), monitoring (are runs getting slower?), and auditing (what was processed when?).

---

## How MLentory Uses Dagster: Real-World Patterns

Understanding how MLentory uses Dagster helps you see these concepts in practice:

### Asset Structure: Building the Pipeline

MLentory's pipeline is organized into clear stages, each with its own assets:

**Extraction Assets** form a dependency chain:
```
hf_run_folder
    ↓
hf_raw_models_latest
hf_raw_models_from_file
    ↓
hf_raw_models (merges both)
    ↓
hf_add_ancestor_models
    ↓
hf_identified_datasets → hf_enriched_datasets
hf_identified_articles → hf_enriched_articles
hf_identified_keywords → hf_enriched_keywords
...
```

This structure shows how extraction progresses: first create a run folder, then extract models (from API and file), merge them, add ancestor models, identify related entities, and finally enrich those entities.

**Transformation Assets** use parallel processing:
```
hf_normalized_run_folder
    ↓
    ├─→ hf_extract_basic_properties (parallel)
    ├─→ hf_extract_keywords_language (parallel)
    ├─→ hf_extract_task_category (parallel)
    ...
    ↓
hf_entity_linking
    ↓
hf_models_normalized (merges all)
```

Multiple property extraction assets run in parallel (they all depend on the same input), then entity linking happens, and finally all properties are merged into normalized models.

**Loading Assets** load to multiple systems:
```
hf_rdf_store_ready
    ↓
hf_load_models_rdf
hf_load_articles_rdf
hf_load_datasets_rdf
...
    ↓
hf_index_models_elasticsearch
```

Different entity types are loaded to Neo4j in parallel, then models are indexed in Elasticsearch.

### Running Assets: Multiple Ways to Execute

**Via UI:** The most user-friendly way. Open Dagster UI (http://localhost:3000), navigate to Assets, select what you want to run, and click Materialize. You can watch progress in real-time and see logs as they're generated.

**Via CLI:** For automation and scripting. Use commands like:
```bash
# Materialize single asset
dagster asset materialize -m etl.repository -a hf_raw_models

# Materialize with dependencies (the + means include dependencies)
dagster asset materialize -m etl.repository -a hf_models_normalized+

# Materialize all assets in a group
dagster asset materialize -m etl.repository --select "hf*"
```

**Programmatic:** For integration with other systems. You can materialize assets from Python code, enabling integration with other tools or custom automation.

---

## Key Features in MLentory: Reliability Patterns

MLentory's use of Dagster includes several patterns that ensure reliability:

### Idempotency: Safe Re-runs

**Idempotency** means that running the same asset multiple times produces the same result (assuming inputs haven't changed). This is crucial for reliability.

**How MLentory achieves it:** Assets are designed to be idempotent. Running `hf_raw_models` twice with the same configuration produces the same output. Upsert logic in loaders ensures that re-loading updates existing records rather than creating duplicates.

**Benefits:** Safe to re-run failed pipelines, can reprocess data with improved logic, and assets can be materialized multiple times for debugging.

### Incremental Processing: Efficiency

**Incremental Processing** means assets track what's already been processed and skip unchanged data.

**How MLentory achieves it:** Extractors can check if models have already been extracted (by ID or timestamp). Transformers can skip models that haven't changed. Loaders use upsert logic to update only changed records.

**Benefits:** Efficient resource usage (only process what's needed), fast updates (changes reflected quickly), and scalable (works with large datasets).

### Error Handling: Graceful Degradation

**Error Handling** ensures that individual failures don't stop the entire pipeline.

**How MLentory achieves it:** Each model is processed independently. If one model fails, others continue. Errors are logged comprehensively, and partial results are still useful.

**Benefits:** Maximizes success rate (get as much data as possible), provides partial results for debugging, and allows the pipeline to complete even with some failures.

### Data Lineage: Complete Traceability

**Data Lineage** tracks where data came from and how it was processed.

**How MLentory achieves it:** Dagster automatically tracks data flow through assets. You can see that `hf_normalized_models` came from `hf_raw_models`, which came from the HuggingFace API. This lineage is visible in the UI.

**Benefits:** Understand data flow (see how data moves through the pipeline), debug issues (trace problems back to their source), and ensure data quality (verify data came from expected sources).

---

## Common Patterns: Proven Solutions

MLentory uses several common Dagster patterns that have proven effective:

### Pattern 1: Run Folder Pattern

**The pattern:** Create a unique folder for each pipeline run, grouping all outputs together.

**Implementation:**
```python
@asset
def hf_run_folder() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]
    folder = f"/data/raw/hf/{timestamp}_{run_id}"
    os.makedirs(folder, exist_ok=True)
    return folder
```

**Benefits:**
- All outputs from one run are grouped together, making it easy to see what belongs together
- Easy to track and compare runs (each run has a unique folder)
- No file conflicts (different runs use different folders)
- Easy cleanup (can archive or delete entire runs)

### Pattern 2: Tuple Returns

**The pattern:** Return multiple values from an asset (data path + metadata).

**Implementation:**
```python
@asset
def hf_raw_models() -> Tuple[str, str]:
    # Returns: (data_path, run_folder)
    json_path = extract_models()
    run_folder = get_run_folder()
    return (json_path, run_folder)
```

**Benefits:**
- Pass metadata through the pipeline (downstream assets know where data is)
- Maintain run context (all assets in a run know the run folder)
- Flexible outputs (can return whatever information is needed)

### Pattern 3: Parallel Processing

**The pattern:** Multiple assets that depend on the same input can run in parallel.

**Implementation:**
```python
@asset
def extract_basic_properties(models: str) -> str:
    # Runs in parallel with other extractors
    pass

@asset
def extract_keywords(models: str) -> str:
    # Runs in parallel with extract_basic_properties
    # Both depend on the same 'models' input
    pass
```

**Benefits:**
- Faster processing (parallel execution instead of sequential)
- Better resource utilization (use all available CPU cores)
- Independent failure handling (one failure doesn't block others)

---

## Best Practices: Writing Maintainable Assets

Based on our experience with MLentory, here are best practices for writing Dagster assets:

### 1. Clear Asset Names

Use descriptive names that clearly indicate what the asset represents:

**Good:**
```python
@asset
def hf_raw_models() -> str:
    # Clear: This is HuggingFace raw models
    pass
```

**Bad:**
```python
@asset
def step1() -> str:
    # Unclear: What is step 1?
    pass
```

### 2. Document Dependencies Explicitly

Make dependencies clear in the code:

**Good:**
```python
@asset(ins={"models": AssetIn("hf_raw_models")})
def hf_normalized_models(models: str):
    # Clear dependency on hf_raw_models
    # The parameter name and AssetIn make it explicit
    pass
```

**Bad:**
```python
@asset
def hf_normalized_models():
    # Dependency is implicit or unclear
    models_path = get_hf_raw_models_path()  # Where does this come from?
    pass
```

### 3. Return Meaningful Values

Return data paths or metadata that downstream assets can use:

**Good:**
```python
@asset
def hf_raw_models() -> str:
    json_path = extract_models()
    return json_path  # Downstream assets can use this path
```

**Bad:**
```python
@asset
def hf_raw_models() -> None:
    extract_models()  # No return value - downstream assets can't use it
    pass
```

### 4. Handle Errors Gracefully

Log errors but don't fail the entire pipeline:

**Good:**
```python
@asset
def hf_raw_models():
    results = []
    for model_id in model_ids:
        try:
            metadata = fetch_model(model_id)
            results.append(metadata)
        except Exception as e:
            logger.error(f"Failed to fetch {model_id}: {e}")
            # Continue with next model
    return save_results(results)
```

**Bad:**
```python
@asset
def hf_raw_models():
    # If one model fails, entire asset fails
    results = [fetch_model(id) for id in model_ids]
    return save_results(results)
```

---

## Troubleshooting: Common Issues and Solutions

When working with Dagster, you'll encounter common issues. Here's how to solve them:

### Asset Won't Materialize

**Problem:** You try to materialize an asset, but it doesn't run or fails immediately.

**Solutions:**
- **Check dependencies:** Ensure all dependency assets exist and have been materialized
- **Verify input assets:** Make sure input assets have valid outputs
- **Check logs:** View asset logs to see error messages
- **Verify asset definition:** Ensure the asset is properly defined and registered

### Dependencies Not Running

**Problem:** You materialize an asset, but its dependencies don't run automatically.

**Solutions:**
- **Check dependency declaration:** Ensure dependencies are declared with `AssetIn`
- **Verify asset names:** Asset names must match exactly (case-sensitive)
- **Check repository:** Ensure all assets are in the same repository
- **Use `+` notation:** Materialize with `asset_name+` to include dependencies

### Performance Issues

**Problem:** Assets are running slowly or using too many resources.

**Solutions:**
- **Check parallelization:** Ensure independent assets can run in parallel
- **Review resource usage:** Check CPU and memory usage
- **Consider splitting assets:** Large assets might benefit from being split into smaller ones
- **Optimize code:** Profile asset code to find bottlenecks

---

## Key Takeaways

Dagster provides a powerful foundation for orchestrating data pipelines. Assets represent data artifacts (not just tasks), making pipelines easier to reason about. Materialization creates or updates assets, with automatic dependency handling. The Dagster UI provides comprehensive observability, showing pipeline status, data lineage, and execution history. Idempotency allows safe re-runs, incremental processing improves efficiency, and error handling ensures graceful degradation.

Understanding Dagster helps you run pipelines effectively, debug issues when they arise, and extend the system with new assets and jobs.

---

## Next Steps

- Explore [Architecture Overview](../architecture/overview.md) - See how Dagster fits into the overall system
- Check [Running Pipelines](../operations/running-pipelines.md) - Practical guide to using Dagster
- See [Extractors](../extractors/overview.md) - How extraction assets work
- Review [Transformers](../transformers/overview.md) - How transformation assets work

---

## Resources

- **Dagster Documentation:** [https://docs.dagster.io/](https://docs.dagster.io/) - Comprehensive guide to Dagster
- **Dagster Concepts:** [https://docs.dagster.io/concepts](https://docs.dagster.io/concepts) - Deep dive into Dagster concepts
- **Dagster Tutorial:** [https://docs.dagster.io/tutorial](https://docs.dagster.io/tutorial) - Hands-on tutorial
