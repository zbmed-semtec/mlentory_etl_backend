"""Backfill splade_vector for models that pass the search metadata gate.

Run inside the API container, from /app:

    python scripts/run_splade_index_update.py

Documents that already have ``splade_vector`` are skipped, so the script can
be run again after a stop.
"""

from __future__ import annotations

import json
import logging

from etl_loaders.elasticsearch_store import ElasticsearchConfig
from etl_loaders.vector_index_manager import run_splade_index_update

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("elastic_transport").setLevel(logging.WARNING)
logging.getLogger("elasticsearch").setLevel(logging.WARNING)


def main() -> None:
    config = ElasticsearchConfig.from_env()
    indexes = [
        config.ai4life_models_index,
        config.kaggle_models_index,
        config.hf_models_index,
    ]
    reports = [
        run_splade_index_update(index_name, metadata_gate=True, progress_every=100)
        for index_name in indexes
    ]
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
