from __future__ import annotations
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime
# from etl_extractors.ai4life import AI4LifeHelper
from etl_extractors.ai4life.ai4life_helper import AI4LifeHelper
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import pandas as pd

logger = logging.getLogger(__name__)

class AI4LifeModelClient:
    """Extractor for fetching raw model metadata from the AI4Life platform."""
    
    def __init__(self, records_data):
        self.records_data = records_data
    
    def get_models_metadata(self):
        """get records from AI4Life API and set extraction timestamp."""
         # Filter records by type
        model_records = [r for r in self.records_data['data'] if r.get("type") == "model"]
        models_metadata = [self.fetch_model_metadata(model_record) for model_record in model_records]
        models_metadata_df = pd.DataFrame(models_metadata)
        return models_metadata_df
        
    def fetch_model_metadata(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch a single model's metadata.
        
        Args:
            record: The model record dump.
        
        Returns:
            Fetched model metadata following the defined schema.
        """
        flat = self._flatten_dict(record)
        model_id = str(flat.get("id") or record.get("id") or "").split("/", 1)[-1]
        mapping = {
        "modelId":       ["id"],
        "mlentory_id": AI4LifeHelper.generate_mlentory_entity_hash_id("Model", model_id, platform="AI4Life"),
        "modelArchitecture":       ["manifest.weights.pytorch_state_dict.architecture.callable"],
        "sharedBy":            ["created_by", "manifest.uploader.name", "manifest.uploader.email"],
        "trainedOn":           ["manifest.training_data.id"],
        "intendedUse":         ["manifest.description"],
        "referencePublication":["config.zenodo.doi_url"],
        "readme_file":      ["manifest.documentation"],
        "citation":         ["manifest.cite"],
        "maintainer":       ["manifest.maintainers"],
        "author":           ["manifest.authors"],
        "license":          ["manifest.license"],
        "name":             ["manifest.name"],
        "keywords":         ["manifest.tags", "config.zenodo.keywords"],
        "version":          ["versions"],
        "codeRepository":   ["git_repo"],
        "datePublished":    ["config.zenodo.metadata.publication_date"],
        "conditionsOfAccess":["config.zenodo.metadata.access_right"],
        "dateCreated":      ["created_at"],
        "dateModified":     ["last_modified"],
        "archivedAt":       ["config.zenodo.links.record_html"],
        "releaseNotes":     ["config.zenodo.notes"],
        "extraction_timestamp": self.records_data['timestamp'],
        "enriched": True,
        "entity_type": "Model",
        "platform": "AI4Life"}
     
        #id = mapping["modelId"].split("/", 1)[-1]
        id = model_id
        mapping["modelId"] = id
        readme_file =  flat.get("manifest.documentation") or ""
        mapping["readme_file"] = f"https://hypha.aicell.io/bioimage-io/artifacts/{id}/files/{readme_file}"
        ai4life_url = f"https://bioimage.io/#/artifacts/{id}"
        mapping["url"] = ai4life_url
        mapping["archivedAt"] = [mapping["archivedAt"], ai4life_url]

        # Map simple fields
        for out_key, paths in mapping.items():
            if not isinstance(paths, list) or not paths or not all(isinstance(x, str) for x in paths):
                continue
                
            values = [flat[p] for p in paths if p in flat]
            if values:
                mapping[out_key] = values[0] if len(values) == 1 else values
         
        # Process dates
        for date_field in ["dateCreated", "dateModified"]:
            if date_field in mapping and mapping[date_field] is not None:
                mapping[date_field] = datetime.utcfromtimestamp(
                    mapping[date_field]
                ).strftime('%Y-%m-%d')
        
        # Process contributor fields (authors and maintainers)
        for contributor_field in ["author", "maintainer"]:
            contributors = mapping.get(contributor_field, []) or []
            transformed = []
            
            # Normalize: sometimes it's a dict or a string, not a list
            if isinstance(contributors, (str, dict)):
                contributors = [contributors]
            elif not isinstance(contributors, list):
                contributors = []

            transformed = []
            for contributor in contributors:
                # contributor can be dict OR string
                if isinstance(contributor, str):
                    transformed.append({"name": contributor, "url": ""})
                    continue

                if not isinstance(contributor, dict):
                    continue
            
                name = contributor.get('name', '')
                orcid = contributor.get('orcid', '')
                github_user = contributor.get('github_user', '')
                
                url = (
                    f"https://orcid.org/{orcid}" if orcid else
                    f"https://github.com/{github_user}" if github_user else
                    ""
                )
                
                transformed.append({'name': name, 'url': url})
            mapping[contributor_field] = transformed
        
        # Handle special case for sharedBy
        shared_by = mapping.get("sharedBy")
        mapping["sharedBy"] = shared_by[0] if shared_by else ""
        
        # Handle special case for version
        version = mapping.get("version")
        mapping["version"] = version[-1]["version"]
        
        return mapping
    
    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
        """
        Returns:
            Dict[str, Any]: Flattened dictionary.
        """
        items = []
        for key, value in d.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(self._flatten_dict(value, new_key, sep).items())
            else:
                items.append((new_key, value))
        return dict(items)
    
    # def _wrap_metadata(self, value: Any, method: str = "hypha_api") -> List[Dict[str, Any]]:
    #     """Wrap metadata value with extraction details.

    #     Args:
    #         value (Any): The metadata value to wrap.
    #         method (str): The extraction method. Defaults to "hypha_api".

    #     Returns:
    #         List[Dict[str, Any]]: Wrapped metadata with extraction details.
    #     """
    #     return [{
    #         "data": value,
    #         "extraction_method": method,
    #         "confidence": 1,
    #         "extraction_time": self.records_data['timestamp']
    #     }]

    # def _wrap_mapped_models(self, mapped_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    #     """Wrap mapped models with metadata details.

    #     Args:
    #         mapped_models (List[Dict[str, Any]]): List of mapped model metadata.

    #     Returns:
    #         List[Dict[str, Any]]: Wrapped model metadata.
    #     """
    #     return [{k: self._wrap_metadata(v) for k, v in model.items()} for model in mapped_models]