"""Hybrid retrieval with RRF fusion and graph expansion."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from pyce.config import RetrievalConfig
from pyce.models import Chunk, RetrievalResult
from pyce.retrieval.confidence import ConfidenceScorer
from pyce.retrieval.query_parser import ParsedQuery, QueryIntent, parse_query
from pyce.storage.backend import LocalBackend


class HybridRetriever:
    def __init__(self, backend: LocalBackend, config: RetrievalConfig, embedder):
        self._backend = backend
        self._config = config
        self._embedder = embedder
        self._scorer = ConfidenceScorer()

    async def retrieve(self, query: str, top_k: int | None = None, max_tokens: int | None = None) -> RetrievalResult:
        top_k = top_k or self._config.top_k
        max_tokens = max_tokens or self._config.max_tokens

        parsed = parse_query(query)
        query_embedding = self._embedder.embed_query_list(query)

        vector_results, fts_results = await asyncio.gather(
            self._backend.vector_search(query_embedding, top_k * 3),
            self._backend.fts_search(query, top_k * 3),
        )

        rrf_scores = self._rrf_merge(vector_results, fts_results, parsed.intent)

        scored_chunks: list[tuple[Chunk, float]] = []
        for chunk_id, rrf_score in rrf_scores.items():
            chunk = await self._backend.get_chunk_by_id(chunk_id)
            if chunk is None:
                continue

            vec_dist = 0.0
            for cid, dist in vector_results:
                if cid == chunk_id:
                    vec_dist = dist
                    break

            confidence = self._scorer.score(chunk, vec_dist, parsed.keywords, parsed.file_hints)

            if "test" in chunk.file_path.lower() or "doc" in chunk.file_path.lower():
                confidence *= 0.8

            final_score = 0.5 * confidence + 0.5 * min(1.0, rrf_score * 60)
            scored_chunks.append((chunk, final_score))

        scored_chunks.sort(key=lambda x: x[1], reverse=True)

        file_counts: dict[str, int] = {}
        final_chunks: list[Chunk] = []
        for chunk, score in scored_chunks:
            count = file_counts.get(chunk.file_path, 0)
            if count >= self._config.max_chunks_per_file:
                continue
            chunk.confidence_score = score
            final_chunks.append(chunk)
            file_counts[chunk.file_path] = count + 1
            if len(final_chunks) >= top_k:
                break

        if self._config.graph_expansion and final_chunks:
            final_chunks = await self._expand_graph(final_chunks, parsed, top_k)

        total_tokens = sum(c.token_count for c in final_chunks)
        overflow_ids: list[str] = []
        if total_tokens > max_tokens:
            kept: list[Chunk] = []
            running = 0
            for chunk in final_chunks:
                if running + chunk.token_count <= max_tokens:
                    kept.append(chunk)
                    running += chunk.token_count
                else:
                    overflow_ids.append(chunk.id)
            final_chunks = kept

        return RetrievalResult(
            chunks=final_chunks,
            query=query,
            scores={c.id: c.confidence_score for c in final_chunks},
            overflow_ids=overflow_ids,
        )

    def _rrf_merge(
        self,
        vector_results: list[tuple[str, float]],
        fts_results: list[tuple[str, float]],
        intent: QueryIntent,
    ) -> dict[str, float]:
        k = 60
        scores: dict[str, float] = defaultdict(float)

        for rank, (chunk_id, _) in enumerate(vector_results):
            scores[chunk_id] += 1.0 / (k + rank + 1)

        fts_boost = 1.5 if intent == QueryIntent.CODE_LOOKUP else 1.0
        for rank, (chunk_id, _) in enumerate(fts_results):
            scores[chunk_id] += fts_boost / (k + rank + 1)

        return dict(scores)

    async def _expand_graph(self, chunks: list[Chunk], parsed: ParsedQuery, top_k: int) -> list[Chunk]:
        top_files = list({c.file_path for c in chunks[:3]})
        related_files = await self._backend.get_related_file_paths(top_files)

        bonus_chunks: list[Chunk] = []
        for rel_file in related_files[:2]:
            file_chunks = await self._backend.get_chunks_by_file(rel_file)
            if file_chunks:
                query_embedding = self._embedder.embed_query_list(parsed.raw_query)
                scored = []
                for c in file_chunks:
                    if c.embedding:
                        dist = _cosine_distance(query_embedding, c.embedding)
                        scored.append((c, dist))
                scored.sort(key=lambda x: x[1])
                for c, _ in scored[:2]:
                    c.confidence_score *= 0.85
                    bonus_chunks.append(c)

        existing_ids = {c.id for c in chunks}
        for bc in bonus_chunks:
            if bc.id not in existing_ids:
                chunks.append(bc)
                existing_ids.add(bc.id)

        return chunks


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - (dot / (norm_a * norm_b))
