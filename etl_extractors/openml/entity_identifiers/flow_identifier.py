"""
Identifier for OpenML flows (models) referenced in run metadata.
"""

from __future__ import annotations
from typing import Set
import pandas as pd
import logging

from .base import EntityIdentifier

logger = logging.getLogger(__name__)


class FlowIdentifier(EntityIdentifier):
    """
    Extracts flow IDs from OpenML run metadata.

    Looks for flow_id field in run records.
    """

    @property
    def entity_type(self) -> str:
        return "flows"

    def identify(self, runs_df: pd.DataFrame) -> Set[int]:
        flows = set()

        if runs_df.empty:
            return flows

        # Extract flow IDs from the flow_id column
        flows = self.extract_ids_from_column(runs_df, "flow_id")

        logger.info("Identified %d unique flows", len(flows))
        return flows

