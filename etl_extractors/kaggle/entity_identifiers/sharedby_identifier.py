from __future__ import annotations

from typing import Dict, List, Set
import logging

import pandas as pd

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class SharedByIdentifier(EntityIdentifier):
    """Identify sharedBy entities from Kaggle model metadata.

    On Kaggle this is the account that uploaded the model - a user or an
    organization - taken from the ``author`` field on the models endpoint.
    Instances inherit it from their parent, so both come through the same
    ``sharedBy`` column.
    """

    @property
    def entity_type(self) -> str:
        return "sharedby"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        values: Set[str] = set()
        if models_df is None or models_df.empty:
            return values

        for _, row in models_df.iterrows():
            sharedby = self._extract_sharedby(row)
            if sharedby:
                values.add(sharedby)

        logger.info("Identified %d unique Kaggle sharedBy entities", len(values))
        return values

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        model_values: Dict[str, List[str]] = {}
        if models_df is None or models_df.empty:
            return model_values

        for _, row in models_df.iterrows():
            model_id = row.get("modelId") or row.get("id") or row.get("model_id") or row.get("name")
            if not model_id:
                continue
            sharedby = self._extract_sharedby(row)
            model_values[str(model_id)] = [sharedby] if sharedby else []

        logger.info("Identified Kaggle sharedBy values for %d models", len(model_values))
        return model_values

    @staticmethod
    def _extract_sharedby(row: pd.Series) -> str:
        """
        Read the owner name off a row.

        Only ``sharedBy`` and the plain form of ``author`` are used.
        ``parent_name`` is deliberately not a fallback: on an instance row it
        holds the parent model's *title*, not its owner, so it would mint
        entities like "Phi-3" as if they were people.
        """
        for column in ("sharedBy", "author"):
            value = row.get(column)
            if value is None:
                continue
            text = str(value).strip()
            # pandas turns missing cells into the float nan, whose str() is
            # "nan" - a string that would otherwise become a real entity.
            if not text or text.lower() in {"none", "nan"}:
                continue
            # models_client writes author as a JSON array of {name, url}; the
            # plain owner string lives in sharedBy, so skip the encoded form.
            if text.startswith("[") or text.startswith("{"):
                continue
            return text
        return ""