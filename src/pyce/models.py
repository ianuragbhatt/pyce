"""Data models for pyce."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class ChunkType(str, Enum):
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    MODULE = "MODULE"
    DOC = "DOC"
    COMMENT = "COMMENT"
    DECISION = "DECISION"


class NodeType(str, Enum):
    FILE = "FILE"
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    MODULE = "MODULE"


class EdgeType(str, Enum):
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    DEFINES = "DEFINES"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @classmethod
    def from_score(cls, score: float) -> ConfidenceLevel:
        if score >= 0.7:
            return cls.HIGH
        elif score >= 0.4:
            return cls.MEDIUM
        return cls.LOW


@dataclass
class Chunk:
    id: str
    content: str
    chunk_type: ChunkType
    file_path: str
    start_line: int
    end_line: int
    language: str = "python"
    embedding: list[float] | None = None
    confidence_score: float = 0.0
    compressed_content: str | None = None

    @property
    def token_count(self) -> int:
        text = self.compressed_content or self.content
        return max(1, len(text) // 4)

    @staticmethod
    def make_id(file_path: str, start_line: int, end_line: int, content: str) -> str:
        raw = f"{file_path}:{start_line}:{end_line}:{content[:100]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class GraphNode:
    id: str
    node_type: NodeType
    name: str
    file_path: str
    properties: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    properties: dict = field(default_factory=dict)


@dataclass
class RetrievalResult:
    chunks: list[Chunk] = field(default_factory=list)
    graph_nodes: list[GraphNode] = field(default_factory=list)
    graph_edges: list[GraphEdge] = field(default_factory=list)
    query: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    overflow_ids: list[str] = field(default_factory=list)
