# Coding Philosophy

These rules apply to every project. Bias toward caution over speed. For trivial tasks, use judgment.

## Think Before Coding

- State assumptions explicitly before starting. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop and ask rather than guess.

## Simplicity First

- Write the minimum code that solves the problem. Nothing speculative.
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

## Surgical Changes

- Touch only what the task requires.
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style exactly, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.
- Remove imports/variables/functions that YOUR changes made unused. Leave pre-existing dead code alone.

## Goal-Driven Execution

For multi-step tasks, state a brief plan with verifiable steps before starting:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Transform tasks into verifiable goals:
- "Fix the bug" → write a test that reproduces it, then make it pass
- "Refactor X" → ensure tests pass before and after

## Project: pyce (Python Code Context Engine)

MCP server that indexes Python codebases for AI coding assistants.

### Package Manager

Use `uv`. Already installed.

### Critical Files

| File | Purpose |
|------|---------|
| `src/pyce/cli.py` | CLI entry point (`pyce` command) |
| `src/pyce/config.py` | Config loading (`.context-engine.yaml`) |
| `src/pyce/models.py` | Data models: Chunk, GraphNode, GraphEdge |
| `src/pyce/indexer/pipeline.py` | Core indexing pipeline |
| `src/pyce/indexer/chunker.py` | Tree-sitter Python AST chunking |
| `src/pyce/indexer/embedder.py` | fastembed wrapper + cache |
| `src/pyce/storage/backend.py` | Composite storage (vector + FTS + graph) |
| `src/pyce/retrieval/retriever.py` | Hybrid search + RRF + graph expansion |
| `src/pyce/integration/mcp_server.py` | MCP server (6 tools + 3 resources) |
| `src/pyce/integration/editors.py` | Editor auto-config |

### Key Docs

| Doc | Content |
|-----|---------|
| `docs/FUTURE_PLANS.md` | v1-v4 roadmap |
| `docs/ARCHITECTURE.md` | System design |
| `docs/FEATURE_SPECIFICATIONS.md` | MCP tools, CLI, pipeline |
| `docs/TECHNICAL_DECISIONS.md` | Why SQLite, fastembed, tree-sitter |
| `docs/REFERENCE_ANALYSIS.md` | Reference project analysis |

### Conventions

- Python 3.11+ (use `list[float] | None` union syntax)
- Async: `asyncio` for I/O, `asyncio.to_thread` for blocking ops
- SQLite: WAL mode, `check_same_thread=False`, RLock
- All storage in single SQLite DB per project
