# Architecture

## System Overview

```
┌─────────────┐     ┌──────────────────────────┐     ┌─────────────────┐
│  CLI (click) │────▶│  Indexer Pipeline        │────▶│  MCP Server     │
│  init/index  │     │  Walk→Hash→Skip/Parse    │     │  (stdio/mcp)    │
│  search/status│     │  →Chunk→Embed→Store      │     │  6 tools/3 res  │
└─────────────┘     └──────────────────────────┘     └────────┬────────┘
                                                               │
                                                    ┌──────────▼──────────┐
                                                    │  Storage Layer      │
                                                    │  SQLite + WAL       │
                                                    │  ┌───────────────┐  │
                                                    │  │ vec (sqlite-vec)│  │
                                                    │  │ FTS (FTS5)     │  │
                                                    │  │ graph tables   │  │
                                                    │  └───────────────┘  │
                                                    └──────────┬──────────┘
                                                               │
                                                    ┌──────────▼──────────┐
                                                    │  Retrieval Pipeline │
                                                    │  Query→Intent→     │
                                                    │  Embed→Vector+FTS  │
                                                    │  →RRF→Score→       │
                                                    │  Graph→Return      │
                                                    └─────────────────────┘
```

## Project Structure

```
src/pyce/
├── __init__.py
├── cli.py              # Click CLI: init, index, search, status, serve
├── config.py           # Project config (pyce.yaml) loading
├── models.py           # Dataclasses: Chunk, SearchResult, RepoMap
├── indexer/
│   ├── walker.py       # File discovery + .gitignore filtering
│   ├── hasher.py       # SHA-256 content hashing + change detection
│   ├── parser.py       # tree-sitter Python AST chunking
│   ├── embedder.py     # fastembed wrapper + content-hash cache
│   ├── graph.py        # Import graph + PageRank
│   ├── secrets.py      # Regex-based secret redaction
│   └── pipeline.py     # Orchestrates: walk→hash→skip/parse→chunk→embed→store
├── storage/
│   ├── sqlite.py       # SQLite connection (WAL, RLock, sqlite-vec/FTS5)
│   ├── schema.py       # Table DDL: chunks, embeddings, graph, files
│   └── vector.py       # Vector search + FTS search + RRF merge
├── retrieval/
│   ├── query.py        # Query intent classification
│   ├── search.py       # Hybrid search orchestrator
│   ├── scoring.py      # 3-factor confidence: vector 50%, keyword 40%, recency 10%
│   ├── diversity.py    # Max 3 chunks per file
│   ├── expansion.py    # 1-hop graph expansion
│   └── packing.py      # Token budget packing
├── compression/
│   ├── truncation.py   # Always-on: smart truncation to budget
│   └── llm.py          # Optional: Ollama/OpenAI summarization
└── integration/
    ├── mcp_server.py   # MCP tool/resource handlers
    ├── claude.py       # .mcp.json generator
    ├── copilot.py      # .vscode/mcp.json generator
    └── opencode.py     # opencode.json generator
```

## Data Flow — Indexing

```
Walk (glob + .gitignore)
  → Hash (SHA-256 per file)
    → Skip if unchanged (compare with files table)
      → Parse (tree-sitter Python → AST nodes)
        → Chunk (by function/class/module boundaries)
          → Embed (fastembed, cached by content hash)
            → Store (SQLite: chunks + embeddings + graph edges)
```

**Incremental logic**: `files` table stores `(path, sha256, mtime)`. On re-index, only changed files re-parse and re-embed. Deleted files cascade-delete their chunks.

## Data Flow — Retrieval

```
Query string
  → Intent classify (code/search/semantic/technical)
    → Embed query (same model as indexing)
      → Parallel:
          ├─ Vector search (sqlite-vec KNN, top 50)
          └─ FTS search (FTS5 MATCH, top 50)
        → RRF fusion (k=60, rank-based)
          → Score (3-factor confidence)
            → Diversity filter (max 3/file)
              → Graph expand (1-hop imports, optional)
                → Pack to token budget
                  → Return ranked results
```

## Thread Safety

| Mechanism | Scope | Purpose |
|-----------|-------|---------|
| `sqlite3` WAL mode | Database | Concurrent readers, single writer |
| `threading.RLock` | Connection pool | Serialize writes from indexer threads |
| `asyncio.to_thread` | MCP handlers | Bridge sync SQLite to async MCP runtime |

MCP server runs async. All SQLite calls are wrapped in `asyncio.to_thread()` to avoid blocking the event loop.

## Storage

Single SQLite database per project at `.pyce/index.db`.

**Tables:**

| Table | Columns | Purpose |
|-------|---------|---------|
| `files` | `path TEXT PK, sha256 TEXT, mtime REAL, indexed_at TEXT` | Change detection |
| `chunks` | `id TEXT PK, file TEXT, start_line INT, end_line INT, kind TEXT, name TEXT, content TEXT, tokens INT` | Code chunks |
| `embeddings` | `chunk_id TEXT PK, vector BLOB` | Vector embeddings (sqlite-vec) |
| `graph` | `source TEXT, target TEXT, edge_type TEXT` | Import/call relationships |
| `chunks_fts` | FTS5 virtual table on `chunks(name, content)` | Full-text search |

**Extensions loaded at startup:**
- `sqlite-vec` — vector similarity search (KNN)
- Built-in FTS5 — full-text keyword search
