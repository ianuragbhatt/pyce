from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pyce.config import RetrievalConfig
from pyce.models import Chunk, ChunkType
from pyce.retrieval.retriever import HybridRetriever


class _Embedder:
    def embed_query_list(self, query: str) -> list[float]:
        return [0.0] * 384


@dataclass
class _Backend:
    chunks: dict[str, Chunk]

    async def vector_search(self, query_embedding: list[float], top_k: int = 10):
        # Return stable ordering with made-up distances
        ids = list(self.chunks.keys())[:top_k]
        return [(cid, float(i + 1)) for i, cid in enumerate(ids)]

    async def fts_search(self, query: str, top_k: int = 10):
        ids = list(self.chunks.keys())[:top_k]
        return [(cid, 1.0 / (i + 1)) for i, cid in enumerate(ids)]

    async def get_chunk_by_id(self, chunk_id: str) -> Chunk | None:
        return self.chunks.get(chunk_id)

    async def get_chunks_by_file(self, file_path: str) -> list[Chunk]:
        return [c for c in self.chunks.values() if c.file_path == file_path]

    async def get_related_file_paths(self, file_paths: list[str]) -> list[str]:
        return []


def test_retriever_enforces_max_tokens_budget() -> None:
    # Make 3 large chunks so the retriever must trim.
    big = "x" * 2000  # token_count ~= 500
    chunks = {
        "c1": Chunk(id="c1", content=big, chunk_type=ChunkType.MODULE, file_path="a.py", start_line=1, end_line=10),
        "c2": Chunk(id="c2", content=big, chunk_type=ChunkType.MODULE, file_path="b.py", start_line=1, end_line=10),
        "c3": Chunk(id="c3", content=big, chunk_type=ChunkType.MODULE, file_path="c.py", start_line=1, end_line=10),
    }

    backend = _Backend(chunks=chunks)
    config = RetrievalConfig(top_k=3, max_tokens=600, graph_expansion=False)
    retriever = HybridRetriever(backend=backend, config=config, embedder=_Embedder())

    result = asyncio.run(retriever.retrieve("show me code", top_k=3, max_tokens=600))
    assert sum(c.token_count for c in result.chunks) <= 600
    assert result.overflow_ids, "Expected some chunks to be trimmed into overflow_ids"

