# pyce — Python Code Context Engine

A local, Python-only MCP server that indexes your codebase and returns only relevant code snippets to your AI assistant — saving massive input tokens.

## The Problem

When you ask Claude Code, Copilot, or Opencode "how does `validate_token` work?", the AI reads the entire `auth.py` (500 lines) when it only needs lines 45-90. This wastes tokens, costs money, and eats your context window.

## How pyce Helps

```
Your Python codebase
    ↓ tree-sitter AST parsing
Semantic chunks (functions, classes, modules)
    ↓ fastembed (BAAI/bge-small-en-v1.5)
384-dim vectors + BM25 full-text index + code graph
    ↓ MCP server
Claude Code / Copilot / Opencode → hybrid search → only relevant chunks
```

Instead of reading 500 lines, the AI gets 50 lines of exactly what it needs.

## Quick Start

```bash
# Install
uv sync

# Initialize (creates index, configures MCP for your editors)
pyce init

# That's it. Your AI assistants now have pyce tools available.

# Re-index after code changes
pyce index

# Test search from terminal
pyce search "payment processing"

# Check index health
pyce status
```

## Supported Editors

| Editor | Config Written To | Integration |
|--------|-------------------|-------------|
| **Claude Code** | `.mcp.json` | MCP server (stdio) |
| **GitHub Copilot** | `.vscode/mcp.json` | MCP server (stdio) |
| **Opencode** | `opencode.json` | MCP server (stdio) |

`pyce init` auto-detects which editors you have and configures all of them.

## MCP Tools

Once running, your AI assistant gets access to these tools:

| Tool | What It Does |
|------|--------------|
| `context_search` | Hybrid vector + BM25 search with graph expansion |
| `expand_chunk` | Get full source for a compressed result |
| `related_context` | Walk code graph (calls, imports) |
| `repo_map` | PageRank-ranked overview of project symbols |
| `index_status` | Check index freshness |
| `reindex` | Trigger re-indexing |

## MCP Resources

Your AI assistant can also browse these resources:

| Resource | Content |
|----------|---------|
| `pyce://project/overview` | Project structure, frameworks, stats |
| `pyce://symbols/{file}` | Symbol table per file |
| `pyce://index/status` | Live index health |

## Configuration

Edit `.context-engine.yaml` in your project root:

```yaml
embedding:
  model: "BAAI/bge-small-en-v1.5"   # or bge-base, gte-qwen2, etc.

compression:
  provider: "ollama"                  # or "openai"
  model: "phi3:mini"
  base_url: "http://localhost:11434"
  # api_key: ""                       # only for openai provider

indexer:
  ignore:
    - "tests/"
    - "docs/"
  redact_secrets: true

retrieval:
  confidence_threshold: 0.5
  top_k: 10
  max_tokens: 8000
```

## Storage

All data lives in `~/.pyce/projects/<project-hash>/`:

- `index.db` — SQLite database (vector + FTS + graph + cache)
- `manifest.json` — SHA-256 file hashes for incremental indexing
- `sessions/` — Session history

## Requirements

- Python 3.11+
- `uv` package manager
- No external services required (Ollama optional for better compression)

## How It Works

### Indexing
1. Walk project files (skip `.git`, `__pycache__`, `.venv`, secrets)
2. SHA-256 hash each file → skip unchanged (96% cache hit rate)
3. Parse Python with tree-sitter → extract functions, classes, modules
4. Build code graph (FILE → DEFINES → chunk, file → IMPORTS → module)
5. Embed chunks with fastembed (ONNX, CPU-only)
6. Store in SQLite: vector index (sqlite-vec) + full-text (FTS5) + graph

### Retrieval
1. Classify query intent (CODE_LOOKUP, ARCHITECTURE, DECISION_RECALL)
2. Embed query → vector search (3× candidates)
3. BM25 keyword search (3× candidates)
4. Reciprocal Rank Fusion merge
5. Confidence scoring (vector 50% + keyword 40% + recency 10%)
6. File diversity (max 3 chunks/file), path penalty for tests/docs
7. Graph expansion (1-hop CALLS/IMPORTS → bonus chunks)
8. Compress if over token budget, return results + overflow references

## Project Structure

```
src/pyce/
├── cli.py                  # CLI entry point
├── config.py               # Config loading
├── models.py               # Data models
├── indexer/
│   ├── chunker.py          # Tree-sitter Python AST chunking
│   ├── embedder.py         # fastembed wrapper + cache
│   ├── pipeline.py         # Main indexing pipeline
│   ├── manifest.py         # SHA-256 change detection
│   ├── secrets.py          # Secret detection & redaction
│   └── watcher.py          # File system watcher
├── storage/
│   ├── vector_store.py     # sqlite-vec vector store
│   ├── fts_store.py        # SQLite FTS5 full-text search
│   ├── graph_store.py      # SQLite graph (nodes + edges)
│   └── backend.py          # Composite backend
├── retrieval/
│   ├── retriever.py        # Hybrid search + RRF + graph expansion
│   ├── confidence.py       # 3-factor scoring
│   ├── query_parser.py     # Intent classification
│   └── repo_map.py         # PageRank-based symbol ranking
├── compression/
│   ├── compressor.py       # LLM or truncation compression
│   └── quality.py          # Lossy compression detection
└── integration/
    ├── mcp_server.py       # MCP server (6 tools + 3 resources)
    ├── session_capture.py  # Session history + decisions
    └── editors.py          # Auto-configure editors
```

## License

MIT
