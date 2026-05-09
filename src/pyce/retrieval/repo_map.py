"""PageRank-based repository map for project overview."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from pyce.models import EdgeType, GraphEdge, GraphNode
from pyce.storage.backend import LocalBackend


async def generate_repo_map(backend: LocalBackend, max_tokens: int = 2000) -> str:
    nodes = await backend.get_all_nodes()
    edges = await backend.get_all_edges()

    if not nodes:
        return "No index data available."

    pageranks = _compute_pagerank(nodes, edges)

    file_nodes = [n for n in nodes if n.node_type.value == "FILE"]
    chunk_nodes = [n for n in nodes if n.node_type.value in ("FUNCTION", "CLASS")]

    file_scores: dict[str, float] = {}
    for fn in file_nodes:
        children = [e.target_id for e in edges if e.source_id == fn.id and e.edge_type == EdgeType.DEFINES]
        score = sum(pageranks.get(cid, 0) for cid in children)
        file_scores[fn.file_path] = score

    sorted_files = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)

    lines: list[str] = []
    lines.append("# Repository Map\n")
    tokens_used = 0

    for file_path, score in sorted_files:
        file_line = f"\n## {file_path}\n"
        if tokens_used + len(file_line) // 4 > max_tokens:
            break
        lines.append(file_line)
        tokens_used += len(file_line) // 4

        file_chunks = [n for n in chunk_nodes if n.file_path == file_path]
        file_chunks.sort(key=lambda n: pageranks.get(n.id, 0), reverse=True)

        for chunk in file_chunks[:10]:
            prefix = "class" if chunk.node_type.value == "CLASS" else "def"
            line = f"- `{prefix} {chunk.name}`"
            if tokens_used + len(line) // 4 > max_tokens:
                break
            lines.append(line)
            tokens_used += len(line) // 4

    return "\n".join(lines)


def _compute_pagerank(nodes: list[GraphNode], edges: list[GraphEdge], damping: float = 0.85, iterations: int = 20) -> dict[str, float]:
    node_ids = {n.id for n in nodes}
    if not node_ids:
        return {}

    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.source_id in node_ids and e.target_id in node_ids:
            adj[e.source_id].append(e.target_id)

    n = len(node_ids)
    rank = {nid: 1.0 / n for nid in node_ids}

    for _ in range(iterations):
        new_rank: dict[str, float] = {}
        dangling_sum = sum(rank[nid] for nid in node_ids if not adj[nid])

        for nid in node_ids:
            incoming = sum(rank[src] / len(adj[src]) for src in node_ids if nid in adj[src])
            new_rank[nid] = (1 - damping) / n + damping * (incoming + dangling_sum / n)

        rank = new_rank

    return rank
