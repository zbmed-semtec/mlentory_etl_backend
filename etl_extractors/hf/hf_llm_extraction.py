from typing import Dict, List

from etl_extractors.common.llm import LLMSchemaPropertyExtractor

class HFLLMSchemaPropertyExtractor(LLMSchemaPropertyExtractor):

    @staticmethod
    def prepare_documents(raw_records: Dict[str, List[dict]]) -> Dict[str, str]:
        """
        Turns model card chunks into one text per model, without code blocks.

        Args:
            raw_records: {model_id: list_of_chunks} from hf_identified_modelcard_chunks.
        """
        documents = {}
        for model_id, chunks in raw_records.items():
            content = ""
            current_heading = ""
            for chunk in chunks:
                if chunk.get("type") in ["section", "code"]:
                    continue

                phtext = chunk.get("phtext") or ""
                if phtext != current_heading and phtext != "":
                    current_heading = phtext
                    content += current_heading + "\n"

                text = chunk.get("text") or ""
                content += text + "\n"

            documents[model_id] = content.strip()
        return documents
