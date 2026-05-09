"""Confidence scoring for retrieval results."""

from __future__ import annotations

import math
import time

from pyce.models import Chunk


class ConfidenceScorer:
    def __init__(self, vector_weight: float = 0.5, keyword_weight: float = 0.4, recency_weight: float = 0.1):
        self._vector_weight = vector_weight
        self._keyword_weight = keyword_weight
        self._recency_weight = recency_weight

    def score(
        self,
        chunk: Chunk,
        vector_distance: float,
        query_keywords: list[str],
        file_hints: list[str],
    ) -> float:
        vector_score = max(0.0, 1.0 - vector_distance)
        keyword_score = self._keyword_score(chunk, query_keywords, file_hints)
        recency_score = 1.0

        return (
            self._vector_weight * vector_score
            + self._keyword_weight * keyword_score
            + self._recency_weight * recency_score
        )

    def _keyword_score(self, chunk: Chunk, keywords: list[str], file_hints: list[str]) -> float:
        if not keywords:
            return 0.0

        score = 0.0

        for hint in file_hints:
            if hint in chunk.file_path:
                score += 0.5
                break

        content_lower = chunk.content.lower()
        matched = sum(1 for kw in keywords if kw.lower() in content_lower)
        score += matched / len(keywords) * 0.5

        return min(1.0, score)
