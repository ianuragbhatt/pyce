"""MCP server exposing pyce tools and resources."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
    Resource,
)

from pyce.config import Config, load_config
from pyce.indexer.pipeline import run_indexing, _project_hash
from pyce.indexer.embedder import EmbeddingCache, Embedder
from pyce.retrieval.retriever import HybridRetriever
from pyce.retrieval.repo_map import generate_repo_map
from pyce.storage.backend import LocalBackend
from pyce.compression.compressor import Compressor
from pyce.integration.session_capture import SessionCapture


class ContextEngineMCP:
    def __init__(self, project_root: Path):
        self._project_root = project_root
        self._config = load_config(project_root)
        self._storage_dir = Path(self._config.storage_path) / _project_hash(project_root)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        db_path = str(self._storage_dir / "index.db")
        self._backend = LocalBackend(db_path)

        cache = EmbeddingCache(db_path)
        self._embedder = Embedder(model_name=self._config.embedding.model, cache=cache)
        self._retriever = HybridRetriever(self._backend, self._config.retrieval, self._embedder)
        self._compressor = Compressor(self._config.compression)

        sessions_dir = self._storage_dir / "sessions"
        self._session = SessionCapture(sessions_dir)

        self._server = Server("pyce")
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        @self._server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="context_search",
                    description="Search the indexed codebase using hybrid vector + BM25 search with graph expansion.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Natural language search query"},
                            "top_k": {"type": "integer", "description": "Max results (default: 10)"},
                            "max_tokens": {"type": "integer", "description": "Token budget (default: 8000)"},
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="expand_chunk",
                    description="Get the full source code for a compressed chunk by its ID.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "chunk_id": {"type": "string", "description": "ID of the chunk to expand"},
                        },
                        "required": ["chunk_id"],
                    },
                ),
                Tool(
                    name="related_context",
                    description="Find related code by walking the code graph (calls, imports).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "chunk_id": {"type": "string", "description": "Starting chunk ID"},
                        },
                        "required": ["chunk_id"],
                    },
                ),
                Tool(
                    name="repo_map",
                    description="Get a ranked overview of the project's most important symbols.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "max_tokens": {"type": "integer", "description": "Token budget (default: 2000)"},
                        },
                    },
                ),
                Tool(
                    name="index_status",
                    description="Check the current index status and health.",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="reindex",
                    description="Trigger re-indexing of the project.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "full": {"type": "boolean", "description": "Full reindex (default: false)"},
                        },
                    },
                ),
            ]

        @self._server.list_resources()
        async def list_resources() -> list[Resource]:
            return [
                Resource(
                    uri="pyce://project/overview",
                    name="Project Overview",
                    description="Project structure, frameworks, and index stats",
                    mimeType="application/json",
                ),
                Resource(
                    uri="pyce://index/status",
                    name="Index Status",
                    description="Live index health and statistics",
                    mimeType="application/json",
                ),
            ]

        @self._server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            if name == "context_search":
                return await self._handle_search(arguments)
            elif name == "expand_chunk":
                return await self._handle_expand(arguments)
            elif name == "related_context":
                return await self._handle_related(arguments)
            elif name == "repo_map":
                return await self._handle_repo_map(arguments)
            elif name == "index_status":
                return await self._handle_status(arguments)
            elif name == "reindex":
                return await self._handle_reindex(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        @self._server.read_resource()
        async def read_resource(uri: str) -> str:
            if uri == "pyce://project/overview":
                return await self._resource_overview()
            elif uri == "pyce://index/status":
                return await self._resource_status()
            else:
                return json.dumps({"error": f"Unknown resource: {uri}"})

    async def _handle_search(self, args: dict) -> list[TextContent]:
        query = args["query"]
        top_k = args.get("top_k", self._config.retrieval.top_k)
        max_tokens = args.get("max_tokens", self._config.retrieval.max_tokens)

        count = await self._backend.count()
        if count == 0:
            await run_indexing(self._project_root, self._config, self._backend)

        result = await self._retriever.retrieve(query, top_k=top_k, max_tokens=max_tokens)

        if not result.chunks:
            return [TextContent(type="text", text="No relevant code found for your query.")]

        output_parts: list[str] = []
        for i, chunk in enumerate(result.chunks, 1):
            score = result.scores.get(chunk.id, 0)
            confidence = "HIGH" if score >= 0.7 else "MEDIUM" if score >= 0.4 else "LOW"
            header = f"--- Result {i} [{confidence}] ({chunk.file_path}:{chunk.start_line}-{chunk.end_line}) ---"
            output_parts.append(f"{header}\n{chunk.compressed_content or chunk.content}")

        if result.overflow_ids:
            output_parts.append(f"\n--- {len(result.overflow_ids)} more results available. Use expand_chunk to see them. ---")

        return [TextContent(type="text", text="\n\n".join(output_parts))]

    async def _handle_expand(self, args: dict) -> list[TextContent]:
        chunk_id = args["chunk_id"]
        chunk = await self._backend.get_chunk_by_id(chunk_id)
        if chunk is None:
            return [TextContent(type="text", text=f"Chunk not found: {chunk_id}")]
        return [TextContent(type="text", text=f"--- {chunk.file_path}:{chunk.start_line}-{chunk.end_line} ---\n{chunk.content}")]

    async def _handle_related(self, args: dict) -> list[TextContent]:
        chunk_id = args["chunk_id"]
        chunk = await self._backend.get_chunk_by_id(chunk_id)
        if chunk is None:
            return [TextContent(type="text", text=f"Chunk not found: {chunk_id}")]

        related_files = await self._backend.get_related_file_paths([chunk.file_path])
        if not related_files:
            return [TextContent(type="text", text=f"No related code found for {chunk.file_path}")]

        parts: list[str] = [f"Related to {chunk.file_path}:"]
        for rf in related_files[:5]:
            parts.append(f"\n--- {rf} ---")
            rf_chunks = await self._backend.get_chunks_by_file(rf)
            for rc in rf_chunks[:3]:
                parts.append(rc.content[:500])

        return [TextContent(type="text", text="\n".join(parts))]

    async def _handle_repo_map(self, args: dict) -> list[TextContent]:
        max_tokens = args.get("max_tokens", 2000)
        count = await self._backend.count()
        if count == 0:
            await run_indexing(self._project_root, self._config, self._backend)
        repo_map = await generate_repo_map(self._backend, max_tokens)
        return [TextContent(type="text", text=repo_map)]

    async def _handle_status(self, args: dict) -> list[TextContent]:
        count = await self._backend.count()
        file_count = await self._backend.file_count()
        status = {
            "project_root": str(self._project_root),
            "chunks": count,
            "files_indexed": file_count,
            "embedding_model": self._config.embedding.model,
            "storage_path": str(self._storage_dir),
        }
        return [TextContent(type="text", text=json.dumps(status, indent=2))]

    async def _handle_reindex(self, args: dict) -> list[TextContent]:
        full = args.get("full", False)
        stats = await run_indexing(self._project_root, self._config, self._backend, full=full)
        return [TextContent(type="text", text=f"Reindex complete: {json.dumps(stats, indent=2)}")]

    async def _resource_overview(self) -> str:
        count = await self._backend.count()
        file_count = await self._backend.file_count()
        return json.dumps({
            "project_root": str(self._project_root),
            "chunks": count,
            "files": file_count,
            "embedding_model": self._config.embedding.model,
        }, indent=2)

    async def _resource_status(self) -> str:
        count = await self._backend.count()
        return json.dumps({"chunks": count, "healthy": True}, indent=2)

    async def run(self) -> None:
        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(read_stream, write_stream, self._server.create_initialization_options())
