"""Composite storage backend orchestrating vector, FTS, and graph stores."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pyce.models import Chunk, EdgeType, GraphEdge, GraphNode
from pyce.storage.vector_store import VectorStore
from pyce.storage.fts_store import FTSStore
from pyce.storage.graph_store import GraphStore


class LocalBackend:
    def __init__(self, db_path: str, dim: int = 384):
        self._db_path = db_path
        self.vector = VectorStore(db_path, dim)
        self.fts = FTSStore(db_path)
        self.graph = GraphStore(db_path)

    async def ingest(self, chunks: list[Chunk], nodes: list[GraphNode], edges: list[GraphEdge]) -> None:
        await asyncio.gather(
            asyncio.to_thread(self.vector.ingest, chunks),
            asyncio.to_thread(self.fts.ingest, chunks),
            asyncio.to_thread(self.graph.ingest_nodes, nodes),
            asyncio.to_thread(self.graph.ingest_edges, edges),
        )

    async def delete_by_files(self, file_paths: list[str]) -> None:
        await asyncio.gather(
            asyncio.to_thread(self.vector.delete_by_files, file_paths),
            asyncio.to_thread(self.fts.delete_by_files, file_paths),
            asyncio.to_thread(self.graph.delete_by_files, file_paths),
        )

    async def vector_search(self, query_embedding: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        return await asyncio.to_thread(self.vector.search, query_embedding, top_k)

    async def fts_search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        return await asyncio.to_thread(self.fts.search, query, top_k)

    async def get_related_file_paths(self, file_paths: list[str]) -> list[str]:
        neighbors = await asyncio.to_thread(
            self.graph.neighbors_for_files, file_paths, [EdgeType.CALLS, EdgeType.IMPORTS]
        )
        return list({n[2] for n in neighbors if n[2]})

    async def get_chunk_by_id(self, chunk_id: str) -> Chunk | None:
        return await asyncio.to_thread(self.vector.get_chunk_by_id, chunk_id)

    async def get_chunks_by_file(self, file_path: str) -> list[Chunk]:
        return await asyncio.to_thread(self.vector.get_chunks_by_file, file_path)

    async def get_compression(self, chunk_id: str, level: str) -> str | None:
        return await asyncio.to_thread(self.vector.get_compression, chunk_id, level)

    async def put_compression(self, chunk_id: str, level: str, compressed: str) -> None:
        await asyncio.to_thread(self.vector.put_compression, chunk_id, level, compressed)

    async def count(self) -> int:
        return await asyncio.to_thread(self.vector.count)

    async def file_count(self) -> int:
        return await asyncio.to_thread(self.vector.file_count)

    async def get_all_chunk_hashes(self) -> set[str]:
        return await asyncio.to_thread(self.vector.get_all_chunk_hashes)

    async def get_all_nodes(self) -> list[GraphNode]:
        return await asyncio.to_thread(self.graph.get_all_nodes)

    async def get_all_edges(self) -> list[GraphEdge]:
        return await asyncio.to_thread(self.graph.get_all_edges)
