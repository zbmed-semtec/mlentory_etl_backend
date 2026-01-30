"""
Identifier for chunks generated from abstract syntax tree (ast) of model cards.
"""

from __future__ import annotations
from typing import Set, Dict, List
import pandas as pd
import logging

from .base import EntityIdentifier
from ..hf_readme_parser import MDParserChunker

logger = logging.getLogger(__name__)


class ChunkIdentifier(EntityIdentifier):
    """
    Generates chunks from AST of HF model cards.
    
    """

    @property
    def entity_type(self) -> str:
        return "chunk"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        # not used for this step, so just return an empty set
        return set()

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[dict]]:
        """
        Extract abstract syntax trees per model and then generates chunks.

        Returns:
            Dict mapping model_id to list of chunks generated from that model card's AST
        """
        model_chunks: Dict[str, List[str]] = {}

        md_parser_chunker = MDParserChunker()

        if models_df.empty:
            return model_chunks

        for _, row in models_df.iterrows():
            model_id = row.get("modelId", "")
            if not model_id:
                continue

            card = row.get("card", "")

            ast = md_parser_chunker.generate_ast(card)

            if ast:
                model_chunks[model_id] = md_parser_chunker.generate_chunks(ast)

            else:
                model_chunks[model_id] = []

        logger.info("Generated chunks for %d models", len(model_chunks))
        return model_chunks

