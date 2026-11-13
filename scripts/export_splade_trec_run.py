"""Write a TREC run for SPLADE from a TREC topics file.

Topics use the usual ``<top>`` / ``<num>`` / ``<title>`` blocks. The query is
the title. Each line of the run is:

    qid Q0 docid rank score mlentory_splade

The document id is the MLentory URI stored in ``db_identifier``. The search
service is called directly, not over HTTP. At most 100 hits are written per
query.

    python scripts/export_splade_trec_run.py topics.txt run.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import List, Tuple

from api.services.splade_search_service import splade_search_service

_RUN_TAG = "mlentory_splade"
_MLENTORY_PREFIX = "https://w3id.org/mlentory/mlentory_graph/"


def read_trec_topics(path: str) -> List[Tuple[str, str]]:
    """Return (topic id, title) pairs from a TREC topics file."""
    text = open(path, encoding="utf-8").read()
    topics: List[Tuple[str, str]] = []
    for block in re.split(r"</top>", text, flags=re.IGNORECASE):
        number = re.search(r"<num>\s*(?:Number:\s*)?(\S+)", block, flags=re.IGNORECASE)
        title = re.search(
            r"<title>\s*(.*?)(?=<desc>|<narr>|</top>|$)",
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not number or not title:
            continue
        query = " ".join(title.group(1).split())
        if query:
            topics.append((number.group(1), query))
    return topics


def document_id(db_identifier) -> str:
    """One TREC document id taken from ``db_identifier``."""
    identifiers = db_identifier if isinstance(db_identifier, list) else [db_identifier]
    identifiers = [item for item in identifiers if isinstance(item, str) and item.strip()]
    for identifier in identifiers:
        if identifier.startswith(_MLENTORY_PREFIX):
            return identifier.replace(" ", "_")
    if identifiers:
        return identifiers[0].replace(" ", "_")
    return "missing"


def write_run(topics_path: str, run_path: str) -> int:
    topics = read_trec_topics(topics_path)
    lines: List[str] = []
    for topic_id, query in topics:
        result = splade_search_service.splade_search(
            query=query,
            limit=100,
            page=1,
            facets=[],
        )
        for rank, model in enumerate(result["models"], start=1):
            score = float(model.score)
            lines.append(
                f"{topic_id} Q0 {document_id(model.db_identifier)} {rank} {score:.6f} {_RUN_TAG}"
            )
    with open(run_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        if lines:
            handle.write("\n")
    return len(topics)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a SPLADE TREC run.")
    parser.add_argument("topics", help="TREC topics file")
    parser.add_argument("run", help="TREC run file to write")
    args = parser.parse_args()
    count = write_run(args.topics, args.run)
    print(f"Wrote {args.run} from {count} topics", file=sys.stderr)


if __name__ == "__main__":
    main()
