"""CLI entry point for pyce."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from pyce.config import Config, load_config
from pyce.indexer.pipeline import run_indexing, _project_hash
from pyce.indexer.embedder import EmbeddingCache, Embedder
from pyce.retrieval.retriever import HybridRetriever
from pyce.storage.backend import LocalBackend
from pyce.integration.editors import configure_editors


def _find_project_root() -> Path:
    cwd = Path.cwd()
    for marker in ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", ".git"]:
        if (cwd / marker).exists():
            return cwd
    return cwd


def _get_backend(config: Config, project_root: Path) -> tuple[LocalBackend, Path]:
    storage_dir = Path(config.storage_path) / _project_hash(project_root)
    storage_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(storage_dir / "index.db")
    return LocalBackend(db_path), storage_dir


@click.group()
def main():
    """pyce — Python Code Context Engine"""
    pass


@main.command()
def init():
    """Initialize pyce for this project."""
    project_root = _find_project_root()
    config = load_config(project_root)

    backend, storage_dir = _get_backend(config, project_root)

    click.echo(f"Project root: {project_root}")
    click.echo(f"Storage: {storage_dir}")

    click.echo("\nIndexing project...")
    stats = asyncio.run(run_indexing(project_root, config, backend, full=True))
    click.echo(f"  Files processed: {stats['files_processed']}")
    click.echo(f"  Chunks created: {stats['chunks_created']}")

    click.echo("\nConfiguring editors...")
    configured = configure_editors(project_root)
    for editor in configured:
        click.echo(f"  Configured: {editor}")

    click.echo("\nDone! Your AI assistants can now use pyce.")


@main.command()
@click.option("--full", is_flag=True, help="Full reindex (re-process everything)")
@click.option("--path", type=click.Path(exists=True), help="Index specific file or directory")
def index(full: bool, path: str | None):
    """Index or reindex the project."""
    project_root = _find_project_root()
    config = load_config(project_root)
    backend, _ = _get_backend(config, project_root)

    specific = Path(path) if path else None
    click.echo("Indexing...")
    stats = asyncio.run(run_indexing(project_root, config, backend, full=full, specific_path=specific))
    click.echo(f"  Files processed: {stats['files_processed']}")
    click.echo(f"  Chunks created: {stats['chunks_created']}")
    click.echo(f"  Files skipped: {stats['files_skipped']}")


@main.command()
@click.argument("query")
@click.option("--top-k", type=int, default=10, help="Max results")
@click.option("--max-tokens", type=int, default=8000, help="Token budget")
def search(query: str, top_k: int, max_tokens: int):
    """Search the indexed codebase."""
    project_root = _find_project_root()
    config = load_config(project_root)
    backend, storage_dir = _get_backend(config, project_root)

    cache = EmbeddingCache(str(storage_dir / "index.db"))
    embedder = Embedder(model_name=config.embedding.model, cache=cache)
    retriever = HybridRetriever(backend, config.retrieval, embedder)

    count = asyncio.run(backend.count())
    if count == 0:
        click.echo("No index found. Run 'pyce index' first.")
        return

    result = asyncio.run(retriever.retrieve(query, top_k=top_k, max_tokens=max_tokens))

    if not result.chunks:
        click.echo("No results found.")
        return

    for i, chunk in enumerate(result.chunks, 1):
        score = result.scores.get(chunk.id, 0)
        confidence = "HIGH" if score >= 0.7 else "MEDIUM" if score >= 0.4 else "LOW"
        click.echo(f"\n--- Result {i} [{confidence}] ({chunk.file_path}:{chunk.start_line}-{chunk.end_line}) ---")
        click.echo(chunk.content[:500])
        if len(chunk.content) > 500:
            click.echo("...")


@main.command()
def status():
    """Show index status."""
    project_root = _find_project_root()
    config = load_config(project_root)
    backend, storage_dir = _get_backend(config, project_root)

    count = asyncio.run(backend.count())
    file_count = asyncio.run(backend.file_count())

    click.echo(f"Project root: {project_root}")
    click.echo(f"Storage: {storage_dir}")
    click.echo(f"Chunks indexed: {count}")
    click.echo(f"Files indexed: {file_count}")
    click.echo(f"Embedding model: {config.embedding.model}")


@main.command()
def serve():
    """Start MCP server (stdio mode)."""
    from pyce.integration.mcp_server import ContextEngineMCP

    project_root = _find_project_root()
    engine = ContextEngineMCP(project_root)
    asyncio.run(engine.run())


if __name__ == "__main__":
    main()
