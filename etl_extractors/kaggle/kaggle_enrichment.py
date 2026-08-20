"""
Enrichment orchestration for Kaggle extraction.

Holds the registry of entity identifiers used by the enrichment assets to
find related entities inside already-fetched model metadata.
"""

from __future__ import annotations

import logging
from typing import Dict

from etl_extractors.kaggle.entity_identifiers.base import EntityIdentifier
from etl_extractors.kaggle.entity_identifiers.instance_identifier import InstanceIdentifier
from etl_extractors.kaggle.entity_identifiers.license_identifier import LicenseIdentifier
from etl_extractors.kaggle.entity_identifiers.keyword_identifier import KeywordIdentifier
from etl_extractors.kaggle.entity_identifiers.framework_identifier import FrameworkIdentifier

logger = logging.getLogger(__name__)


class KaggleEnrichment:
    """Registry of entity identifiers for Kaggle model metadata."""

    def __init__(self) -> None:
        self.identifiers: Dict[str, EntityIdentifier] = {
            "instances": InstanceIdentifier(),
            "licenses": LicenseIdentifier(),
            "keywords": KeywordIdentifier(),
            "frameworks": FrameworkIdentifier(),
            
        }