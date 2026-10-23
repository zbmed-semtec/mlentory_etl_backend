from typing import Dict, List

from etl_extractors.common.llm import LLMSchemaPropertyExtractor

class KaggleLLMSchemaPropertyExtractor(LLMSchemaPropertyExtractor):

    @staticmethod
    def prepare_documents(raw_records: List[dict]) -> Dict[str, str]:
        """
        Uses each model's documentation ("abstract": intendedUse or the full model documentation).

        Args:
            raw_records: model records from kaggle_models_raw.
        """
        documents = {}
        for idx, record in enumerate(raw_records):
            if not isinstance(record, dict):
                continue
            model_id = str(record.get("modelId", "")).strip() or f"unknown_{idx}"
            documents[model_id] = str(record.get("abstract") or "").strip()
        return documents
