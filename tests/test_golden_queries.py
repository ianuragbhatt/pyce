"""Golden eval set schema and consistency with eval/build_golden_queries.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GOLDEN_PATH = _REPO_ROOT / "eval" / "golden_queries.json"
_BUILD_SCRIPT = _REPO_ROOT / "eval" / "build_golden_queries.py"


def _load_build_module():
    spec = importlib.util.spec_from_file_location("build_golden_queries", _BUILD_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _norm_item(d: dict) -> dict:
    return {
        "id": d["id"],
        "category": d["category"],
        "query": d["query"],
        "answer": d["answer"],
        "primary_files": sorted(d["primary_files"]),
        "secondary_files": sorted(d["secondary_files"]),
        "must_mention": sorted(d["must_mention"]),
    }


def _load_golden() -> dict:
    assert _GOLDEN_PATH.is_file(), f"Missing {_GOLDEN_PATH}"
    return json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))


def test_golden_queries_committed_matches_builder_items():
    """Committed JSON must match eval/build_golden_queries.py items() exactly."""
    mod = _load_build_module()
    built = mod.items()
    data = _load_golden()

    by_id_json = {item["id"]: item for item in data["items"]}
    by_id_built = {item["id"]: item for item in built}

    assert set(by_id_json) == set(by_id_built)
    for gid in by_id_built:
        assert _norm_item(by_id_json[gid]) == _norm_item(by_id_built[gid]), gid


def test_golden_queries_schema_and_metadata():
    data = _load_golden()
    assert data.get("version") == 2
    assert data.get("project") == "pyce"
    assert "categories" in data and isinstance(data["categories"], dict)
    items = data["items"]
    assert len(items) >= 50, "golden set should remain substantial"

    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids)), "duplicate ids in golden_queries.json"

    cat_keys = set(data["categories"])
    required_keys = frozenset(
        {"id", "category", "query", "answer", "primary_files", "secondary_files", "must_mention"}
    )

    for item in items:
        assert set(item.keys()) == required_keys, item.get("id")
        assert item["category"] in cat_keys, f"unknown category: {item['id']} -> {item['category']}"
        for key in ("primary_files", "secondary_files", "must_mention"):
            assert isinstance(item[key], list), item["id"]
            assert all(isinstance(x, str) for x in item[key]), item["id"]
        assert item["primary_files"], f"{item['id']}: primary_files must be non-empty"
        assert isinstance(item["query"], str) and item["query"].strip()
        assert isinstance(item["answer"], str) and item["answer"].strip()


def test_golden_queries_referenced_paths_exist():
    data = _load_golden()
    for item in data["items"]:
        for rel in item["primary_files"] + item["secondary_files"]:
            path = _REPO_ROOT / rel
            assert path.is_file(), f"{item['id']}: missing file {rel}"
