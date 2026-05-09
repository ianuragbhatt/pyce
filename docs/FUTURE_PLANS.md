# Future Plans

## Version Roadmap

### v1.0 — Core (current)

| Feature | Status |
|---------|--------|
| Tree-sitter Python chunking | ✅ |
| Hybrid search (vector + FTS) | ✅ |
| Graph expansion (1-hop) | ✅ |
| MCP server (stdio, 6 tools, 3 resources) | ✅ |
| Editor integration (Claude, Copilot, Opencode) | ✅ |
| CLI (init, index, search, status, serve) | ✅ |
| Incremental indexing (SHA-256) | ✅ |
| Secret redaction | ✅ |
| Configurable embedding model | ✅ |
| PageRank repo map | ✅ |
| Compression (truncation + optional LLM) | ✅ |

### v1.1 — MCP Enhancements

| Feature | Description |
|---------|-------------|
| MCP Prompts | Slash commands for common queries (`/explain`, `/refactor`, `/test`) |
| Output compression directives | `--compress` flag on tools to auto-summarize results |
| Structured output | JSON schema for tool results (typed responses) |
| Better error messages | Actionable error messages with suggested fixes |

### v2.0 — Retrieval

| Feature | Description |
|---------|-------------|
| Multi-resolution indexing | Index at function, class, module, and file levels simultaneously |
| Query expansion | Expand user query with synonyms, related terms from codebase |
| Branch-aware indexing | Index per git branch, switch context on checkout |
| Call-graph chunking | Chunk by call relationships, not just AST boundaries |
| ColBERT late interaction | Token-level interaction for better code matching |
| Code-specific re-ranker | Fine-tuned cross-encoder for code relevance |

### v2.0 — Knowledge

| Feature | Description |
|---------|-------------|
| Knowledge graph memory | Persistent entity-relationship graph across sessions |
| Decision trees | Track architectural decisions and their rationale |
| Forgetting curves | Decay relevance of untouched code over time |
| Session continuity | Resume context across MCP server restarts |
| Sampling for auto-docs | Periodically sample and summarize codebase sections |

### v3.0 — Scale

| Feature | Description |
|---------|-------------|
| Multi-language support | JS/TS, Go, Rust, Java via tree-sitter grammars |
| Remote indexing | Streamable HTTP transport for shared index servers |
| GPU embedding | CUDA/ROCm support for large codebases |
| Team memory | Shared index + annotations across team members |
| Web dashboard | Lightweight status/exploration UI |
| More editors | Zed, Neovim, JetBrains, Sublime Text |

### v4.0 — Intelligence

| Feature | Description |
|---------|-------------|
| Learned retrieval | Fine-tune embedding model on code search pairs |
| Auto re-indexing triggers | Git hooks, CI events, editor save |
| Code quality signals | Integrate linting/type-check results into ranking |
| Issue tracker integration | Link code to GitHub issues/Jira tickets |

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-15 | Python-only for v1.0 | Depth over breadth, one grammar to maintain |
| 2026-01-20 | SQLite over ChromaDB | Single file, no server, WAL mode, FTS5 built-in |
| 2026-01-22 | fastembed over sentence-transformers | 40x smaller, no PyTorch, fast enough |
| 2026-01-25 | tree-sitter over ast module | Error-tolerant, fine-grained nodes |
| 2026-01-28 | Click over argparse | Cleaner API, no extra deps |
| 2026-02-01 | RRF over weighted average | No tuning, proven algorithm |
| 2026-02-03 | stdio over HTTP transport | Simplest, universal editor support |
| 2026-02-05 | Content-hash cache | Survives renames, deduplicates |
| 2026-02-08 | PageRank for repo map | Transitive importance, automatic |
| 2026-02-10 | 3-factor scoring (50/40/10) | Vector primary, keywords for code, recency for context |
| 2026-02-12 | No dashboard in v1.0 | CLI + MCP sufficient, reduces maintenance |
| 2026-02-15 | Ollama + OpenAI fallback | Local-first, cloud-optional |
| 2026-02-18 | 3 editors (not 6) | Cover 80% of users, add more on demand |
| 2026-02-20 | MCP resources (new) | Passive metadata complements active search tools |
