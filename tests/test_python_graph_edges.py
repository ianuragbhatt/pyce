from __future__ import annotations

from pathlib import Path

from pyce.indexer.chunker import Chunker
from pyce.indexer.pipeline import _build_module_index, _resolve_import_to_file


def test_resolve_import_to_file_prefers_exact_match(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")

    files = [tmp_path / "pkg" / "__init__.py", tmp_path / "pkg" / "mod.py"]
    index = _build_module_index(tmp_path, files)

    assert _resolve_import_to_file("pkg.mod", index) == "pkg/mod.py"
    # fallback to parent module when importing a deeper symbol
    assert _resolve_import_to_file("pkg.mod.something", index) == "pkg/mod.py"


def test_chunker_extracts_calls_by_function() -> None:
    src = """
def a():
    b()
    obj.c()

def b():
    return 1
"""
    calls = Chunker()._extract_calls_by_function(src)  # type: ignore[attr-defined]
    assert calls["a"] >= {"b", "c"}
