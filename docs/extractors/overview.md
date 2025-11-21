# Extractors Overview: Gathering Data from ML Model Repositories

Extractors are the first stage of the MLentory ETL pipeline, responsible for gathering raw, unprocessed data from external ML model repositories. Understanding how extractors work is crucial for anyone who wants to add new data sources, debug extraction issues, or understand where the data in MLentory comes from.

---

## What Are Extractors and Why Do We Need Them?

Imagine you're building a comprehensive search system for machine learning models. You want to include models from HuggingFace Hub, OpenML, AI4Life, and potentially other platforms. Each of these platforms has its own API, its own data format, and its own way of organizing information. Some provide rich metadata through well-documented APIs, while others require web scraping or have limited programmatic access.

**Extractors** are specialized modules that handle these differences. Each extractor is designed for a specific platform and knows how to:
- Connect to that platform's API or data source
- Handle authentication and rate limiting
- Fetch model metadata and related information
- Deal with platform-specific quirks and limitations
- Store the raw data in a consistent format for later processing

Think of extractors as translators—they speak the language of each platform (HuggingFace's API, OpenML's Python package, etc.) and convert everything into a common format that the rest of the pipeline can understand.

![Extractor Architecture](images/extractor-architecture.png)
*Figure 1: Extractors act as translators, converting platform-specific data formats into a common structure that the transformation stage can process.*

### The Challenge of Multiple Sources

Each platform presents unique challenges. HuggingFace has millions of models and provides rich metadata, but you need to handle pagination and rate limits carefully. OpenML focuses on ML experiments and has a different data model (runs, flows, datasets, tasks). AI4Life specializes in biomedical models and uses yet another structure.

Extractors abstract away these differences, providing a consistent interface regardless of the source. This means the transformation stage doesn't need to know whether data came from HuggingFace or OpenML—it just receives raw JSON files in a predictable structure.

---

## The Four Pillars of Extraction

Extractors have four main responsibilities that ensure reliable, comprehensive data collection:

### 1. Data Collection: Fetching What You Need

The primary job of an extractor is to fetch model metadata from external platforms. This sounds simple, but it involves many complexities:

**API Interactions** require understanding each platform's API structure. HuggingFace uses REST APIs with specific endpoints for models, datasets, and papers. OpenML provides a Python package that wraps their API. Each requires different authentication methods, handles errors differently, and has different rate limits.

**Pagination** is crucial when dealing with large datasets. HuggingFace has millions of models—you can't fetch them all at once. Extractors must handle pagination gracefully, fetching data in chunks and tracking progress to avoid missing items or fetching duplicates.

**Rate Limiting** is a reality when working with external APIs. Most platforms limit how many requests you can make per minute or hour. Good extractors respect these limits, implementing backoff strategies and queuing requests to avoid being blocked.

**Multiple Extraction Methods** provide flexibility. While API-based extraction is preferred (fast and reliable), sometimes you need file-based extraction for specific models or web scraping for data not available via API. Extractors support all these methods.

### 2. Entity Discovery: Finding Hidden Connections

Models don't exist in isolation. A BERT model might mention that it was trained on the SQuAD dataset, cites a specific arXiv paper, and is based on another model. These relationships are often embedded in model descriptions, tags, or metadata fields.

**Entity Identifiers** scan model metadata to find these references. They look for dataset names, arXiv paper IDs, base model references, keywords, licenses, and other entities mentioned in the model description. This is like reading a research paper and extracting all the citations—tedious but essential for building a complete knowledge graph.

**Reference Extraction** requires understanding different formats. HuggingFace might mention a dataset as "squad" in tags, while OpenML uses numeric IDs. Entity identifiers normalize these references, converting them into a format that can be used to fetch full metadata later.

**Relationship Building** happens as entities are discovered. When a model mentions a dataset, that creates a relationship. When it cites a paper, that's another relationship. These relationships form the foundation of the knowledge graph that will be built in the loading stage.

### 3. Data Preservation: Keeping the Original

One of the most important principles in data pipelines is preserving raw data exactly as received. This might seem wasteful—why keep data you're going to transform anyway? But raw data preservation is crucial for several reasons:

**Debugging** becomes much easier when you can inspect the original data. If a transformation fails or produces unexpected results, you can look at the raw data to understand what went wrong. Without the original, you're stuck guessing.

**Reprocessing** is possible when you have raw data. If you improve your transformation logic, you can re-run transformations without re-fetching from the source. This is especially valuable when dealing with rate-limited APIs or large datasets.

**Provenance** tracking requires keeping the original data. You need to know not just what the data is, but where it came from, when it was extracted, and how it was obtained. This information is crucial for research reproducibility and data quality assurance.

**Audit Trails** help you understand what was extracted when. If a model's metadata changes on the source platform, you can compare old and new extractions to see what changed. This is valuable for tracking model evolution over time.

### 4. Error Handling: Graceful Degradation

In a perfect world, every extraction would succeed completely. In reality, APIs fail, networks timeout, data is malformed, and platforms change their structures. Extractors must handle these failures gracefully.

**Continue on Failure** means that if one model fails to extract, the extractor continues with the next one. This prevents a single bad model from stopping the entire extraction process. Errors are logged for later investigation, but the pipeline keeps running.

**Retry Logic** handles transient failures. Network timeouts, temporary API issues, and rate limit errors are often temporary. Extractors implement retry strategies with exponential backoff, giving the system time to recover before trying again.

**Partial Success** is better than complete failure. If you're extracting 1000 models and 10 fail, you still have 990 successful extractions. Extractors are designed to maximize success rate while tracking failures for later resolution.

**Error Logging** provides detailed information about what went wrong. This includes the model ID, the error type, the error message, and context about what was being attempted. This information is crucial for debugging and improving extraction reliability.

---

## Supported Sources: A Diverse Ecosystem

MLentory currently supports three major ML model platforms, each with unique characteristics:

### HuggingFace Hub: The Largest Repository

HuggingFace Hub is the world's largest repository of machine learning models, with millions of models covering every imaginable task. It's also the most feature-rich source, providing extensive metadata through well-documented APIs.

**Rich Metadata** includes model cards (detailed Markdown descriptions), dataset information, paper citations, license information, and community engagement metrics (downloads, likes). This richness makes HuggingFace models particularly valuable for building comprehensive knowledge graphs.

**Multiple Extraction Methods** are supported. You can extract the latest N models via API, extract specific models from a file, or use a combination of both. This flexibility allows you to focus on models of particular interest while still keeping up with new additions.

**Entity Enrichment** is particularly sophisticated for HuggingFace. The extractor discovers datasets mentioned in models, finds arXiv papers cited, identifies base models, extracts keywords and licenses, and builds a rich network of relationships. This enrichment process transforms simple model metadata into a comprehensive knowledge graph foundation.

**API Quality** is excellent. HuggingFace provides well-documented REST APIs with good rate limits (especially with authentication), clear error messages, and comprehensive documentation. This makes HuggingFace extraction reliable and maintainable.

### OpenML: The Experiment Platform

OpenML takes a different approach, focusing on ML experiments rather than just models. The platform tracks runs (individual experiments), flows (reusable algorithms/models), datasets, and tasks (problem definitions).

**Experiment Data** is OpenML's strength. Each run represents a real ML experiment with results, configurations, and performance metrics. This provides valuable context about how models perform in practice, not just theoretical descriptions.

**Relationship Richness** comes from the experiment structure. Runs link to flows (models), datasets, and tasks, creating natural relationships. This structure makes it easy to understand which models work well on which datasets for which tasks.

**Optional Web Scraping** supplements API data. While the OpenML Python package provides good API access, some statistics (like download counts and community engagement) are only available on the website. The extractor can optionally use Selenium-based web scraping to gather this additional data, though this is slower and less reliable than API extraction.

**Data Model** is different from HuggingFace. Instead of models as primary entities, OpenML uses runs as the central entity, with flows (models), datasets, and tasks as related entities. This requires different extraction logic but provides valuable experiment context.

### AI4Life: Specialized Domain Knowledge

AI4Life focuses on biomedical AI models and datasets, providing specialized knowledge in life sciences and bioimaging. This domain specialization means models are often highly specialized and come with domain-specific metadata.

**Biomedical Focus** means models are typically designed for specific biological or medical tasks. This specialization is valuable for researchers in these fields who need models tailored to their domain.

**Hypha Platform** is the underlying system that hosts AI4Life models. The extractor connects to the Hypha API, which has its own structure and conventions that differ from HuggingFace and OpenML.

**Domain-Specific Metadata** includes information relevant to biomedical applications, such as organism types, imaging modalities, and biological processes. This specialized metadata requires domain knowledge to extract and interpret correctly.

---

## Extractor Architecture: Building for Maintainability

All extractors in MLentory follow a modular architecture pattern. This design choice makes extractors easier to understand, test, and extend. Instead of one monolithic extractor class that does everything, we break functionality into focused modules.

![Modular Extractor Architecture](images/modular-extractor-architecture.png)
*Figure 2: Extractors use a modular architecture with separate layers for API clients, entity identification, enrichment, and orchestration.*

### The Client Layer: Low-Level API Interactions

The **client layer** handles the nitty-gritty of API interactions. Each client is responsible for one type of entity (models, datasets, papers, etc.) and knows how to communicate with that platform's API.

**HTTP Requests** are made through these clients, which handle authentication, headers, query parameters, and response parsing. Clients abstract away platform-specific details, providing a clean interface for the rest of the extractor.

**Rate Limiting** is managed at the client level. Clients track request rates, implement backoff strategies, and queue requests to respect platform limits. This ensures we're good API citizens and avoid being blocked.

**Error Handling** happens here too. Clients catch network errors, API errors, and parsing errors, converting them into consistent exception types that the rest of the extractor can handle.

**Response Parsing** converts API responses (which might be JSON, XML, or other formats) into Python objects. This parsing handles platform-specific quirks and normalizes data structures.

### Entity Identifiers: Finding Hidden Gems

**Entity identifiers** scan model metadata to find references to related entities. This is like reading a document and extracting all the citations, links, and references.

**Pattern Matching** is used to find entity references. For example, arXiv papers might be referenced as "arXiv:2106.09685" or "https://arxiv.org/abs/2106.09685". Dataset identifiers might be simple names like "squad" or full URLs. Identifiers use regular expressions, string matching, and heuristics to find these references.

**Normalization** converts found references into a standard format. "arXiv:2106.09685" and "https://arxiv.org/abs/2106.09685" both refer to the same paper, so identifiers normalize them to a canonical form.

**Confidence Scoring** helps prioritize which references are most likely to be valid. A reference found in a model's description is more reliable than one found in a comment. Identifiers assign confidence scores that help downstream processing decide which references to pursue.

### The Enrichment Layer: Filling in the Details

Once entity identifiers have found references (like "squad" dataset or "arXiv:2106.09685" paper), the **enrichment layer** fetches full metadata for those entities.

**Batch Processing** is used for efficiency. Instead of fetching entities one at a time, the enrichment layer collects all identified entities and fetches them in batches. This reduces API calls and speeds up the process.

**Parallel Processing** further improves performance. Multiple entities can be fetched simultaneously using threads or async operations, dramatically reducing total enrichment time.

**Caching** prevents duplicate fetches. If multiple models reference the same dataset, we only fetch that dataset's metadata once. This is especially valuable for popular datasets that are referenced by many models.

**Error Handling** ensures that if one entity fails to enrich, others continue. This prevents a single bad reference from stopping the entire enrichment process.

### The High-Level Extractor: Orchestrating the Process

The **high-level extractor** coordinates all these components, managing the overall extraction workflow. It's responsible for:

**Orchestration** means deciding what to extract when. Should we extract models first, then identify entities, then enrich? Or can some steps happen in parallel? The extractor makes these decisions based on dependencies and efficiency.

**Workflow Management** handles the sequence of operations. It ensures that entity identification happens after model extraction (since we need models to scan), and enrichment happens after identification (since we need entity IDs to fetch).

**Error Recovery** happens at this level. If a step fails, the extractor decides whether to retry, skip, or abort. It tracks overall progress and ensures that partial results are saved even if the process is interrupted.

**Output Management** handles saving extracted data to disk. The extractor organizes outputs into run folders, ensures file naming is consistent, and manages metadata about the extraction run.

---

## Extraction Methods: Flexibility for Different Needs

Extractors support multiple methods for gathering data, each suited to different use cases:

### API-Based Extraction: The Primary Method

**API-based extraction** is the default and preferred method for all sources. It's fast, reliable, and respects platform rate limits.

**How it works:** Extractors use official API clients (like HuggingFace Hub's Python library or OpenML's Python package) to make direct API calls. These clients handle authentication, rate limiting, and response parsing, providing a clean interface for the extractor.

**Advantages:** APIs are designed for programmatic access, so they're fast, reliable, and well-documented. They provide structured data in predictable formats, making parsing straightforward. Rate limits are clear and manageable.

**When to use:** This is the default method for all sources. Use it whenever possible—it's the most reliable and efficient approach.

**Example usage:**
```python
from etl_extractors.hf import HFExtractor

extractor = HFExtractor()
models_df, json_path = extractor.extract_models(
    num_models=50,
    update_recent=True,
    threads=4
)
```

### File-Based Extraction: Targeted Model Selection

**File-based extraction** allows you to extract specific models listed in a configuration file. This is useful when you want to focus on particular models of interest rather than extracting everything.

**How it works:** You create a text file listing model IDs (one per line), and the extractor reads this file and extracts only those models. Results are merged with API extraction results, so you can combine both methods.

**Advantages:** Perfect for reproducing specific model sets, testing with known models, or focusing on models of particular interest. It's deterministic—the same file always produces the same results.

**When to use:** When you need specific models rather than the latest N models, when reproducing research results, or when testing with known good models.

**Configuration:** The file is typically located at `/data/refs/hf_model_ids.txt` and supports comments (lines starting with `#`) and empty lines for readability.

**Example file:**
```
# Popular transformer models
bert-base-uncased
gpt2
facebook/bart-large

# Vision models
google/vit-base-patch16-224
```

### Web Scraping: When APIs Aren't Enough

**Web scraping** uses browser automation (Selenium) to extract data from websites when APIs don't provide all needed information. This is a last resort method due to its limitations.

**How it works:** The extractor launches a browser (Chrome/Chromium), navigates to model pages, and extracts data from the HTML. This requires parsing web pages, which is fragile and slow.

**Advantages:** Can access data not available via API, such as download statistics, community engagement metrics, or information only displayed on web pages.

**Disadvantages:** Much slower than API calls (seconds per page vs. milliseconds per API call), fragile (breaks when website structure changes), requires browser installation, and can be unreliable due to network issues or page load problems.

**When to use:** Only when absolutely necessary—when data is not available via API and is critical for your use case. For OpenML, this might be dataset statistics that aren't in the API.

**Configuration:** Enable with environment variable `OPENML_ENABLE_SCRAPING=true`. Use sparingly and be prepared for it to break when websites change.

---

## Common Patterns: Proven Solutions

Extractors use several common patterns that have proven effective across different sources:

### Pattern 1: Two-Stage Extraction

Most extractors use a two-stage approach: first extract models, then enrich related entities.

**Stage 1: Extract Models** fetches model metadata from the source platform. This is relatively straightforward—you're just getting the primary entities you're interested in.

**Stage 2: Enrich Entities** takes the models from stage 1, scans them for references to other entities (datasets, papers, base models), and fetches full metadata for those entities. This creates a rich network of related information.

**Why this pattern?** It's efficient—you don't know what entities to fetch until you've seen the models. It's also flexible—you can enrich different types of entities independently. And it's fault-tolerant—if entity enrichment fails, you still have the models.

**Example flow:**
```
Extract Models → Identify Entities → Enrich Entities
     ↓                ↓                    ↓
models.json    entity_ids.json    entities.json
```

### Pattern 2: Run Folder Organization

All outputs from a single extraction run are grouped in a timestamped folder. This creates a clear association between files and makes it easy to track what was extracted together.

**Structure:** Each run gets a folder named with timestamp and UUID: `2025-01-15_12-00-00_abc123/`. All files from that run go in this folder.

**Benefits:** Easy to track which files belong together, compare outputs across runs, clean up or archive complete runs, and debug issues by looking at all files from a specific run.

**Example structure:**
```
/data/raw/hf/
└── 2025-01-15_12-00-00_abc123/
    ├── hf_models.json
    ├── hf_datasets_specific.json
    ├── arxiv_articles.json
    ├── keywords.json
    └── licenses.json
```

### Pattern 3: Parallel Processing

Extractors use multiple threads to make parallel API calls, dramatically improving performance.

**How it works:** Instead of fetching models one at a time, extractors use a thread pool to fetch multiple models simultaneously. This is especially valuable when dealing with rate limits—while one thread waits for a rate limit reset, others can continue.

**Configuration:** The number of threads is configurable via environment variables (e.g., `HF_THREADS=4`). More threads mean faster extraction but also more API load, so balance is important.

**Benefits:** Faster extraction (often 4-10x speedup), better resource utilization, and configurable based on API limits and system resources.

### Pattern 4: Error Resilience

Extractors are designed to continue processing even when individual items fail. This ensures that one bad model doesn't stop the entire extraction.

**Implementation:** Each model extraction is wrapped in a try-except block. If extraction fails, the error is logged but processing continues with the next model.

**Error logging:** Failed extractions are logged with the model ID, error type, error message, and context. This information is saved to error files for later investigation.

**Benefits:** Maximizes success rate (extract 990 models even if 10 fail), provides partial results for debugging, and allows the pipeline to complete even with some failures.

---

## Output Format: Consistent Structure

All extractors save data in JSON format, providing a consistent structure regardless of source:

### File Structure

Extracted data is saved as JSON arrays, where each element represents one entity (model, dataset, paper, etc.). This structure is simple, human-readable, and easy to process programmatically.

**Example structure:**
```json
[
  {
    "modelId": "bert-base-uncased",
    "author": "google",
    "pipeline_tag": "fill-mask",
    "tags": ["pytorch", "transformers"],
    "downloads": 5000000,
    ...
  },
  ...
]
```

### Extraction Metadata

Some extractors (OpenML, AI4Life) wrap fields with extraction metadata. This provides provenance information about how each field was obtained.

**Structure:**
```json
{
  "field_name": [
    {
      "data": <value>,
      "extraction_method": "api" | "web_scraping",
      "confidence": 1.0,
      "extraction_time": "2025-01-15T12:00:00Z"
    }
  ]
}
```

**Benefits:** Track how data was extracted (API vs. scraping), confidence scores help assess data quality, and extraction timestamps provide provenance information.

---

## Configuration: Tuning Extraction Behavior

All extractors are configured via environment variables, providing flexibility without code changes:

### HuggingFace Configuration

- `HF_NUM_MODELS`: Number of latest models to extract (default: 50)
- `HF_UPDATE_RECENT`: Prioritize recently updated models (default: true)
- `HF_THREADS`: Parallel threads for extraction (default: 4)
- `HF_MODELS_FILE_PATH`: Path to model IDs file for file-based extraction
- `HF_ENRICHMENT_THREADS`: Threads for entity enrichment (default: 4)
- `HF_BASE_MODEL_ITERATIONS`: Recursive base model depth (default: 1)
- `HF_TOKEN`: HuggingFace API token (optional, for higher rate limits)

### OpenML Configuration

- `OPENML_NUM_INSTANCES`: Number of runs to extract (default: 50)
- `OPENML_OFFSET`: Pagination offset (default: 0)
- `OPENML_THREADS`: Parallel threads (default: 4)
- `OPENML_ENRICHMENT_THREADS`: Threads for enrichment (default: 4)
- `OPENML_ENABLE_SCRAPING`: Enable web scraping (default: false)

### AI4Life Configuration

- `AI4LIFE_NUM_MODELS`: Number of models to extract (default: 50)
- `AI4LIFE_BASE_URL`: API base URL (default: https://hypha.aicell.io)
- `AI4LIFE_PARENT_ID`: Parent ID for extraction (default: bioimage-io/bioimage.io)

See the [Configuration Guide](../getting-started/configuration.md) for detailed information about all configuration options.

---

## Data Flow: From Source to Storage

Understanding the data flow helps you see how extractors fit into the larger pipeline:

### Extraction Pipeline

```
External Source (HuggingFace/OpenML/AI4Life)
    ↓
Extractor (API calls, file reading, scraping)
    ↓
Raw JSON Files
    ↓
/data/raw/<source>/<timestamp>_<uuid>/
    ├── models.json (or runs.json, records.json)
    ├── datasets.json
    ├── articles.json
    └── ...
```

### Entity Enrichment Flow

```
Models JSON
    ↓
Entity Identifiers (scan for references)
    ↓
Entity IDs (datasets: ["squad", "glue"], papers: ["2106.09685"])
    ↓
Enrichment (fetch full metadata)
    ↓
Enriched Entity JSON Files
```

This flow ensures that raw data is preserved, relationships are discovered, and related entities are fully described before transformation begins.

---

## Adding a New Extractor: Extending the System

To add support for a new data source, you'll need to:

1. **Create Extractor Module** in `etl_extractors/<source>/` with the extractor class and API clients
2. **Create Dagster Assets** in `etl/assets/<source>_extraction.py` to define extraction assets and dependencies
3. **Register in Repository** by adding to `etl/repository.py` to load assets from the module
4. **Configure** by adding environment variables and updating documentation

See [Adding a New Extractor](adding-extractor.md) for a detailed step-by-step guide.

---

## Key Takeaways

Extractors are the foundation of the MLentory pipeline, gathering raw data from diverse sources and preparing it for transformation. They use modular architectures for maintainability, support multiple extraction methods for flexibility, discover and enrich related entities to build knowledge graphs, handle errors gracefully to maximize success rates, and preserve raw data for debugging and reprocessing.

Understanding extractors helps you work with the pipeline effectively, debug issues when they arise, and extend the system to support new data sources.

---

## Next Steps

- Learn about [HuggingFace Extractor](huggingface.md) - The most comprehensive extractor with extensive entity enrichment
- Explore [OpenML Extractor](openml.md) - ML experiments platform with unique data model
- Check [AI4Life Extractor](ai4life.md) - Biomedical AI models with domain-specific metadata
- See [Adding a New Extractor](adding-extractor.md) - Step-by-step guide for extending the system
