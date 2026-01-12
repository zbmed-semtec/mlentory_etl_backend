from __future__ import annotations

from typing import Set, Dict, List
import pandas as pd
import logging

from .base import EntityIdentifier

logger = logging.getLogger(__name__)


class LicenseIdentifier(EntityIdentifier):
    """
    Extracts license ids/names from model metadata.
    Expects a 'license' column (string or list-like) and a 'modelId' column.
    """

    @property
    def entity_type(self) -> str:
        return "licenses"

    
    def _get_license_value(self, row) -> Optional[object]:
        # support both spellings
        lic = row.get("licence", None)
        if lic is None or lic == "":
            lic = row.get("license", None)
        return lic

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        """
        Unique licenses across all models.
        """
        licenses: Set[str] = set()
        if models_df is None or models_df.empty:
            return licenses

        for _, row in models_df.iterrows():
            lic = self._get_license_value(row)
            if lic is None or lic == "":
                continue

            if isinstance(lic, (list, tuple, set)):
                for x in lic:
                    if x:
                        licenses.add(str(x))
            else:
                licenses.add(str(lic))

        logger.info("Identified %d unique licenses", len(licenses))
        return licenses
    
    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        model_id -> [license(s)]
        """
        model_licenses: Dict[str, List[str]] = {}
        if models_df is None or models_df.empty:
            return model_licenses

        for _, row in models_df.iterrows():
            model_id = row.get("modelId") or row.get("id")
            if not model_id:
                continue

            lic = self._get_license_value(row)
            if lic is None or lic == "":
                model_licenses[str(model_id)] = []
                continue

            if isinstance(lic, (list, tuple, set)):
                vals = [str(x) for x in lic if x]
            else:
                vals = [str(lic)]

            model_licenses[str(model_id)] = vals

        logger.info("Identified licenses for %d models", len(model_licenses))
        return model_licenses
    
    # Optional: keep backward compatibility if anything calls the old name
    def identify_per_license(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        return self.identify_per_model(models_df)
