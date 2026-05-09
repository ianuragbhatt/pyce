from __future__ import annotations

from pathlib import Path

from pyce.config import Config
from pyce.indexer.pipeline import _discover_files


def test_discover_files_includes_supporting_extensions(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def hi():\n    return 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hello\n", encoding="utf-8")
    (tmp_path / "ignore.js").write_text("console.log('no')\n", encoding="utf-8")

    config = Config()
    files = _discover_files(tmp_path, config)
    rel = sorted(str(p.relative_to(tmp_path)).replace("\\", "/") for p in files)

    assert "src/app.py" in rel
    assert "pyproject.toml" in rel
    assert "README.md" in rel
    assert "ignore.js" not in rel

