"""
Preprocess Hugging Face model card markdown for LLM schema extraction.

Strips code/section chunks and rebuilds heading + text content suitable for
property extraction prompts.
"""

from __future__ import annotations

from typing import Optional

from .hf_readme_parser import MDParserChunker

_DEFAULT_CHUNKER: Optional[MDParserChunker] = None


def _get_chunker() -> MDParserChunker:
    global _DEFAULT_CHUNKER
    if _DEFAULT_CHUNKER is None:
        _DEFAULT_CHUNKER = MDParserChunker()
    return _DEFAULT_CHUNKER


def preprocess_card_for_llm(
    card: str,
    *,
    md_parser_chunker: Optional[MDParserChunker] = None,
) -> str:
    """
    Preprocess model card markdown by removing code blocks and section shells.

    Keeps heading labels and granular/table/orphan text chunks so the LLM sees
    structured prose without large code blocks.

    Args:
        card: Raw README / model card markdown.
        md_parser_chunker: Optional parser instance (for testing).

    Returns:
        Preprocessed plain text, or empty string if input is empty.
    """
    if not card or not str(card).strip():
        return ""

    chunker = md_parser_chunker or _get_chunker()
    ast = chunker.generate_ast(str(card))
    chunks = chunker.generate_chunks(ast)

    content_parts: list[str] = []
    current_heading = ""

    for chunk in chunks:
        if chunk.get("type") in ("section", "code"):
            continue

        phtext = chunk.get("phtext") or ""
        if phtext and phtext != current_heading:
            current_heading = phtext
            content_parts.append(current_heading)

        text = (chunk.get("text") or "").strip()
        if text:
            content_parts.append(text)

    return "\n".join(content_parts).strip()
