"""SQLite-vec vector store."""

from __future__ import annotations

import json
import sqlite3
import struct
import threading

import sqlite_vec

from pyce.models import Chunk, ChunkType


class VectorStore:
    def __init__(self, db_path: str, dim: int = 384):
        self._db_path = db_path
        self._dim = dim
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._init_tables()

    def _init_tables(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    chunk_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    language TEXT DEFAULT 'python',
                    confidence_score REAL DEFAULT 0.0,
                    compressed_content TEXT
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS chunk_compressions (
                    chunk_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    compressed TEXT NOT NULL,
                    PRIMARY KEY (chunk_id, level)
                )
            """)
            try:
                self._conn.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
                        chunk_id TEXT PRIMARY KEY,
                        embedding float[{self._dim}]
                    )
                """)
            except sqlite3.OperationalError:
                pass
            self._conn.commit()

    def ingest(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO chunks (id, content, chunk_type, file_path, start_line, end_line, language, confidence_score, compressed_content) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        c.id,
                        c.content[:5000],
                        c.chunk_type.value,
                        c.file_path,
                        c.start_line,
                        c.end_line,
                        c.language,
                        c.confidence_score,
                        c.compressed_content,
                    )
                    for c in chunks
                ],
            )

            vec_rows: list[tuple[str, bytes]] = []
            for c in chunks:
                if not c.embedding:
                    continue
                blob = struct.pack(f"{len(c.embedding)}f", *c.embedding)
                vec_rows.append((c.id, blob))
            if vec_rows:
                self._conn.executemany(
                    "INSERT OR REPLACE INTO chunks_vec (chunk_id, embedding) VALUES (?, ?)",
                    vec_rows,
                )
            self._conn.commit()

    def search(self, query_embedding: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        with self._lock:
            blob = struct.pack(f"{len(query_embedding)}f", *query_embedding)
            rows = self._conn.execute(
                "SELECT chunk_id, distance FROM chunks_vec WHERE embedding MATCH ? AND k = ?",
                (blob, top_k),
            ).fetchall()
            return [(row[0], row[1]) for row in rows]

    def get_chunk_by_id(self, chunk_id: str) -> Chunk | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, content, chunk_type, file_path, start_line, end_line, language, confidence_score, compressed_content FROM chunks WHERE id = ?",
                (chunk_id,),
            ).fetchone()
            if row is None:
                return None
            return Chunk(
                id=row[0], content=row[1], chunk_type=ChunkType(row[2]),
                file_path=row[3], start_line=row[4], end_line=row[5],
                language=row[6], confidence_score=row[7], compressed_content=row[8],
            )

    def get_chunks_by_file(self, file_path: str) -> list[Chunk]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, content, chunk_type, file_path, start_line, end_line, language, confidence_score, compressed_content FROM chunks WHERE file_path = ?",
                (file_path,),
            ).fetchall()
            return [Chunk(
                id=r[0], content=r[1], chunk_type=ChunkType(r[2]),
                file_path=r[3], start_line=r[4], end_line=r[5],
                language=r[6], confidence_score=r[7], compressed_content=r[8],
            ) for r in rows]

    def delete_by_files(self, file_paths: list[str]) -> None:
        if not file_paths:
            return
        with self._lock:
            for fp in file_paths:
                chunk_ids = [r[0] for r in self._conn.execute(
                    "SELECT id FROM chunks WHERE file_path = ?", (fp,)
                ).fetchall()]
                if chunk_ids:
                    placeholders = ",".join("?" for _ in chunk_ids)
                    self._conn.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", chunk_ids)
                    self._conn.execute(f"DELETE FROM chunks_vec WHERE chunk_id IN ({placeholders})", chunk_ids)
            self._conn.commit()

    def get_all_chunk_hashes(self) -> set[str]:
        with self._lock:
            rows = self._conn.execute("SELECT id FROM chunks").fetchall()
            return {r[0] for r in rows}

    def get_compression(self, chunk_id: str, level: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT compressed FROM chunk_compressions WHERE chunk_id=? AND level=?",
                (chunk_id, level),
            ).fetchone()
            return row[0] if row else None

    def put_compression(self, chunk_id: str, level: str, compressed: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO chunk_compressions (chunk_id, level, compressed) VALUES (?, ?, ?)",
                (chunk_id, level, compressed),
            )
            self._conn.commit()

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def file_count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(DISTINCT file_path) FROM chunks").fetchone()[0]
