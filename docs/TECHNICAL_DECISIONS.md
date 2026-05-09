# Technical Decisions

## 1. SQLite over LanceDB/ChromaDB

| Criterion | SQLite + sqlite-vec | LanceDB | ChromaDB |
|-----------|-------------------|---------|----------|
| Dependencies | 0 (stdlib + extension) | Rust binary | Python + Docker |
| Single file | Yes | Yes | No |
| Maturity | 20+ years | 2 years | 3 years |
| Concurrent reads | WAL mode | Limited | HTTP server |
| Vector search | sqlite-vec extension | Native | Native |
| FTS | Built-in FTS5 | No | No |
| Graph tables | Yes (relational) | No | No |

**Decision**: SQLite. Single file, zero external deps, WAL mode for concurrent access, FTS5 + sqlite-vec + relational tables all in one DB. The embedding dimension is the only constraint (sqlite-vec handles up to 16K dims).

---

## 2. fastembed over sentence-transformers

| Criterion | fastembed | sentence-transformers |
|-----------|-----------|----------------------|
| Runtime | ONNX Runtime (CPU) | PyTorch |
| Install size | ~50MB | ~2GB |
| Startup time | <1s | 3-5s |
| Model size | 33MB (bge-small) | 130MB (all-MiniLM) |
| GPU support | Optional ONNX GPU | Native CUDA |
| API | `FastEmbed()` | `SentenceTransformer()` |

**Decision**: fastembed. ONNX CPU-only is fast enough for code embedding. 40x smaller install. No PyTorch dependency. Model swap is just changing a string in config.

---

## 3. tree-sitter over regex/ast module

| Criterion | tree-sitter | regex | ast module |
|-----------|------------|-------|------------|
| AST-aware | Yes | No | Yes |
| Error-tolerant | Yes (partial parse) | N/A | No (SyntaxError) |
| Speed | ~10ms/file | ~1ms/file | ~5ms/file |
| Multi-language | Easy (grammar swap) | Manual patterns | Python-only |
| Granularity | Fine (any node type) | Line-level | Module-level |
| Incremental | Yes (partial reparse) | No | No |

**Decision**: tree-sitter. Error-tolerant parsing is critical for real codebases with incomplete files. Fine-grained node selection enables function-level chunking. Grammar swap enables future multi-language support.

---

## 4. Click over argparse/typer

| Criterion | Click | argparse | Typer |
|-----------|-------|----------|-------|
| Dependencies | None | stdlib | Click + type hints |
| API style | Decorators | Verbose | Type-annotated |
| Subcommands | Native | Manual | Native |
| Help generation | Auto | Manual | Auto |
| Testing | Built-in runner | Manual | Via Click |
| Battle-tested | Flask, pip, black | stdlib | FastAPI, new |

**Decision**: Click. Clean decorator API, no extra dependencies beyond itself, proven in production CLI tools. Typer adds a layer over Click without meaningful benefit for this project.

---

## 5. RRF over Weighted Average

Reciprocal Rank Fusion:

```
RRF_score(d) = Σ 1 / (k + rank_i(d))   where k=60
```

| Criterion | RRF | Weighted Average |
|-----------|-----|-----------------|
| Weight tuning | None (k=60 is universal) | Requires per-project tuning |
| Score normalization | Not needed (rank-based) | Required (different scales) |
| Provenance | Microsoft Research, TREC | Ad-hoc |
| Code search benchmarks | Top performer | Varies |

**Decision**: RRF. No weight tuning needed. Rank-based fusion is immune to score scale differences between vector distance and BM25. Well-proven in information retrieval literature.

---

## 6. stdio Transport

| Criterion | stdio | SSE/Streamable HTTP |
|-----------|-------|-------------------|
| Setup | None (stdin/stdout) | Port + URL config |
| Port conflicts | None | Possible |
| Firewall | N/A | May block |
| Editor support | Universal (Claude, Copilot, Opencode) | Partial |
| Multi-client | Single | Multi |

**Decision**: stdio. Simplest transport for local tools. Every MCP-capable editor supports it. No port configuration, no firewall issues, no URL management.

---

## 7. Content-Hash Embedding Cache

Cache key = SHA-256 of chunk content, not file path.

| Criterion | Content hash | File path + offset |
|-----------|-------------|-------------------|
| Survives renames | Yes | No |
| Cross-file dedup | Yes (identical content) | No |
| Cache invalidation | On content change | On any file change |
| Storage efficiency | Deduped | Duplicated |

**Decision**: Content hash. Renames are common in refactoring. Identical code (e.g., boilerplate) gets one embedding. Cache invalidation is precise — only changed content re-embeds.

---

## 8. PageRank for Repo Map

PageRank on the import graph to rank symbols by importance.

| Criterion | PageRank | Import count | Manual tagging |
|-----------|----------|-------------|---------------|
| Transitive importance | Yes (imported by importers) | No | No |
| Automatic | Yes | Yes | No |
| Tunable | Damping factor | None | N/A |

**Decision**: PageRank. A module imported by many important modules is itself important. Transitive importance captures the true dependency structure. No manual annotation required.

---

## 9. 3-Factor Confidence Scoring

```
confidence = 0.5 * vector_sim + 0.4 * keyword_rel + 0.1 * recency
```

| Factor | Weight | Rationale |
|--------|--------|-----------|
| Vector similarity | 50% | Semantic relevance is primary signal |
| Keyword relevance | 40% | Exact matches matter for code (function names, APIs) |
| Recency | 10% | Recently modified files are more likely relevant |

**Decision**: 3-factor with these weights. Vector captures semantics, keywords capture exact identifiers, recency captures active development context. Weights are defaults; configurable via `pyce.yaml`.

---

## 10. Configurable Embedding Model

Different projects have different tradeoffs:

| Use Case | Recommended Model | Dim | Size |
|----------|------------------|-----|------|
| Small codebase, fast | `BAAI/bge-small-en-v1.5` | 384 | 33MB |
| General purpose | `BAAI/bge-base-en-v1.5` | 768 | 130MB |
| High accuracy | `BAAI/bge-large-en-v1.5` | 1024 | 330MB |
| Multilingual | `intfloat/multilingual-e5-small` | 384 | 118MB |

**Decision**: Configurable via `pyce.yaml`. Default is `bge-small-en-v1.5` for fast setup. Users can swap models without code changes. Embedding dimension stored in DB schema for validation.
