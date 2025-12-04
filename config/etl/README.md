# ETL Configuration

This directory contains YAML-based configuration for MLentory ETL runs.

## Overview

ETL run configurations (extraction parameters, thread counts, etc.) are stored in `run_config.yaml`, while **sensitive credentials** (database passwords, API keys) remain in `.env` files for security.

## Configuration File

### `run_config.yaml`

Main configuration file for extraction pipelines. Contains:

- **General Configuration**: Shared settings across all platforms
- **Platform-Specific Configuration**: Settings for each data source (HuggingFace, OpenML, AI4Life)

### Structure

```yaml
general:
  default_threads: 4        # Default parallelism
  data_root: "/data"        # Base directory for outputs

platforms:
  huggingface:
    num_models: 2000        # Number of latest models to extract
    update_recent: true     # Prioritize recently updated models
    threads: 4              # Parallel threads for extraction
    models_file_path: "/data/refs/hf_model_ids.txt"  # Specific models file
    base_model_iterations: 1  # Depth to follow base model references
    enrichment_threads: 4   # Threads for enrichment operations
    offset: 0               # Pagination offset

  openml:
    num_instances: 50       # Number of run instances to extract
    offset: 0               # Pagination offset
    threads: 4              # Parallel threads for extraction
    enrichment_threads: 4   # Threads for enrichment operations
    enable_scraping: false  # Enable web scraping for additional metadata

  ai4life:
    num_models: 50          # Number of models to extract
    base_url: "https://hypha.aicell.io"  # API base URL
    parent_id: "bioimage-io/bioimage.io"  # Collection parent ID
```

## Usage in Code

The configuration is loaded via the `ConfigLoader` singleton:

```python
from etl.config import get_hf_config, get_openml_config, get_ai4life_config

# Get platform-specific config
hf_config = get_hf_config()
print(f"Extracting {hf_config.num_models} models with {hf_config.threads} threads")

# Access configuration fields
openml_config = get_openml_config()
if openml_config.enable_scraping:
    print("Web scraping is enabled")
```

### Advanced Usage

```python
from etl.config import ConfigLoader

# Load config explicitly
config = ConfigLoader.load()

# Access nested configuration
num_models = config.platforms.huggingface.num_models
data_root = config.general.data_root

# Force reload (useful for tests)
config = ConfigLoader.reload()
```

## Model Lists

For HuggingFace, specific model IDs can be provided via a text file:

**File Location:** `/data/refs/hf_model_ids.txt`

**Format:**
```text
# Comments start with #
# One model ID per line

bert-base-uncased
gpt2
facebook/opt-125m
https://huggingface.co/username/model-name  # Full URLs also supported
```

The path to this file is configured in `run_config.yaml` under `platforms.huggingface.models_file_path`.

## Environment Variables (Secrets Only)

The following credentials must remain in `.env` files:

### Neo4j
```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j
```

### Elasticsearch
```bash
ELASTIC_HOST=mlentory-elasticsearch
ELASTIC_PORT=9201
ELASTIC_SCHEME=http
ELASTIC_USER=elastic
ELASTIC_PASSWORD=changeme
ELASTIC_HF_MODELS_INDEX=hf_models
```

## Migration from Environment Variables

Previously, extraction parameters were configured via environment variables:
- `HF_NUM_MODELS` → `platforms.huggingface.num_models`
- `HF_THREADS` → `platforms.huggingface.threads`
- `OPENML_NUM_INSTANCES` → `platforms.openml.num_instances`
- etc.

These environment variables are **no longer used**. All extraction parameters are now in `run_config.yaml`.

## Validation

The configuration is validated using Pydantic models on load. Invalid values will raise descriptive errors:

```python
# Example validation errors:
# - threads must be >= 1
# - num_models must be >= 0
# - File not found: config/etl/run_config.yaml
```

## Default Values

If `run_config.yaml` is missing or incomplete, sensible defaults are provided:

- `general.default_threads`: 4
- `platforms.huggingface.num_models`: 2000
- `platforms.openml.num_instances`: 50
- `platforms.ai4life.num_models`: 50

See `etl/config.py` for all default values.

## Best Practices

1. **Version Control**: Commit `run_config.yaml` to track configuration changes.
2. **Environment-Specific Config**: Use separate config files for dev/staging/prod if needed.
3. **Secrets**: Never commit `.env` files. Keep secrets separate from run configuration.
4. **Documentation**: Update this README when adding new configuration parameters.
5. **Validation**: Let Pydantic validate your config—don't bypass type checking.

## Adding New Platforms

To add a new platform configuration:

1. **Define Pydantic Model** in `etl/config.py`:
```python
class NewPlatformConfig(BaseModel):
    num_items: int = Field(default=100, ge=0)
    threads: int = Field(default=4, ge=1)
```

2. **Add to PlatformsConfig**:
```python
class PlatformsConfig(BaseModel):
    huggingface: HuggingFaceConfig = Field(default_factory=HuggingFaceConfig)
    openml: OpenMLConfig = Field(default_factory=OpenMLConfig)
    ai4life: AI4LifeConfig = Field(default_factory=AI4LifeConfig)
    new_platform: NewPlatformConfig = Field(default_factory=NewPlatformConfig)
```

3. **Add Convenience Function**:
```python
def get_new_platform_config() -> NewPlatformConfig:
    """Get NewPlatform configuration."""
    return ConfigLoader.get_config().platforms.new_platform
```

4. **Update run_config.yaml**:
```yaml
platforms:
  new_platform:
    num_items: 100
    threads: 4
```

5. **Use in Assets**:
```python
from etl.config import get_new_platform_config

config = get_new_platform_config()
extractor.extract(num_items=config.num_items, threads=config.threads)
```

