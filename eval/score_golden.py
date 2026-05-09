#!/usr/bin/env python3
"""Score pyce retrieval against eval/golden_queries.json (v2).

Run from the project root after indexing:

    uv run python eval/score_golden.py --top-k 10 --relax-k 20

Metrics:
- primary_hit@k: any primary_files path in top-k chunk paths
- union_hit@k: any primary ∪ secondary in top-k
- partial@k: 1.0 if primary_hit else 0.5 if union_hit else 0.0
- relax_union: union hit in top relax_k (wider pool)
- mrr_primary / mrr_union: reciprocal rank of first matching chunk
- mention_coverage: mean fraction of must_mention phrases found (case-insensitive)
  in concatenated text of the first mention_pool_k chunks

Stratified means are printed per category. Optional --report-json for machine-readable output.

Supports legacy v1 items with only expected_files: first path -> primary, rest -> secondary.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pyce.config import load_config
from pyce.indexer.embedder import EmbeddingCache, Embedder
from pyce.indexer.pipeline import _project_hash
from pyce.retrieval.retriever import HybridRetriever
from pyce.storage.backend import LocalBackend


@dataclass
class RowResult:
    id: str
    category: str
    primary_hit_k: bool
    union_hit_k: bool
    relax_union: bool
    partial: float
    rr_primary: float
    rr_union: float
    mention_cov: float
    top1_path: str


def _normalize_files(item: dict[str, Any]) -> tuple[list[str], list[str]]:
    if item.get("primary_files") is not None:
        p = list(item.get("primary_files") or [])
        s = list(item.get("secondary_files") or [])
        return p, s
    legacy = list(item.get("expected_files") or [])
    if not legacy:
        return [], []
    return [legacy[0]], legacy[1:]


def _first_rank(paths: list[str], targets: set[str]) -> int | None:
    for i, p in enumerate(paths):
        if p in targets:
            return i + 1
    return None


def _mention_coverage(chunks: list[Any], phrases: list[str]) -> float:
    if not phrases:
        return 1.0
    blob = "\n".join(c.content or "" for c in chunks).lower()
    hits = sum(1 for ph in phrases if ph.lower() in blob)
    return hits / len(phrases)


async def _evaluate(
    retriever: HybridRetriever,
    backend: LocalBackend,
    item: dict[str, Any],
    top_k: int,
    relax_k: int,
    mention_pool_k: int,
    max_tokens: int,
) -> RowResult | None:
    primary, secondary = _normalize_files(item)
    union = set(primary) | set(secondary)
    phrases: list[str] = list(item.get("must_mention") or [])

    count = await backend.count()
    if count == 0:
        return None

    fetch_k = max(top_k, relax_k, mention_pool_k)
    result = await retriever.retrieve(item["query"], top_k=fetch_k, max_tokens=max_tokens)
    paths = [c.file_path for c in result.chunks]
    if not paths:
        return RowResult(
            id=item["id"],
            category=item.get("category", "unknown"),
            primary_hit_k=False,
            union_hit_k=False,
            relax_union=False,
            partial=0.0,
            rr_primary=0.0,
            rr_union=0.0,
            mention_cov=_mention_coverage([], phrases),
            top1_path="",
        )

    pk = paths[:top_k]
    rk = paths[:relax_k]
    mk = result.chunks[:mention_pool_k]

    primary_set = set(primary)
    union_set = union

    phit = any(p in primary_set for p in pk)
    uhit = any(p in union_set for p in pk)
    rhit = any(p in union_set for p in rk)

    partial = 1.0 if phit else (0.5 if uhit else 0.0)

    rrp = _first_rank(paths, primary_set)
    rru = _first_rank(paths, union_set)
    rr_primary = 1.0 / rrp if rrp else 0.0
    rr_union = 1.0 / rru if rru else 0.0

    mcov = _mention_coverage(mk, phrases)

    return RowResult(
        id=item["id"],
        category=item.get("category", "unknown"),
        primary_hit_k=phit,
        union_hit_k=uhit,
        relax_union=rhit,
        partial=partial,
        rr_primary=rr_primary,
        rr_union=rr_union,
        mention_cov=mcov,
        top1_path=paths[0],
    )


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


async def main_async() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path(__file__).resolve().parent / "golden_queries.json",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--relax-k", type=int, default=20)
    parser.add_argument("--mention-pool-k", type=int, default=20)
    parser.add_argument("--max-tokens", type=int, default=8000)
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true", help="Only print summary + JSON report")
    args = parser.parse_args()

    project_root = (args.project_root or Path.cwd()).resolve()
    config = load_config(project_root)
    storage_dir = Path(config.storage_path) / _project_hash(project_root)
    db_path = str(storage_dir / "index.db")

    backend = LocalBackend(db_path)
    cache = EmbeddingCache(db_path)
    embedder = Embedder(model_name=config.embedding.model, cache=cache)
    retriever = HybridRetriever(backend, config.retrieval, embedder)

    data = json.loads(args.golden.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = data["items"]

    rows: list[RowResult] = []
    for item in items:
        row = await _evaluate(
            retriever,
            backend,
            item,
            args.top_k,
            args.relax_k,
            args.mention_pool_k,
            args.max_tokens,
        )
        if row is None:
            print("Index empty — run `pyce index` first.")
            return
        rows.append(row)
        if not args.quiet:
            tag = "OK" if row.primary_hit_k else ("PART" if row.union_hit_k else "MISS")
            print(
                f"{row.id} [{row.category}] {tag} "
                f"p@{args.top_k}={int(row.primary_hit_k)} "
                f"u@{args.top_k}={int(row.union_hit_k)} "
                f"relax={int(row.relax_union)} "
                f"partial={row.partial:.1f} "
                f"m_mention={row.mention_cov:.2f} "
                f":: {item['query'][:55]}..."
            )
            if not row.primary_hit_k and row.top1_path:
                print(f"    top1: {row.top1_path}")

    n = len(rows)
    primary_hits = [float(r.primary_hit_k) for r in rows]
    union_hits = [float(r.union_hit_k) for r in rows]
    relax_hits = [float(r.relax_union) for r in rows]
    partials = [r.partial for r in rows]
    ments = [r.mention_cov for r in rows]

    by_cat: dict[str, list[RowResult]] = defaultdict(list)
    for r in rows:
        by_cat[r.category].append(r)

    print("---")
    print(f"golden version: {data.get('version')}, items: {n}")
    print(f"mean primary_hit@{args.top_k}: {_mean(primary_hits):.3f}")
    print(f"mean union_hit@{args.top_k}: {_mean(union_hits):.3f}")
    print(f"mean partial (1 primary / 0.5 union): {_mean(partials):.3f}")
    print(f"mean relax_union@{args.relax_k}: {_mean(relax_hits):.3f}")
    print(f"mean MRR primary: {_mean([r.rr_primary for r in rows]):.3f}")
    print(f"mean MRR union: {_mean([r.rr_union for r in rows]):.3f}")
    print(f"mean must_mention coverage (pool={args.mention_pool_k}): {_mean(ments):.3f}")
    print("--- stratified primary_hit@k ---")
    for cat in sorted(by_cat.keys()):
        rs = by_cat[cat]
        ph = _mean([float(r.primary_hit_k) for r in rs])
        print(f"  {cat}: {ph:.3f} (n={len(rs)})")

    if args.report_json:
        report = {
            "top_k": args.top_k,
            "relax_k": args.relax_k,
            "mention_pool_k": args.mention_pool_k,
            "counts": n,
            "mean_primary_hit_k": _mean(primary_hits),
            "mean_union_hit_k": _mean(union_hits),
            "mean_partial": _mean(partials),
            "mean_relax_union": _mean(relax_hits),
            "mean_mrr_primary": _mean([r.rr_primary for r in rows]),
            "mean_mrr_union": _mean([r.rr_union for r in rows]),
            "mean_mention_coverage": _mean(ments),
            "by_category": {
                cat: {
                    "n": len(rs),
                    "mean_primary_hit_k": _mean([float(r.primary_hit_k) for r in rs]),
                }
                for cat, rs in sorted(by_cat.items())
            },
            "rows": [asdict(r) for r in rows],
        }
        args.report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {args.report_json}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
