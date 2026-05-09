# Reference Analysis: elara-labs/code-context-engine

## What We Keep

| Feature | Implementation | Notes |
|---------|---------------|-------|
| Hybrid search | Vector (sqlite-vec) + FTS (FTS5) | Same architecture, different backends |
| SQLite storage | Single DB file | Identical approach |
| Tree-sitter chunking | AST-aware, function/class boundaries | Python grammar only (vs 8 languages) |
| Content-hash cache | SHA-256 of chunk content as cache key | Survives renames |
| Incremental indexing | File hash comparison, skip unchanged | Same approach |
| Graph expansion | 1-hop import graph expansion | Same depth |
| Confidence scoring | Multi-factor scoring | Adjusted weights (50/40/10 vs 40/40/20) |
| Secret detection | Regex patterns before embedding | Same patterns |
| MCP server | stdio transport | Same transport |
| Git hooks | post-commit auto-reindex | Same trigger |
| Watchdog | Live re-indexing on file change | Same approach |

## What We Change

| Aspect | Reference (elara-labs) | PyCE |
|--------|----------------------|------|
| Languages supported | 8 (Python, JS, TS, Go, Rust, Java, C, C++) | Python only |
| Dashboard | Web dashboard (React) | None (CLI only) |
| LLM compression | Ollama only | Ollama + OpenAI fallback |
| Editor support | 6 editors | 3 (Claude Code, Copilot, Opencode) |
| MCP tools | 9 tools | 6 tools (focused set) |
| MCP resources | None | 3 resources |
| MCP prompts | None | Planned (v1.1) |
| Repo map | None | PageRank-based repo map |
| Git-blame hot detection | None | File hotness via git blame |
| Embedding model | Fixed (bge-small) | Configurable via config |

## What We Add

### MCP Resources

Read-only endpoints for project metadata:

- `pyce://project/overview` — project structure summary
- `pyce://symbols/{file}` — symbols in a specific file
- `pyce://index/status` — index health metrics

Resources complement tools by providing passive information without requiring a search query.

### PageRank Repo Map

`repo_map` tool generates a ranked symbol overview:

- PageRank on import graph determines symbol importance
- Compact format for LLM context: `file:line kind name`
- Replaces manual "important files" lists

### Git-blame Hot Detection

Uses `git blame` to identify recently-active files:

- Files with many recent commits get a recency boost
- Integrates into confidence scoring (10% recency factor)
- Helps prioritize actively-developed code

### OpenAI-compatible Compression

LLM compression supports both:

- **Ollama** (local, free, default)
- **OpenAI API** (remote, paid, fallback)

Falls back gracefully: Ollama → OpenAI → truncation.

## Dependencies Comparison

| Dependency | Reference | PyCE | Purpose |
|------------|-----------|------|---------|
| `tree-sitter` | ✅ | ✅ | AST parsing |
| `tree-sitter-python` | ✅ (8 grammars) | ✅ (1 grammar) | Python grammar |
| `sqlite-vec` | ✅ | ✅ | Vector search |
| `fastembed` | ✅ | ✅ | Embedding (ONNX) |
| `click` | ❌ (argparse) | ✅ | CLI framework |
| `mcp` | ✅ | ✅ | MCP server |
| `watchdog` | ✅ | ✅ | File watching |
| `httpx` | ❌ | ✅ | OpenAI API calls |
| `pyyaml` | ✅ | ✅ | Config file |
| `sentence-transformers` | ✅ | ❌ | Replaced by fastembed |
| `chromadb` | ✅ | ❌ | Replaced by sqlite-vec |
| `flask` | ✅ (dashboard) | ❌ | No dashboard |
| `react` | ✅ (dashboard) | ❌ | No dashboard |

**Net result**: PyCE has fewer dependencies (10 vs 18), smaller install footprint, and no external service requirements (no ChromaDB server, no React build).

## Summary

PyCE takes the proven architecture of code-context-engine (hybrid search, SQLite, tree-sitter, MCP) and simplifies it:

- **Scope**: Python-only vs 8 languages — depth over breadth
- **Interface**: CLI + MCP vs CLI + MCP + dashboard — no web UI to maintain
- **Dependencies**: Minimal (ONNX vs PyTorch, sqlite-vec vs ChromaDB)
- **Extensions**: MCP resources, repo map, git-blame, configurable embeddings
