"""Query intent classification and keyword extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class QueryIntent(str, Enum):
    CODE_LOOKUP = "CODE_LOOKUP"
    DECISION_RECALL = "DECISION_RECALL"
    ARCHITECTURE = "ARCHITECTURE"
    GENERAL = "GENERAL"


_DECISION_PATTERNS = [
    r"what did we decide",
    r"why did we",
    r"decision",
    r"chose",
    r"rationale",
]
_ARCHITECTURE_PATTERNS = [
    r"how does .* work",
    r"architecture",
    r"structure",
    r"overview",
    r"explain the",
    r"what does .* do",
]
_CODE_PATTERNS = [
    r"\.py\b",
    r"\bfunction\b",
    r"\bclass\b",
    r"\bmethod\b",
    r"\bimport\b",
    r"\bdef\b",
    r"\basync\b",
]

_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "not",
    "only", "own", "same", "so", "than", "too", "very", "just", "because",
    "but", "and", "or", "if", "while", "about", "up", "it", "its", "this",
    "that", "these", "those", "what", "which", "who", "whom", "i", "me",
    "my", "we", "our", "you", "your", "he", "him", "his", "she", "her",
    "they", "them", "their", "find", "show", "get", "look", "search",
}


@dataclass
class ParsedQuery:
    intent: QueryIntent = QueryIntent.GENERAL
    keywords: list[str] = field(default_factory=list)
    file_hints: list[str] = field(default_factory=list)
    raw_query: str = ""


def parse_query(query: str) -> ParsedQuery:
    parsed = ParsedQuery(raw_query=query)

    query_lower = query.lower()

    for pattern in _DECISION_PATTERNS:
        if re.search(pattern, query_lower):
            parsed.intent = QueryIntent.DECISION_RECALL
            break

    if parsed.intent == QueryIntent.GENERAL:
        for pattern in _ARCHITECTURE_PATTERNS:
            if re.search(pattern, query_lower):
                parsed.intent = QueryIntent.ARCHITECTURE
                break

    if parsed.intent == QueryIntent.GENERAL:
        for pattern in _CODE_PATTERNS:
            if re.search(pattern, query_lower):
                parsed.intent = QueryIntent.CODE_LOOKUP
                break

    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query)
    parsed.keywords = [w for w in words if w.lower() not in _STOP_WORDS and len(w) > 1]

    file_patterns = re.findall(r"[\w/\\]+\.py\b", query)
    parsed.file_hints = file_patterns

    return parsed
