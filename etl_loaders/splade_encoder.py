"""SPLADE query and document encoder.

Loads one SparseEncoder and reuses it. Document and query maps are pruned,
and feature names that Elasticsearch cannot store are dropped.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from sentence_transformers import SparseEncoder

DEFAULT_SPLADE_MODEL = "naver/splade-cocondenser-ensembledistil"
MAX_SEQUENCE_TOKENS = 512
DOCUMENT_TERMS = 256
QUERY_TERMS = 100

# Description token cap. None means the description is not capped; the whole
# card is still cut to MAX_SEQUENCE_TOKENS. Set from the pre-index length
# distribution before a full index run.
DESCRIPTION_TOKEN_CAP: Optional[int] = None

_ENCODER: Optional["SpladeEncoder"] = None


def unsafe_feature_token(token: str) -> bool:
    """True when a vocab token cannot be an Elasticsearch sparse_vector key.

    Dots are path separators in Elasticsearch field names, so a token such as
    ``"."`` is dropped rather than rewritten.
    """
    if not token or not str(token).strip():
        return True
    return "." in token


def sanitize_feature_name(token: str) -> Optional[str]:
    """Return a safe feature name, or None when the token must be dropped."""
    if unsafe_feature_token(token):
        return None
    return str(token)


class SpladeEncoder:
    """One shared SPLADE model for indexing and search."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or os.getenv("SPLADE_MODEL", DEFAULT_SPLADE_MODEL)
        token = os.getenv("HUGGINGFACE_HUB_TOKEN") or os.getenv("HF_TOKEN")
        kwargs = {"token": token} if token else {}
        self.model = SparseEncoder(self.model_name, **kwargs)
        self.model.max_seq_length = MAX_SEQUENCE_TOKENS
        self.tokenizer = self.model.tokenizer

    def truncate(self, text: str, max_tokens: int = MAX_SEQUENCE_TOKENS) -> str:
        from etl_loaders.vector_index_manager import _truncate_to_tokens

        return _truncate_to_tokens(self.tokenizer, text or "", max_tokens)

    def prepare_document_text(self, model_data: dict, extracted: Optional[dict] = None) -> str:
        """Card text that will be stored and encoded."""
        from etl_loaders.vector_index_manager import build_splade_searchable_text

        text = build_splade_searchable_text(
            model_data,
            extracted,
            description_max_tokens=DESCRIPTION_TOKEN_CAP,
            tokenizer=self.tokenizer if DESCRIPTION_TOKEN_CAP else None,
        )
        return self.truncate(text, MAX_SEQUENCE_TOKENS)

    def encode_documents(self, texts: Sequence[str]) -> List[Dict[str, float]]:
        return self._encode(list(texts), document=True, limit=DOCUMENT_TERMS)

    def encode_query(self, text: str) -> Dict[str, float]:
        encoded = self._encode([text or ""], document=False, limit=QUERY_TERMS)
        return encoded[0] if encoded else {}

    def raw_document_tokens(self, texts: Sequence[str]) -> List[List[Tuple[str, float]]]:
        """Positive-weight tokens before pruning and name sanitizing."""
        return self._decode(list(texts), document=True)

    def _encode(self, texts: List[str], *, document: bool, limit: int) -> List[Dict[str, float]]:
        rows = self._decode(texts, document=document)
        return [_weight_map(pairs, limit) for pairs in rows]

    def _decode(self, texts: List[str], *, document: bool) -> List[List[Tuple[str, float]]]:
        if not texts:
            return []
        encode = self.model.encode_document if document else self.model.encode_query
        embeddings = encode(
            texts,
            show_progress_bar=False,
            convert_to_sparse_tensor=True,
        )
        decoded = self.model.decode(embeddings)
        if decoded and isinstance(decoded[0], tuple):
            decoded = [decoded]
        rows: List[List[Tuple[str, float]]] = []
        for pairs in decoded:
            rows.append(
                [
                    (str(token), float(weight))
                    for token, weight in pairs
                    if float(weight) > 0
                ]
            )
        if len(rows) != len(texts):
            raise RuntimeError(
                f"SPLADE decoded {len(rows)} rows for {len(texts)} inputs"
            )
        return rows


def _weight_map(pairs: Sequence[Tuple[str, float]], limit: int) -> Dict[str, float]:
    """Drop unsafe names, keep the max weight on a collision, then the top terms."""
    ranked = sorted(pairs, key=lambda item: item[1], reverse=True)
    merged: Dict[str, float] = {}
    for token, weight in ranked:
        if weight <= 0:
            continue
        key = sanitize_feature_name(token)
        if key is None:
            continue
        current = merged.get(key)
        if current is None or weight > current:
            merged[key] = weight
    top = sorted(merged.items(), key=lambda item: item[1], reverse=True)[:limit]
    return {key: value for key, value in top}


def get_splade_encoder() -> SpladeEncoder:
    """Load the SPLADE model on first use and reuse it."""
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = SpladeEncoder()
    return _ENCODER
