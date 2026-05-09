# Feature Specifications

## MCP Tools (6)

### 1. `context_search`

Search codebase using hybrid retrieval.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Natural language or code query |
| `max_results` | int | no | Default 10, max 50 |
| `file_filter` | string | no | Glob pattern to restrict search |
| `include_graph` | bool | no | Expand results via import graph |

**Behavior**: Classifies query intent, runs vector + FTS search in parallel, fuses with RRF, applies confidence scoring and diversity filter, optionally expands via graph, packs to token budget.

### 2. `expand_chunk`

Get surrounding context for a specific chunk.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `chunk_id` | string | yes | Chunk identifier |
| `include_imports` | bool | no | Include imported symbols |
| `include_callers` | bool | no | Include functions that call this |

**Behavior**: Returns the chunk content plus its imports and/or callers (from graph table).

### 3. `related_context`

Find chunks related to a given chunk.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `chunk_id` | string | yes | Source chunk |
| `max_results` | int | no | Default 5 |

**Behavior**: Embeds the chunk content, runs vector similarity search, excludes the source chunk.

### 4. `repo_map`

Generate a repository overview with ranked symbols.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `format` | string | no | `"compact"` (default) or `"full"` |
| `max_symbols` | int | no | Default 100 |

**Behavior**: Returns file tree + top symbols ranked by PageRank (imported-by count). Compact format: `file:line kind name`. Full format: includes docstrings and signatures.

### 5. `index_status`

Get current index statistics.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | | | |

**Behavior**: Returns `{files_indexed, chunks_total, embedding_model, last_indexed, index_size_bytes, db_path}`.

### 6. `reindex`

Trigger re-indexing of the project.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `force` | bool | no | Re-index all files (ignore hash cache) |

**Behavior**: Runs the full indexing pipeline. With `force=false`, only processes changed files.

---

## MCP Resources (3)

### 1. `pyce://project/overview`

Returns project metadata: name, root path, file count, language breakdown, top-level structure.

### 2. `pyce://symbols/{file}`

Returns all symbols (functions, classes, methods) defined in a specific file with line numbers and signatures.

### 3. `pyce://index/status`

Returns index health: last indexed time, chunk count, embedding model, DB size, any errors.

---

## CLI Commands (5)

```
pyce init          # Create pyce.yaml config + .pyce/ directory
pyce index         # Run indexing pipeline (incremental by default)
pyce search "query" # Hybrid search from terminal
pyce status        # Print index stats
pyce serve         # Start MCP server (stdio transport)
```

### `pyce init`

Creates `pyce.yaml` with defaults and `.pyce/` directory. Interactive prompts for embedding model selection.

### `pyce index [--force] [--watch]`

Runs indexing pipeline. `--force` re-indexes everything. `--watch` uses `watchdog` for live re-indexing on file changes.

### `pyce search <query> [--max N] [--file GLOB]`

Runs hybrid search and prints results to stdout with file path, line range, confidence score, and content preview.

### `pyce status`

Prints: files indexed, chunks, embedding model, DB size, last indexed time.

### `pyce serve [--transport stdio]`

Starts MCP server. Default transport is `stdio`. Registers all 6 tools and 3 resources.

---

## Indexing Pipeline

### File Discovery (`indexer/walker.py`)

- Walks project root recursively
- Respects `.gitignore` patterns via `pathspec`
- Filters by configurable extensions (default: `.py`)
- Skips hidden dirs (`.git`, `.venv`, `__pycache__`, `node_modules`)

### Change Detection (`indexer/hasher.py`)

- SHA-256 hash of file contents
- Compared against `files` table in SQLite
- Skips parsing + embedding if hash matches
- Tracks `mtime` for filesystem-level quick check

### Secret Redaction (`indexer/secrets.py`)

Pattern-based detection before embedding:

| Pattern | Example |
|---------|---------|
| API keys | `sk-...`, `AKIA...` |
| Tokens | `ghp_...`, `Bearer ...` |
| Passwords | `password = "..."` |
| Private keys | `-----BEGIN RSA PRIVATE KEY-----` |

Redacted content is stored with `[REDACTED]` markers. Original file is never modified.

### Tree-sitter Chunking (`indexer/parser.py`)

Python AST-aware chunking using `tree-sitter-python`:

| Node Type | Chunk Boundary |
|-----------|---------------|
| `function_definition` | Entire function including decorators |
| `class_definition` | Class header + methods (or split if >500 tokens) |
| `module` | Top-level code between functions/classes |
| `import_statement` | Grouped with the chunk that uses them |

**Chunk metadata**: `id`, `file`, `start_line`, `end_line`, `kind`, `name`, `content`, `tokens`.

### Embedding (`indexer/embedder.py`)

- Model: configurable via `pyce.yaml` (default: `BAAI/bge-small-en-v1.5`)
- Library: `fastembed` (ONNX runtime, CPU-only)
- Cache: embeddings keyed by content hash, not file path
  - Survives file renames
  - Shares embeddings across identical content in different files
- Batch processing: embeds chunks in batches of 64

### Graph Construction (`indexer/graph.py`)

- Parses `import` and `from X import Y` statements
- Builds `(source_chunk, target_chunk, edge_type)` edges
- Edge types: `imports`, `calls`, `inherits`
- PageRank computed on the import graph for repo map ranking

---

## Retrieval Pipeline

### Query Intent Classification (`retrieval/query.py`)

| Intent | Signal | Strategy |
|--------|--------|----------|
| `code` | Contains code tokens, function names | Boost vector weight |
| `search` | Natural language description | Balance vector + FTS |
| `technical` | Framework/library terms | Boost FTS weight |

### Hybrid Search (`retrieval/search.py`)

Two searches run in parallel:

1. **Vector search**: sqlite-vec KNN, top 50 candidates
2. **FTS search**: FTS5 MATCH, top 50 candidates

### RRF Fusion (`retrieval/search.py`)

Reciprocal Rank Fusion with `k=60`:

```
RRF_score(d) = Σ 1 / (k + rank_i(d))
```

No weight tuning required. Proven to outperform weighted averages in most code search benchmarks.

### Confidence Scoring (`retrieval/scoring.py`)

3-factor scoring:

| Factor | Weight | Source |
|--------|--------|--------|
| Vector similarity | 50% | sqlite-vec distance |
| Keyword relevance | 40% | FTS5 BM25 score |
| Recency | 10% | File mtime (normalized) |

Final score: `0.5 * vec + 0.4 * kw + 0.1 * recency`, normalized to [0, 1].

### File Diversity (`retrieval/diversity.py`)

Max 3 chunks per file in final results. Prevents single-file domination.

### Graph Expansion (`retrieval/expansion.py`)

1-hop expansion: for each result, include chunks that import or are imported by it. Adds at most 2 graph-expanded chunks per original result.

### Token Budget Packing (`retrieval/packing.py`)

Fits results into a configurable token budget (default: 4000 tokens). Greedy packing: highest-scored results first, truncated if needed.

---

## Compression

### Truncation (always on)

- Smart truncation: preserves function signature + first N lines
- Applied when chunk exceeds budget after packing
- Preserves docstrings when present

### LLM Compression (optional)

- **Ollama** (local, default): runs `qwen2.5-coder:7b` or configured model
- **OpenAI** (fallback): uses `gpt-4o-mini` if Ollama unavailable
- Quality check: compressed output must retain ≥40% of original identifiers
- Falls back to truncation if quality check fails

---

## Editor Integration

### Claude Code

Generates `.mcp.json`:

```json
{
  "mcpServers": {
    "pyce": {
      "command": "pyce",
      "args": ["serve"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

### GitHub Copilot

Generates `.vscode/mcp.json`:

```json
{
  "servers": {
    "pyce": {
      "command": "pyce",
      "args": ["serve"],
      "type": "stdio"
    }
  }
}
```

### Opencode

Generates `opencode.json`:

```json
{
  "mcp": {
    "pyce": {
      "command": ["pyce", "serve"]
    }
  }
}
```
