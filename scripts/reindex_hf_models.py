"""
Reindex Hugging Face models with updated mapping.

Workflow:
- Create a temporary index with the new mapping (HFModelDocument).
- Copy data from the existing index into the temporary index.
- Drop and recreate the original index with the new mapping.
- Copy data back from the temporary index.
- Drop the temporary index.

Usage:
    python scripts/reindex_hf_models.py \
        --source-index hf_models \
        --temp-index hf_models_tmp
"""

from __future__ import annotations

import argparse
import logging
from typing import Optional

from elasticsearch import Elasticsearch

from etl_loaders.elasticsearch_store import (
    ElasticsearchConfig,
    create_elasticsearch_client,
)
from etl_loaders.hf_index_loader import HFModelDocument

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def ensure_index(es: Elasticsearch, index_name: str) -> None:
    """Create index with HFModelDocument mapping."""
    if es.indices.exists(index=index_name):
        logger.info("Index %s already exists; deleting before recreation", index_name)
        es.indices.delete(index=index_name)
    HFModelDocument.init(index=index_name, using=es)
    es.indices.refresh(index=index_name)
    logger.info("Index %s created with HFModelDocument mapping", index_name)


def reindex(
    es: Elasticsearch, source: str, dest: str, batch_size: int = 1000, refresh: bool = True
) -> None:
    """Run Elasticsearch reindex from source to dest."""
    logger.info("Reindexing from %s -> %s", source, dest)
    es.reindex(
        body={
            "source": {"index": source, "size": batch_size},
            "dest": {"index": dest, "op_type": "create"},
        },
        wait_for_completion=True,
        refresh=refresh,
        requests_per_second=-1,
    )
    if refresh:
        es.indices.refresh(index=dest)
    count = es.count(index=dest)["count"]
    logger.info("Reindex complete: %s documents now in %s", count, dest)


def run(source_index: str, temp_index: str, cfg: Optional[ElasticsearchConfig] = None) -> None:
    config = cfg or ElasticsearchConfig.from_env()
    es = create_elasticsearch_client(config)

    if not es.indices.exists(index=source_index):
        raise RuntimeError(f"Source index {source_index} does not exist")

    # Step 1: temp index with new mapping
    ensure_index(es, temp_index)

    # Step 2: copy data old -> temp
    reindex(es, source_index, temp_index)

    # Step 3: drop old and recreate with new mapping
    logger.info("Deleting old index %s", source_index)
    es.indices.delete(index=source_index)
    ensure_index(es, source_index)

    # Step 4: copy data temp -> new
    reindex(es, temp_index, source_index)

    # Step 5: drop temp
    logger.info("Deleting temporary index %s", temp_index)
    es.indices.delete(index=temp_index)
    logger.info("Reindexing finished successfully.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reindex HF models with updated mapping.")
    parser.add_argument(
        "--source-index",
        default=None,
        help="Existing HF models index name. Defaults to ELASTIC_HF_MODELS_INDEX or 'hf_models'.",
    )
    parser.add_argument(
        "--temp-index",
        default=None,
        help="Temporary index name to use. Defaults to '<source-index>_tmp'.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = ElasticsearchConfig.from_env()
    source_index = args.source_index or cfg.hf_models_index
    temp_index = args.temp_index or f"{source_index}_tmp"
    run(source_index=source_index, temp_index=temp_index, cfg=cfg)


if __name__ == "__main__":
    main()

