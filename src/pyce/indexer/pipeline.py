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

def _build_module_index(project_root: Path, files: list[Path]) -> dict[str, str]:
    """
    Build a best-effort mapping from module import path -> repo-relative file path.

    Examples:
    - src/pkg/foo.py -> "src.pkg.foo" (if project_root is repo root)
    - pkg/__init__.py -> "pkg"
    """
    index: dict[str, str] = {}
    for fp in files:
        if fp.suffix.lower() != ".py":
            continue
        rel = str(fp.relative_to(project_root)).replace("\\", "/")
        no_ext = rel[:-3]  # strip .py
        if no_ext.endswith("/__init__"):
            mod = no_ext[: -len("/__init__")].replace("/", ".")
        else:
            mod = no_ext.replace("/", ".")
        index[mod] = rel
    return index


def _resolve_import_to_file(import_path: str, module_index: dict[str, str]) -> str | None:
    """
    Resolve an import path like 'pkg.sub' to the closest matching module file.
    Falls back to parent modules (pkg.sub.x -> pkg.sub -> pkg).
    """
    cur = import_path
    while cur:
        if cur in module_index:
            return module_index[cur]
        if "." not in cur:
            break
        cur = cur.rsplit(".", 1)[0]
    return None


def _build_calls_edges(
    rel_path: str,
    chunks: list[Chunk],
    calls_by_fn: dict[str, set[str]],
) -> list[GraphEdge]:
    """
    Build CALLS edges between chunks within the same file (fast + reliable).
    """
    name_to_id: dict[str, str] = {}
    for c in chunks:
        if c.file_path != rel_path:
            continue
        if c.chunk_type.value in ("FUNCTION", "CLASS"):
            name_to_id[_chunk_name(c)] = c.id

    edges: list[GraphEdge] = []
    for caller_name, callees in calls_by_fn.items():
        caller_id = name_to_id.get(caller_name)
        if not caller_id:
            continue
        for callee in callees:
            callee_id = name_to_id.get(callee)
            if not callee_id or callee_id == caller_id:
                continue
            edges.append(
                GraphEdge(
                    source_id=caller_id,
                    target_id=callee_id,
                    edge_type=EdgeType.CALLS,
                )
            )
    return edges


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
        module_index = _build_module_index(project_root, files_to_index)

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
                ext = file_path.suffix.lower()
                basename = file_path.name

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

                if ext == ".py":
                    chunks, imports, calls_by_fn = await asyncio.to_thread(
                        chunker.chunk_with_relationships, source, rel_path
                    )
                else:
                    language = ext.lstrip(".") or basename.lower()
                    chunks = chunker.chunk_text(source, rel_path, language=language)
                    imports = []
                    calls_by_fn = {}

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
                    target_rel = _resolve_import_to_file(imp, module_index)
                    if not target_rel:
                        continue
                    all_edges.append(
                        GraphEdge(
                            source_id=file_node.id,
                            target_id=f"file:{target_rel}",
                            edge_type=EdgeType.IMPORTS,
                        )
                    )

                if calls_by_fn and chunks:
                    all_edges.extend(_build_calls_edges(rel_path, chunks, calls_by_fn))

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
    allowed_exts = {e.lower() for e in (config.indexer.include_extensions or [".py"])}

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
            fp = Path(root) / filename
            rel_fp = str(fp.relative_to(project_root)).replace("\\", "/")
            if _should_ignore(rel_fp, config.indexer.ignore):
                continue
            if is_secret_file(fp):
                continue
            ext = fp.suffix.lower()
            if (ext and ext in allowed_exts) or (not ext and filename.lower() in allowed_exts):
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
