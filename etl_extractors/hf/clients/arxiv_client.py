from __future__ import annotations

from typing import List
from datetime import datetime
import time
import logging
import traceback

import pandas as pd
import arxiv

from etl.utils import generate_mlentory_entity_hash_id


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HFArxivClient:
    """
    Client for retrieving metadata from arXiv by ID.
    """

    def get_specific_arxiv_metadata_dataset(self, arxiv_ids: List[str], batch_size: int = 200) -> pd.DataFrame:
        temp_arxiv_ids: List[str] = []
        original_to_normalized = {}  # Map normalized ID back to original
        
        for arxiv_id in arxiv_ids:
            if "." in arxiv_id:
                arxiv_id = arxiv_id.split("/")[-1]
                normalized = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
                temp_arxiv_ids.append(normalized)
                original_to_normalized[normalized] = arxiv_id
        arxiv_ids = temp_arxiv_ids

        client = arxiv.Client(page_size=batch_size)
        arxiv_data: List[dict] = []
        retrieved_ids = set()

        for i in range(0, len(arxiv_ids), batch_size):
            batch_ids = arxiv_ids[i : i + batch_size]
            logger.info(
                "Processing batch %s/%s with %s arXiv IDs",
                i // batch_size + 1,
                (len(arxiv_ids) + batch_size - 1) // batch_size,
                len(batch_ids),
            )
            try:
                search = arxiv.Search(id_list=batch_ids, max_results=batch_size)
                results = list(client.results(search))
            except Exception as e:  # noqa: BLE001
                logger.warning("Error processing arXiv papers batch: %s, creating stub entities", e)
                logger.error(traceback.format_exc())
                # Create stub entities for all IDs in this batch
                for arxiv_id in batch_ids:
                    arxiv_data.append({
                        "arxiv_id": arxiv_id,
                        "mlentory_id": generate_mlentory_entity_hash_id("Article", arxiv_id, platform="HF"),
                        "title": None,
                        "enriched": False,
                        "entity_type": "Article",
                        "platform": "HF",
                        "extraction_metadata": {
                            "extraction_method": "arXiv_API",
                            "confidence": 1.0,
                            "extraction_time": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                        },
                    })
                    retrieved_ids.add(arxiv_id)
                time.sleep(5)
                continue

            for paper in results:
                try:
                    arxiv_id = str(paper).split("/")[-1].strip()
                    if "v" in arxiv_id:
                        arxiv_id = arxiv_id.split("v")[0]
                    retrieved_ids.add(arxiv_id)
                    
                    authors_data = []
                    if hasattr(paper, "authors") and paper.authors:
                        for author in paper.authors:
                            author_name = author.name if hasattr(author, "name") else str(author)
                            authors_data.append({"name": author_name, "affiliation": None})

                    categories = paper.categories if hasattr(paper, "categories") and paper.categories else []
                    links: List[str] = []
                    if hasattr(paper, "links") and paper.links:
                        for link in paper.links:
                            if isinstance(link, dict) and "href" in link:
                                links.append(link["href"])
                            elif hasattr(link, "href"):
                                links.append(link.href)
                            else:
                                links.append(str(link))

                    doi = paper.doi if hasattr(paper, "doi") and paper.doi else None
                    journal_ref = paper.journal_ref if hasattr(paper, "journal_ref") and paper.journal_ref else None
                    comment = paper.comment if hasattr(paper, "comment") and paper.comment else None
                    primary_category = categories[0] if categories else None
                    published = paper.published.strftime("%Y-%m-%d") if paper.published else None
                    updated = paper.updated.strftime("%Y-%m-%d") if paper.updated else None

                    paper_metadata = {
                        "arxiv_id": arxiv_id,
                        "mlentory_id": generate_mlentory_entity_hash_id("Article", arxiv_id, platform="HF"),
                        "title": paper.title,
                        "published": published,
                        "updated": updated,
                        "summary": paper.summary,
                        "authors": authors_data,
                        "categories": categories,
                        "primary_category": primary_category,
                        "comment": comment,
                        "journal_ref": journal_ref,
                        "doi": doi,
                        "links": links,
                        "pdf_url": paper.pdf_url if hasattr(paper, "pdf_url") else None,
                        "enriched": True,
                        "entity_type": "Article",
                        "platform": "HF",
                        "extraction_metadata": {
                            "extraction_method": "arXiv_API",
                            "confidence": 1.0,
                            "extraction_time": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                        },
                    }
                    arxiv_data.append(paper_metadata)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Error processing arXiv paper '%s': %s, creating stub", arxiv_id, e)
                    arxiv_data.append({
                        "arxiv_id": arxiv_id,
                        "mlentory_id": generate_mlentory_entity_hash_id("Article", arxiv_id, platform="HF"),
                        "title": None,
                        "enriched": False,
                        "entity_type": "Article",
                        "platform": "HF",
                        "extraction_metadata": {
                            "extraction_method": "arXiv_API",
                            "confidence": 1.0,
                            "extraction_time": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                        },
                    })
                    retrieved_ids.add(arxiv_id)

            # Create stub entities for IDs that weren't retrieved in this batch
            for arxiv_id in batch_ids:
                if arxiv_id not in retrieved_ids:
                    logger.warning("arXiv paper '%s' not found in results, creating stub", arxiv_id)
                    arxiv_data.append({
                        "arxiv_id": arxiv_id,
                        "mlentory_id": generate_mlentory_entity_hash_id("Article", arxiv_id, platform="HF"),
                        "title": None,
                        "enriched": False,
                        "entity_type": "Article",
                        "platform": "HF",
                        "extraction_metadata": {
                            "extraction_method": "arXiv_API",
                            "confidence": 1.0,
                            "extraction_time": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                        },
                    })
                    retrieved_ids.add(arxiv_id)

            if i + batch_size < len(arxiv_ids):
                logger.info("Waiting 6 seconds before processing next batch...")
                time.sleep(6)

        return pd.DataFrame(arxiv_data)


