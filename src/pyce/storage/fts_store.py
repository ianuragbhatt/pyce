"""SQLite FTS5 full-text search store."""

from __future__ import annotations

import threading

from pyce.models import Chunk, ChunkType
from pyce.storage.sqlite_compat import FTS5_AVAILABLE, sqlite3


class FTSStore:
    def __init__(self, db_path: str):
        if not FTS5_AVAILABLE:
            raise RuntimeError(
                "SQLite FTS5 is not available in this Python environment. "
                "Install a Python build that includes FTS5, or install the optional "
                "dependency `pysqlite3-binary` (recommended) and re-run."
            )
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._init_tables()

    def _init_tables(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    id, content, file_path, language, chunk_type,
                    tokenize='porter unicode61'
                )
            """)
            self._conn.commit()

    def ingest(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO chunks_fts (id, content, file_path, language, chunk_type) VALUES (?, ?, ?, ?, ?)",
                [(c.id, c.content[:5000], c.file_path, c.language, c.chunk_type.value) for c in chunks],
            )
            self._conn.commit()

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        safe_query = f'"{query}"'
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, rank FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                (safe_query, top_k),
            ).fetchall()
            return [(row[0], -row[1]) for row in rows]

    def delete_by_files(self, file_paths: list[str]) -> None:
        if not file_paths:
            return
        with self._lock:
            for fp in file_paths:
                self._conn.execute("DELETE FROM chunks_fts WHERE file_path = ?", (fp,))
            self._conn.commit()
