"""SQLite compatibility helpers.

Some Python distributions ship with SQLite compiled without optional modules
like FTS5. pyce relies on FTS5 for its keyword index, so we attempt to
transparently fall back to `pysqlite3-binary` when the stdlib sqlite3 lacks it.
"""

from __future__ import annotations

from typing import Any

import sqlite3 as _stdlib_sqlite3


def _supports_fts5(sqlite3_mod: Any) -> bool:
    try:
        conn = sqlite3_mod.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE __pyce_fts5_test USING fts5(content)")
        finally:
            conn.close()
        return True
    except Exception:
        return False


# Prefer stdlib sqlite3 when it supports FTS5; otherwise try pysqlite3.
if _supports_fts5(_stdlib_sqlite3):
    sqlite3 = _stdlib_sqlite3
else:
    try:
        import pysqlite3 as sqlite3  # type: ignore
    except Exception:  # pragma: no cover
        sqlite3 = _stdlib_sqlite3


FTS5_AVAILABLE: bool = _supports_fts5(sqlite3)

