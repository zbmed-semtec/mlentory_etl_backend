import torch
from sentence_transformers import SentenceTransformer
import numpy as np

class ChunkRankingEngine:

    def __init__(
        self, logger, model_name="google/embeddinggemma-300M", document_batchsize=32, hf_token: str = None
    ):

        self.logger = logger
        self.model_name = model_name
        self.document_batchsize = document_batchsize

        self.initialize_model(hf_token)

    def initialize_model(self, hf_token: str) -> None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(self.model_name, token=hf_token, device=device)

    def compute_property_embedding(self, property_dsc: str) -> np.ndarray:
        return self.model.encode_query(f"task: search result | query: {property_dsc}")

    def compute_document_embedding(self, documents: str) -> np.ndarray:
        return self.model.encode_document(documents)

    def compute_chunk_embedding(self, chunk: dict) -> np.ndarray:
        pp_chunk = self._preprocess_chunk(chunk)

        return self.model.encode_document(
            pp_chunk, batch_size=self.document_batchsize
        )

    def _preprocess_chunk(self, chunk: dict):
        return f"title: {chunk['phtext']} | text: {chunk['text']}"

    def compute_similarity(self, query_embedding: np.ndarray, chunks: list[dict]) -> list[dict]:
        valid_chunks = [c for c in chunks if "emb" in c]
        if not valid_chunks:
            return []

        doc_embeddings = [c["emb"] for c in valid_chunks]
        similarities = self.model.similarity(query_embedding, doc_embeddings)

        results = []
        scores = similarities[0] 
        
        for chunk, score in zip(valid_chunks, scores):
            results.append({
                "id": chunk.get("id"), 
                "sim_score": float(score)
            })

        results.sort(key=lambda x: x["sim_score"], reverse=True)

        return results
