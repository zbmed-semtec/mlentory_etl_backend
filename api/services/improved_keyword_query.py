"""Keyword query that ranks exact names, tasks, and property values above loose text."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

# Tokens that match too many cards to be useful as free-text requirements.
_STOPWORDS = frozenset({"a", "an", "the", "to", "of", "for", "and", "in", "on", "with", "from"})

# Whole-value fields. A full match is a strong hit; these are not scanned with wildcards.
_EXACT_KEYWORD_FIELDS = (
    "keywords",
    "shared_by",
    "datasets",
    "baseModels",
    "model_category",
    "domain",
)

def _normalize_slug(text: str) -> str:
    slug = re.sub(r"[\s_]+", "-", text.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def _meaningful_tokens(query: str) -> List[str]:
    tokens: List[str] = []
    for token in re.split(r"[ \-_\.]+", query.lower()):
        token = token.strip()
        if len(token) < 2 or token in _STOPWORDS or token in tokens:
            continue
        tokens.append(token)
    return tokens


def _constant_filter(clause: Dict[str, Any], boost: float) -> Dict[str, Any]:
    return {"constant_score": {"filter": clause, "boost": boost}}


def _raw_name_term(value: str) -> Dict[str, Any]:
    """Exact `name.raw` match. Case does not matter; the caller supplies separator variants."""
    return {"term": {"name.raw": {"value": value, "case_insensitive": True}}}


def _raw_name_prefix(value: str) -> Dict[str, Any]:
    return {"prefix": {"name.raw": {"value": value, "case_insensitive": True}}}


def _content_tokens(text: str) -> List[str]:
    """Words of a label or query, in order, with "to" kept as the direction marker."""
    tokens: List[str] = []
    for token in re.split(r"[^a-z0-9]+", text.lower()):
        if token == "to":
            tokens.append(token)
            continue
        if len(token) < 2 or token in _STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _split_direction(text: str) -> Optional[tuple]:
    """Parse one "A to B" phrase into source and target word sequences."""
    tokens = _content_tokens(text)
    if tokens.count("to") != 1:
        return None
    split_at = tokens.index("to")
    source = tuple(tokens[:split_at])
    target = tuple(tokens[split_at + 1 :])
    if not source or not target:
        return None
    return source, target


def _ordered_covers(needle: Sequence[str], haystack: Sequence[str]) -> bool:
    if not needle:
        return False
    index = 0
    for token in haystack:
        if index < len(needle) and token == needle[index]:
            index += 1
    return index == len(needle)


def matching_task_labels(
    tokens: Sequence[str],
    task_labels: Optional[Sequence[str]],
) -> List[tuple]:
    """Stored labels whose words contain the query words in the same order.

    An equal word sequence is an exact task. A longer label is a partial task,
    and only when the query has at least two words.
    """
    needle = [token for token in tokens if token != "to"]
    if not needle or not task_labels:
        return []
    matches: List[tuple] = []
    seen = set()
    for label in task_labels:
        parts = [token for token in _content_tokens(label) if token != "to"]
        if label in seen or not _ordered_covers(needle, parts):
            continue
        if parts != needle and len(needle) < 2:
            continue
        seen.add(label)
        matches.append((label, 80.0 if parts == needle else 40.0))
    return matches


def matching_directions(
    source: Sequence[str],
    target: Sequence[str],
    task_labels: Optional[Sequence[str]],
) -> List[tuple]:
    """Labels that run from the same source to the same target.

    `text to image` matches `text-to-image` and not `image-to-text`. A longer
    label such as `text-to-image generation` is a partial match. Labels that
    do not contain "to" are left to the ordered word match.
    """
    if not task_labels:
        return []
    source_t = tuple(source)
    target_t = tuple(target)
    matches: List[tuple] = []
    seen = set()
    for label in task_labels:
        if label in seen:
            continue
        parsed = _split_direction(label)
        if not parsed:
            continue
        label_source, label_target = parsed
        if label_source == source_t and label_target == target_t:
            boost = 80.0
        elif (
            label_source == source_t
            and len(label_target) > len(target_t)
            and label_target[: len(target_t)] == target_t
        ):
            boost = 40.0
        else:
            continue
        seen.add(label)
        matches.append((label, boost))
    return matches


def build_improved_keyword_query(
    query: str,
    task_labels: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Build a bool query. Exact name outranks an exact task, which outranks other exact fields.

    An "A to B" query matches stored labels with that source and target in order.
    Other task matches keep the query words in order. Free-text BM25 on name,
    description, and abstract only breaks ties.

    A name matches exactly when it equals the query once case is ignored and
    spaces or underscores are written as hyphens. `Mistral 7B` matches
    `Mistral-7B` and `mistral-7b`.
    """
    text = (query or "").strip()
    if not text:
        return None

    lowered = text.lower()
    slug = _normalize_slug(text)
    tokens = _meaningful_tokens(text)
    lexical = " ".join(tokens)
    should: List[Dict[str, Any]] = []

    for value in dict.fromkeys([text, lowered, slug]):
        if value:
            should.append(_constant_filter(_raw_name_term(value), 200))

    if 3 <= len(slug) <= 80 and len(tokens) <= 4:
        should.append(_constant_filter(_raw_name_prefix(slug), 25))

    should.append(_constant_filter({"match_phrase": {"name": lowered}}, 40))
    if tokens:
        should.append(
            _constant_filter(
                {"match": {"name": {"query": lexical, "operator": "and"}}},
                30,
            )
        )

    task_boosts: Dict[str, float] = {}
    if slug:
        task_boosts[slug] = 80.0
    direction = _split_direction(text)
    if direction:
        source, target = direction
        label_matches = matching_directions(source, target, task_labels)
    else:
        label_matches = matching_task_labels(tokens, task_labels)
    for label, boost in label_matches:
        task_boosts[label] = max(task_boosts.get(label, 0.0), boost)
    for task, boost in task_boosts.items():
        should.append(_constant_filter({"term": {"ml_tasks": task}}, boost))

    for field in _EXACT_KEYWORD_FIELDS:
        for value in dict.fromkeys([text, lowered, slug]):
            if value:
                should.append(_constant_filter({"term": {field: value}}, 60))

    if lexical:
        best: Dict[str, Any] = {
            "query": lexical,
            "fields": ["name^3", "description^1.5", "abstract"],
            "type": "best_fields",
        }
        if len(tokens) >= 4:
            best["minimum_should_match"] = "75%"
        elif len(tokens) >= 2:
            best["operator"] = "and"
        should.append({"multi_match": best})

    # log1p(downloads) is at most ~20, so it reorders hits inside a tier.
    # An exact name match stays at 200.
    return {
        "function_score": {
            "query": {"bool": {"should": should, "minimum_should_match": 1}},
            "functions": [
                {
                    "field_value_factor": {
                        "field": "downloads",
                        "modifier": "log1p",
                        "missing": 0,
                    }
                }
            ],
            "boost_mode": "sum",
            "score_mode": "sum",
        }
    }
