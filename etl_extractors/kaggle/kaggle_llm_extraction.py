from typing import Dict, List

from etl_extractors.common.llm import LLMSchemaPropertyExtractor

class KaggleLLMSchemaPropertyExtractor(LLMSchemaPropertyExtractor):

    @staticmethod
    def prepare_documents(raw_records: List[dict]) -> Dict[str, str]:
        """
        Uses each model's documentation: abstract, else intendedUse, else documentation_content.
        Records without a modelId or without text are skipped.

        Args:
            raw_records: model records from kaggle_models_raw.
        """
        documents = {}
        for record in raw_records:
            if not isinstance(record, dict):
                continue
            model_id = str(record.get("modelId") or "").strip()
            text = str(
                record.get("abstract")
                or record.get("intendedUse")
                or record.get("documentation_content")
                or ""
            ).strip()
            if model_id and text:
                documents[model_id] = text
        return documents
