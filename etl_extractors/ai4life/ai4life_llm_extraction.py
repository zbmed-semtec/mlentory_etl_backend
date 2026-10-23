from typing import Dict, List

from etl_extractors.common.llm import LLMSchemaPropertyExtractor

class AI4LifeLLMSchemaPropertyExtractor(LLMSchemaPropertyExtractor):

    @staticmethod
    def prepare_documents(raw_records: List[dict]) -> Dict[str, str]:
        """
        Joins each model's description, intended use and name.

        Args:
            raw_records: model records from ai4life_models_raw.
        """
        documents = {}
        for idx, record in enumerate(raw_records):
            if not isinstance(record, dict):
                continue
            model_id = str(record.get("modelId", "")).strip() or f"unknown_{idx}"
            text_parts = [
                str(record.get("description", "")).strip(),
                str(record.get("intendedUse", "")).strip(),
                str(record.get("name", "")).strip(),
            ]
            documents[model_id] = "\n\n".join([part for part in text_parts if part])
        return documents
