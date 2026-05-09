"""Main indexing pipeline."""

from __future__ import annotations

import asyncio
import fnmatch
import os
from pathlib import Path

from pyce.config import Config
from pyce.models import Chunk, EdgeType, GraphEdge, GraphNode, NodeType
from pyce.indexer.chunker import Chunker
from pyce.indexer.embedder import EmbeddingCache, Embedder
from pyce.indexer.manifest import Manifest
from pyce.indexer.secrets import is_secret_file, redact_secrets
from pyce.storage.backend import LocalBackend


_pipeline_lock = asyncio.Lock()


async def run_indexing(
    project_root: Path,
    config: Config,
    backend: LocalBackend,
    full: bool = False,
    specific_path: Path | None = None,
    progress_fn=None,
) -> dict:
    async with _pipeline_lock:
        storage_dir = Path(config.storage_path) / _project_hash(project_root)
        storage_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = storage_dir / "manifest.json"
        manifest = Manifest(manifest_path)

        if full:
            manifest = Manifest(manifest_path)
            manifest._data = {"schema_version": 1, "files": {}, "last_git_sha": ""}
            manifest.save()

        cache_path = str(storage_dir / "index.db")
        cache = EmbeddingCache(cache_path)
        embedder = Embedder(model_name=config.embedding.model, cache=cache)
        chunker = Chunker()

        files_to_index = _discover_files(project_root, config, specific_path)

        if full:
            old_files = set(manifest.get_files().keys())
            new_files = {str(f.relative_to(project_root)).replace("\\", "/") for f in files_to_index}
            deleted = old_files - new_files
            if deleted:
                await backend.delete_by_files(list(deleted))
                for fp in deleted:
                    manifest.remove_file(fp)

        stats = {"files_processed": 0, "chunks_created": 0, "files_skipped": 0, "files_deleted": 0}

        batch_size = 50
        for i in range(0, len(files_to_index), batch_size):
            batch = files_to_index[i:i + batch_size]
            all_chunks: list[Chunk] = []
            all_nodes: list[GraphNode] = []
            all_edges: list[GraphEdge] = []

            for file_path in batch:
                rel_path = str(file_path.relative_to(project_root)).replace("\\", "/")

                try:
                    content_bytes = file_path.read_bytes()
                except (OSError, UnicodeDecodeError):
                    stats["files_skipped"] += 1
                    continue

                if len(content_bytes) > config.indexer.max_file_size:
                    stats["files_skipped"] += 1
                    continue

                content_hash = Manifest.hash_content(content_bytes)
                if not manifest.has_changed(rel_path, content_hash):
                    stats["files_skipped"] += 1
                    continue

                try:
                    source = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    stats["files_skipped"] += 1
                    continue

                if config.indexer.redact_secrets:
                    source = redact_secrets(source)

                chunks, imports = await asyncio.to_thread(chunker.chunk_with_imports, source, rel_path)

                file_node = GraphNode(
                    id=f"file:{rel_path}",
                    node_type=NodeType.FILE,
                    name=rel_path,
                    file_path=rel_path,
                )
                all_nodes.append(file_node)

                for chunk in chunks:
                    chunk_node = GraphNode(
                        id=chunk.id,
                        node_type=NodeType(chunk.chunk_type.value),
                        name=_chunk_name(chunk),
                        file_path=rel_path,
                    )
                    all_nodes.append(chunk_node)
                    all_edges.append(GraphEdge(
                        source_id=file_node.id,
                        target_id=chunk.id,
                        edge_type=EdgeType.DEFINES,
                    ))

                for imp in imports:
                    all_edges.append(GraphEdge(
                        source_id=file_node.id,
                        target_id=f"module:{imp}",
                        edge_type=EdgeType.IMPORTS,
                    ))

                all_chunks.extend(chunks)
                manifest.update_file(rel_path, content_hash)
                stats["files_processed"] += 1
                stats["chunks_created"] += len(chunks)

                if progress_fn:
                    await progress_fn(rel_path, stats)

            if all_chunks:
                await asyncio.to_thread(embedder.embed, all_chunks, config.embedding.batch_size)
                await backend.ingest(all_chunks, all_nodes, all_edges)

        manifest.save()

        orphan_hashes = await backend.get_all_chunk_hashes()
        known_hashes = {c.id for c in []}
        if orphan_hashes:
            cache.prune_orphans(orphan_hashes)

        return stats


def _discover_files(project_root: Path, config: Config, specific_path: Path | None = None) -> list[Path]:
    search_root = specific_path or project_root
    files: list[Path] = []

    for root, dirs, filenames in os.walk(search_root):
        rel_root = Path(root).relative_to(project_root)
        rel_str = str(rel_root).replace("\\", "/")

        skip = False
        for pattern in config.indexer.ignore:
            if fnmatch.fnmatch(rel_str + "/", pattern) or fnmatch.fnmatch(rel_str, pattern.rstrip("/")):
                skip = True
                break
        if skip:
            dirs.clear()
            continue

        dirs[:] = [d for d in dirs if not _should_ignore(str(rel_root / d).replace("\\", "/"), config.indexer.ignore)]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            fp = Path(root) / filename
            rel_fp = str(fp.relative_to(project_root)).replace("\\", "/")
            if _should_ignore(rel_fp, config.indexer.ignore):
                continue
            if is_secret_file(fp):
                continue
            files.append(fp)

    return files


def _should_ignore(rel_path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        clean = pattern.rstrip("/")
        if fnmatch.fnmatch(rel_path, clean) or fnmatch.fnmatch(rel_path, clean + "/*"):
            return True
        if clean in rel_path:
            return True
    return False


def _chunk_name(chunk: Chunk) -> str:
    lines = chunk.content.split("\n")
    for line in lines[:3]:
        line = line.strip()
        if line.startswith("def ") or line.startswith("async def "):
            name = line.split("(")[0].replace("def ", "").replace("async ", "").strip()
            return name
        if line.startswith("class "):
            name = line.split("(")[0].split(":")[0].replace("class ", "").strip()
            return name
    return chunk.file_path


def _project_hash(project_root: Path) -> str:
    import hashlib
    return hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:12]
