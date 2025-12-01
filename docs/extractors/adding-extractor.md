# Adding a New Extractor

Complete step-by-step guide for creating a new extractor to support a new ML model platform.

---

## Prerequisites

Before starting, make sure you understand:

- [Extractors Overview](overview.md) - High-level concepts
- [Extractors Code Flow](code-flow.md) - How extraction works internally
- Python basics (classes, functions, error handling)
- The platform's API or data access method

---

## Overview: What You're Building

An extractor consists of:

1. **Extractor class** - High-level interface for extraction
2. **Client classes** - Low-level API interactions
3. **Entity identifiers** (optional) - Find related entities
4. **Enrichment class** (optional) - Fetch related entity metadata
5. **Dagster assets** - Orchestration and dependencies
6. **Configuration** - Environment variables and settings

---

## Step 1: Create the Extractor Module Structure

Create a new directory for your platform:

```bash
mkdir -p etl_extractors/newplatform
mkdir -p etl_extractors/newplatform/clients
mkdir -p etl_extractors/newplatform/entity_identifiers
```

**Example structure:**
```
etl_extractors/newplatform/
├── __init__.py                    # Exports main classes
├── newplatform_extractor.py       # Main extractor class
├── newplatform_enrichment.py      # Entity enrichment (optional)
├── clients/
│   ├── __init__.py
│   └── newplatform_client.py      # API client
└── entity_identifiers/            # Optional
    ├── __init__.py
    └── dataset_identifier.py
```

---

## Step 2: Create the API Client

The client handles low-level API interactions. Create `etl_extractors/newplatform/clients/newplatform_client.py`:

```python
"""
API client for NewPlatform.

Handles authentication, rate limiting, and API calls.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
import time
import requests

logger = logging.getLogger(__name__)


class NewPlatformClient:
    """
    Client for interacting with NewPlatform API.
    
    Handles:
    - Authentication
    - Rate limiting
    - Error handling
    - Response parsing
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.newplatform.com",
        rate_limit_delay: float = 0.1,
    ):
        """
        Initialize the client.
        
        Args:
            api_key: API key for authentication (optional)
            base_url: Base URL for API
            rate_limit_delay: Delay between requests (seconds)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        
        # Set up authentication
        if api_key:
            self.session.headers.update({
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            })
    
    def get_models(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Fetch models from the API.
        
        Args:
            limit: Maximum number of models to fetch
            offset: Pagination offset
            
        Returns:
            List of model dictionaries
        """
        url = f"{self.base_url}/models"
        params = {
            "limit": limit,
            "offset": offset,
        }
        
        try:
            # Respect rate limits
            time.sleep(self.rate_limit_delay)
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            return data.get("models", [])
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch models: {e}")
            raise
    
    def get_model_by_id(self, model_id: str) -> Dict[str, Any]:
        """
        Fetch a specific model by ID.
        
        Args:
            model_id: Model identifier
            
        Returns:
            Model dictionary
        """
        url = f"{self.base_url}/models/{model_id}"
        
        try:
            time.sleep(self.rate_limit_delay)
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch model {model_id}: {e}")
            raise
```

**Key Points:**

- Handle authentication (API keys, tokens)
- Implement rate limiting (respect API limits)
- Use proper error handling (try/except, logging)
- Return consistent data structures

---

## Step 3: Create the Extractor Class

Create `etl_extractors/newplatform/newplatform_extractor.py`:

```python
"""
High-level extractor for NewPlatform metadata.

Coordinates client classes to extract and persist raw artifacts
to the data volume under /data/raw/newplatform.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List
import logging
import json
from datetime import datetime

import pandas as pd

from .clients import NewPlatformClient


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class NewPlatformExtractor:
    """
    High-level wrapper around NewPlatform client to extract raw artifacts
    and persist them to the data volume under /data/raw/newplatform.
    """
    
    def __init__(
        self,
        client: Optional[NewPlatformClient] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the extractor.
        
        Args:
            client: Pre-configured client (optional)
            api_key: API key for authentication (optional)
        """
        self.client = client or NewPlatformClient(api_key=api_key)
    
    def extract_models(
        self,
        num_models: int = 50,
        threads: int = 4,
        output_root: Path | None = None,
        save_csv: bool = False,
    ) -> tuple[pd.DataFrame, Path]:
        """
        Extract model metadata.
        
        Args:
            num_models: Number of models to extract
            threads: Number of threads for parallel processing
            output_root: Root directory for outputs
            save_csv: Whether to also save as CSV
            
        Returns:
            Tuple of (DataFrame, json_path)
        """
        logger.info(f"Extracting {num_models} models from NewPlatform")
        
        # Fetch models from API
        models = []
        offset = 0
        
        while len(models) < num_models:
            batch = self.client.get_models(
                limit=min(50, num_models - len(models)),
                offset=offset,
            )
            
            if not batch:
                break
            
            models.extend(batch)
            offset += len(batch)
            
            if len(batch) < 50:  # Last page
                break
        
        # Convert to DataFrame
        df = pd.DataFrame(models[:num_models])
        
        # Save to JSON
        json_path = self._save_dataframe_to_json(
            df, output_root=output_root, save_csv=save_csv, suffix="newplatform_models"
        )
        
        logger.info(f"Extracted {len(df)} models, saved to {json_path}")
        return df, json_path
    
    def extract_specific_models(
        self,
        model_ids: List[str],
        threads: int = 4,
        output_root: Path | None = None,
    ) -> tuple[pd.DataFrame, Path]:
        """
        Extract specific models by ID.
        
        Args:
            model_ids: List of model IDs to extract
            threads: Number of threads for parallel processing
            output_root: Root directory for outputs
            
        Returns:
            Tuple of (DataFrame, json_path)
        """
        logger.info(f"Extracting {len(model_ids)} specific models")
        
        # Fetch models in parallel (simplified - use ThreadPoolExecutor in real implementation)
        models = []
        for model_id in model_ids:
            try:
                model = self.client.get_model_by_id(model_id)
                models.append(model)
            except Exception as e:
                logger.error(f"Failed to extract model {model_id}: {e}")
        
        df = pd.DataFrame(models)
        json_path = self._save_dataframe_to_json(
            df, output_root=output_root, save_csv=False, suffix="newplatform_models_specific"
        )
        
        return df, json_path
    
    def _save_dataframe_to_json(
        self,
        df: pd.DataFrame,
        output_root: Path | None = None,
        save_csv: bool = False,
        suffix: str = "newplatform",
    ) -> Path:
        """
        Save DataFrame to JSON file.
        
        Args:
            df: DataFrame to save
            output_root: Root directory (defaults to /data/1_raw/newplatform)
            save_csv: Whether to also save as CSV
            suffix: Filename suffix
            
        Returns:
            Path to saved JSON file
        """
        if output_root is None:
            output_root = Path("/data/1_raw/newplatform")
        else:
            output_root = Path(output_root) / "1_raw" / "newplatform"
        
        output_root.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        json_filename = f"{timestamp}_{suffix}.json"
        json_path = output_root / json_filename
        
        # Save as JSON
        df.to_json(json_path, orient='records', indent=2)
        logger.info(f"Saved {len(df)} records to {json_path}")
        
        # Optionally save as CSV
        if save_csv:
            csv_path = json_path.with_suffix('.csv')
            df.to_csv(csv_path, index=False)
            logger.info(f"Also saved to {csv_path}")
        
        return json_path
```

**Key Points:**

- High-level interface that coordinates clients
- Handles pagination if needed
- Saves data to consistent locations
- Returns DataFrames and file paths
- Includes error handling and logging

---

## Step 4: Create Entity Identifiers (Optional)

If your platform has related entities (datasets, papers, etc.), create identifiers:

```python
# etl_extractors/newplatform/entity_identifiers/dataset_identifier.py

from __future__ import annotations

from typing import Set, Dict, List
import pandas as pd
import re

from etl_extractors.hf.entity_identifiers.base import EntityIdentifier


class DatasetIdentifier(EntityIdentifier):
    """
    Identifies dataset references from NewPlatform model metadata.
    """
    
    @property
    def entity_type(self) -> str:
        return "datasets"
    
    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        """
        Extract unique dataset names from models.
        
        Args:
            models_df: DataFrame with model metadata
            
        Returns:
            Set of dataset identifiers
        """
        datasets = set()
        
        # Check various fields that might contain dataset references
        for field in ["description", "tags", "metadata"]:
            if field in models_df.columns:
                for value in models_df[field].dropna():
                    # Extract dataset names (customize pattern for your platform)
                    found = re.findall(r'dataset[:\s]+(\w+)', str(value), re.IGNORECASE)
                    datasets.update(found)
        
        return datasets
    
    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Extract dataset references per model.
        
        Args:
            models_df: DataFrame with model metadata
            
        Returns:
            Dict mapping model_id to list of dataset identifiers
        """
        result = {}
        
        for _, row in models_df.iterrows():
            model_id = row.get("id", "")
            datasets = []
            
            # Extract datasets from this model's metadata
            description = str(row.get("description", ""))
            found = re.findall(r'dataset[:\s]+(\w+)', description, re.IGNORECASE)
            datasets.extend(found)
            
            if datasets:
                result[model_id] = datasets
        
        return result
```

**Key Points:**

- Inherit from `EntityIdentifier` base class
- Implement `entity_type`, `identify()`, and `identify_per_model()`
- Use pattern matching to find entity references
- Return consistent data structures

---

## Step 5: Create Enrichment Class (Optional)

If you have entity identifiers, create an enrichment class:

```python
# etl_extractors/newplatform/newplatform_enrichment.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set, Optional
import logging

import pandas as pd

from .newplatform_extractor import NewPlatformExtractor
from .entity_identifiers import DatasetIdentifier


logger = logging.getLogger(__name__)


class NewPlatformEnrichment:
    """
    Orchestrates the identification and extraction of related entities.
    """
    
    def __init__(self, extractor: Optional[NewPlatformExtractor] = None):
        self.extractor = extractor or NewPlatformExtractor()
        
        # Register entity identifiers
        self.identifiers = {
            "datasets": DatasetIdentifier(),
        }
    
    def identify_datasets(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """Identify dataset references from models."""
        identifier = self.identifiers["datasets"]
        return identifier.identify_per_model(models_df)
    
    def enrich_datasets(self, dataset_names: List[str]) -> pd.DataFrame:
        """Fetch full metadata for datasets."""
        # Implement dataset fetching logic
        datasets = []
        for name in dataset_names:
            try:
                # Fetch dataset metadata from API
                dataset = self.extractor.client.get_dataset(name)
                datasets.append(dataset)
            except Exception as e:
                logger.error(f"Failed to fetch dataset {name}: {e}")
        
        return pd.DataFrame(datasets)
```

---

## Step 6: Create Configuration

Add configuration to `etl/config.py`:

```python
# Add to etl/config.py

class NewPlatformConfig(BaseModel):
    """Configuration for NewPlatform extraction."""
    
    num_models: int = Field(default=50, ge=0)
    threads: int = Field(default=4, ge=1)
    api_key: Optional[str] = Field(default=None)
    base_url: str = Field(default="https://api.newplatform.com")


def get_newplatform_config() -> NewPlatformConfig:
    """Load NewPlatform configuration from environment."""
    return NewPlatformConfig(
        num_models=int(os.getenv("NEWPLATFORM_NUM_MODELS", "50")),
        threads=int(os.getenv("NEWPLATFORM_THREADS", "4")),
        api_key=os.getenv("NEWPLATFORM_API_KEY"),
        base_url=os.getenv("NEWPLATFORM_BASE_URL", "https://api.newplatform.com"),
    )
```

**Environment Variables:**
Add to `.env.example`:
```bash
# NewPlatform Configuration
NEWPLATFORM_NUM_MODELS=50
NEWPLATFORM_THREADS=4
NEWPLATFORM_API_KEY=your_api_key_here
NEWPLATFORM_BASE_URL=https://api.newplatform.com
```

---

## Step 7: Create Dagster Assets

Create `etl/assets/newplatform_extraction.py`:

```python
"""
Dagster assets for NewPlatform extraction.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional
import logging

import pandas as pd

from dagster import asset, AssetIn

from etl_extractors.newplatform import NewPlatformExtractor
from etl.config import get_newplatform_config


logger = logging.getLogger(__name__)


@asset(group_name="newplatform", tags={"pipeline": "newplatform_etl"})
def newplatform_run_folder() -> str:
    """
    Create a unique run folder for this materialization.
    
    Returns:
        Path to the run-specific output directory
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]
    run_folder_name = f"{timestamp}_{run_id}"
    
    run_folder = Path("/data/1_raw/newplatform") / run_folder_name
    run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created run folder: {run_folder}")
    return str(run_folder)


@asset(
    group_name="newplatform",
    ins={"run_folder": AssetIn("newplatform_run_folder")},
    tags={"pipeline": "newplatform_etl"}
)
def newplatform_raw_models(run_folder: str) -> Tuple[str, str]:
    """
    Extract models from NewPlatform.
    
    Args:
        run_folder: Path to the run-specific output directory
    
    Returns:
        Tuple of (models_json_path, run_folder)
    """
    config = get_newplatform_config()
    extractor = NewPlatformExtractor(api_key=config.api_key)
    
    output_root = Path(run_folder).parent.parent  # Go up to /data
    df, output_path = extractor.extract_models(
        num_models=config.num_models,
        threads=config.threads,
        output_root=output_root,
    )
    
    # Move file to run folder
    run_path = Path(run_folder)
    final_path = run_path / "newplatform_models.json"
    
    # Load and save to run folder
    with open(output_path, 'r') as f:
        models = json.load(f)
    
    with open(final_path, 'w') as f:
        json.dump(models, f, indent=2)
    
    # Clean up temporary file
    Path(output_path).unlink(missing_ok=True)
    
    logger.info(f"Extracted {len(df)} models")
    return (str(final_path), run_folder)
```

**Key Points:**

- Create run folder asset first
- Extract models asset depends on run folder
- Save outputs to run folder
- Return paths for downstream assets

---

## Step 8: Register Assets in Repository

Add to `etl/repository.py`:

```python
from etl.assets import newplatform_extraction as newplatform_extraction_module

@repository
def mlentory_etl_repository():
    # ... existing assets ...
    newplatform_assets = load_assets_from_modules([newplatform_extraction_module])
    return [*hf_extraction_assets, ..., *newplatform_assets]
```

---

## Step 9: Create Module Exports

Create `etl_extractors/newplatform/__init__.py`:

```python
"""
NewPlatform extractor module.
"""

from .newplatform_extractor import NewPlatformExtractor
from .newplatform_enrichment import NewPlatformEnrichment

__all__ = [
    "NewPlatformExtractor",
    "NewPlatformEnrichment",
]
```

---

## Step 10: Testing

Create tests in `tests/test_newplatform_extractor.py`:

```python
"""Tests for NewPlatform extractor."""

import pytest
from pathlib import Path
from etl_extractors.newplatform import NewPlatformExtractor


def test_extractor_initialization():
    """Test extractor can be initialized."""
    extractor = NewPlatformExtractor()
    assert extractor is not None


def test_extract_models(tmp_path):
    """Test model extraction."""
    extractor = NewPlatformExtractor()
    
    df, json_path = extractor.extract_models(
        num_models=10,
        output_root=tmp_path,
    )
    
    assert len(df) > 0
    assert Path(json_path).exists()
    
    # Verify JSON structure
    with open(json_path, 'r') as f:
        models = json.load(f)
    
    assert isinstance(models, list)
    assert len(models) > 0
    assert "id" in models[0]  # Adjust based on your schema
```

---

## Common Patterns and Best Practices

### Pattern 1: Error Resilience

Always handle errors gracefully:

```python
def extract_models(self, model_ids: List[str]) -> List[Dict]:
    models = []
    for model_id in model_ids:
        try:
            model = self.client.get_model_by_id(model_id)
            models.append(model)
        except Exception as e:
            logger.error(f"Failed to extract {model_id}: {e}")
            # Continue with next model
    return models
```

### Pattern 2: Rate Limiting

Respect API rate limits:

```python
import time

def get_models(self):
    time.sleep(self.rate_limit_delay)  # Wait between requests
    return self.session.get(url)
```

### Pattern 3: Pagination

Handle paginated APIs:

```python
def extract_all_models(self, limit: int):
    models = []
    offset = 0
    
    while len(models) < limit:
        batch = self.client.get_models(limit=50, offset=offset)
        if not batch:
            break
        models.extend(batch)
        offset += len(batch)
    
    return models[:limit]
```

### Pattern 4: Parallel Processing

Use threads for parallel API calls:

```python
from concurrent.futures import ThreadPoolExecutor

def extract_models_parallel(self, model_ids: List[str], threads: int = 4):
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [
            executor.submit(self.client.get_model_by_id, model_id)
            for model_id in model_ids
        ]
        models = [f.result() for f in futures]
    return models
```

---

## Checklist

Before considering your extractor complete:

- [ ] Extractor class implemented with `extract_models()` method
- [ ] API client handles authentication and rate limiting
- [ ] Data is saved to `/data/1_raw/newplatform/` with run folders
- [ ] Dagster assets created and registered
- [ ] Configuration added to `etl/config.py`
- [ ] Environment variables documented in `.env.example`
- [ ] Module exports in `__init__.py`
- [ ] Basic tests written
- [ ] Error handling implemented
- [ ] Logging added throughout
- [ ] Documentation updated

---

## Next Steps

After creating your extractor:

1. **Test it** - Run extraction manually to verify it works
2. **Create transformer** - See [Adding a Transformer](../transformers/adding-transformer.md)
3. **Create loader** - See [Loaders Code Flow](../loaders/code-flow.md)
4. **Update documentation** - Add your platform to relevant docs

---

## Getting Help

- Review [Extractors Code Flow](code-flow.md) for detailed flow explanation
- Check [HuggingFace Extractor](huggingface.md) for a complete example
- Look at [OpenML Extractor](openml.md) for another example
- See [Extractors Overview](overview.md) for high-level concepts

---

## Example: Complete Minimal Extractor

Here's a minimal working example:

```python
# etl_extractors/simple/simple_extractor.py

from pathlib import Path
import json
import requests
import pandas as pd

class SimpleExtractor:
    def __init__(self):
        self.base_url = "https://api.example.com"
    
    def extract_models(self, num_models: int = 50) -> tuple[pd.DataFrame, Path]:
        # Fetch models
        response = requests.get(f"{self.base_url}/models?limit={num_models}")
        models = response.json()
        
        # Convert to DataFrame
        df = pd.DataFrame(models)
        
        # Save to JSON
        output_path = Path("/data/1_raw/simple/models.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_json(output_path, orient='records', indent=2)
        
        return df, output_path
```

This minimal example shows the core pattern - fetch data, convert to DataFrame, save to JSON.
