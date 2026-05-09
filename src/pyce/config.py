"""Configuration loading and defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULT_IGNORE = [
    ".git/",
    "__pycache__/",
    "node_modules/",
    ".venv/",
    "venv/",
    "dist/",
    "build/",
    ".eggs/",
    "*.egg-info/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".tox/",
    ".nox/",
    "htmlcov/",
    ".coverage",
    "coverage.xml",
    "*.pyc",
    "*.pyo",
    ".env",
    ".env.*",
]

SECRET_PATTERNS = [
    r"\.env",
    r"\.pem$",
    r"credentials\.json",
    r"\.ssh/",
    r"\.gnupg/",
    r"id_rsa",
    r"id_ed25519",
]

SECRET_CONTENT_PATTERNS = [
    r"AKIA[0-9A-Z]{16}",
    r"gh[ps]_[A-Za-z0-9_]{36,}",
    r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+",
    r"sk_live_[0-9a-zA-Z]{24}",
    r"sk_test_[0-9a-zA-Z]{24}",
    r"-----BEGIN.*PRIVATE KEY-----",
    r"(?i)(api_key|api_secret|secret_key|access_token|auth_token)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
    r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{4,}['\"]",
]


@dataclass
class CompressionConfig:
    provider: str = "ollama"
    model: str = "phi3:mini"
    base_url: str = "http://localhost:11434"
    api_key: str = ""


@dataclass
class EmbeddingConfig:
    model: str = "BAAI/bge-small-en-v1.5"
    batch_size: int = 64


@dataclass
class IndexerConfig:
    ignore: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE))
    redact_secrets: bool = True
    max_file_size: int = 2 * 1024 * 1024
    include_extensions: list[str] = field(
        default_factory=lambda: [
            ".py",
            ".toml",
            ".yaml",
            ".yml",
            ".json",
            ".md",
            ".txt",
            "Dockerfile",
            "Makefile",
        ]
    )
    watch: bool = True
    debounce_ms: int = 500


@dataclass
class RetrievalConfig:
    confidence_threshold: float = 0.5
    top_k: int = 10
    max_tokens: int = 8000
    graph_expansion: bool = True
    max_chunks_per_file: int = 3


@dataclass
class Config:
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    indexer: IndexerConfig = field(default_factory=IndexerConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    storage_path: str = ""

    def __post_init__(self):
        if not self.storage_path:
            self.storage_path = str(Path.home() / ".pyce" / "projects")


def load_config(project_root: Path | None = None) -> Config:
    config = Config()

    global_path = Path.home() / ".pyce" / "config.yaml"
    _merge_yaml(config, global_path)

    if project_root:
        project_path = project_root / ".context-engine.yaml"
        _merge_yaml(config, project_path)

    return config


def _merge_yaml(config: Config, path: Path) -> None:
    if not path.exists():
        return
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if "compression" in data:
        for k, v in data["compression"].items():
            if hasattr(config.compression, k):
                setattr(config.compression, k, v)
    if "embedding" in data:
        for k, v in data["embedding"].items():
            if hasattr(config.embedding, k):
                setattr(config.embedding, k, v)
    if "indexer" in data:
        for k, v in data["indexer"].items():
            if hasattr(config.indexer, k):
                setattr(config.indexer, k, v)
    if "retrieval" in data:
        for k, v in data["retrieval"].items():
            if hasattr(config.retrieval, k):
                setattr(config.retrieval, k, v)
    if "storage_path" in data:
        config.storage_path = data["storage_path"]
