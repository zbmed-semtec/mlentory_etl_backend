"""
SPDX license metadata extractor.
"""

from __future__ import annotations
from typing import List, Dict, Any
import pandas as pd
import logging
import spdx_lookup

from ..hf_helper import HFHelper



logger = logging.getLogger(__name__)


class HFLicenseClient:
    """
    Extracts SPDX license information for a given list of license identifiers.
    """

    def get_licenses_metadata(self, license_ids: List[str]) -> pd.DataFrame:
        """
        Retrieve SPDX license information for the given license IDs.
        
        Args:
            license_ids: List of license identifier strings (e.g., "mit", "apache-2.0")
            
        Returns:
            DataFrame containing license metadata
        """
            
        all_license_data: List[Dict[str, Any]] = []
        
        for license_id in license_ids:
            license_data: Dict[str, Any] = {
                "Name": license_id,
                "mlentory_id": HFHelper.generate_entity_hash("License", license_id),
                "Identifier": None,
                "OSI Approved": None,
                "Deprecated": None,
                "Notes": None,
                "Text": None,
                "URL": None,
                "entity_type": "License",
                "platform": "HF",
                "extraction_metadata": {
                    "extraction_method": "SPDX_API",
                    "confidence": 1.0,
                },
            }
            
            # Search by ID and by name
            spdx_license_from_id = spdx_lookup.by_id(license_id)
            spdx_license_from_name = spdx_lookup.by_name(license_id)
            spdx_license = spdx_license_from_id or spdx_license_from_name

            if spdx_license:
                if hasattr(spdx_license, "id"):
                    license_data["Identifier"] = spdx_license.id
                    license_data["URL"] = f"https://spdx.org/licenses/{spdx_license.id}.html"
                if hasattr(spdx_license, "osi_approved"):
                    license_data["OSI Approved"] = spdx_license.osi_approved
                if hasattr(spdx_license, "sources"):
                    license_data["Deprecated"] = spdx_license.sources
                if hasattr(spdx_license, "notes"):
                    license_data["Notes"] = spdx_license.notes
                if hasattr(spdx_license, "text"):
                    license_data["Text"] = spdx_license.text
                
                license_data["enriched"] = True
                all_license_data.append(license_data)
            else:
                # Create stub entity if license not found in SPDX
                logger.warning("License '%s' not found in SPDX, creating stub entity", license_id)
                license_data["enriched"] = False
                license_data["extraction_metadata"] = {
                    "extraction_method": "SPDX_API",
                    "confidence": 1.0,
                }
                all_license_data.append(license_data)
        
        return pd.DataFrame(all_license_data)

