from __future__ import annotations

from typing import List
from datetime import datetime
import time
import logging

import pandas as pd
import arxiv


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HFArxivClient:
    """
    Client for retrieving metadata from arXiv by ID.
    """

    def get_specific_arxiv_metadata_dataset(self, arxiv_ids: List[str], batch_size: int = 200) -> pd.DataFrame:
        temp_arxiv_ids: List[str] = []
        for arxiv_id in arxiv_ids:
            if "." in arxiv_id:
                arxiv_id = arxiv_id.split("/")[-1]
                temp_arxiv_ids.append(arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id)
        arxiv_ids = temp_arxiv_ids

        client = arxiv.Client(page_size=batch_size)
        arxiv_data: List[dict] = []

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
                logger.warning("Error processing arXiv papers: %s", e)
                time.sleep(5)
                return pd.DataFrame()

            for paper in results:
                try:
                    arxiv_id = str(paper).split("/")[-1].strip()
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
                        "extraction_metadata": {
                            "extraction_method": "arXiv_API",
                            "confidence": 1.0,
                            "extraction_time": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                        },
                    }
                    arxiv_data.append(paper_metadata)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Error processing arXiv paper '%s': %s", arxiv_id, e)

            if i + batch_size < len(arxiv_ids):
                logger.info("Waiting 6 seconds before processing next batch...")
                time.sleep(6)

        if not arxiv_data:
            logger.warning("No arXiv papers could be successfully retrieved")
            return pd.DataFrame()
        return pd.DataFrame(arxiv_data)


