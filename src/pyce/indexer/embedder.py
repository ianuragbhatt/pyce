"""Embedding generation with content-hash cache."""

from __future__ import annotations

import hashlib
import struct
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

from fastembed import TextEmbedding

from pyce.models import Chunk


class EmbeddingCache:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                content_hash TEXT PRIMARY KEY,
                model_name TEXT NOT NULL,
                dim INTEGER NOT NULL,
                embedding BLOB NOT NULL
            )
        """)
        self._conn.commit()
        self._lock = threading.RLock()

    def get(self, content_hash: str, model_name: str) -> list[float] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT dim, embedding FROM embedding_cache WHERE content_hash=? AND model_name=?",
                (content_hash, model_name),
            ).fetchone()
            if row is None:
                return None
            dim, blob = row
            return list(struct.unpack(f"{dim}f", blob))

    def put(self, content_hash: str, model_name: str, embedding: list[float]) -> None:
        with self._lock:
            blob = struct.pack(f"{len(embedding)}f", *embedding)
            self._conn.execute(
                "INSERT OR REPLACE INTO embedding_cache (content_hash, model_name, dim, embedding) VALUES (?, ?, ?, ?)",
                (content_hash, model_name, len(embedding), blob),
            )
            self._conn.commit()

    def get_batch(self, hashes: list[tuple[str, str]]) -> dict[str, list[float]]:
        results: dict[str, list[float]] = {}
        with self._lock:
            for i in range(0, len(hashes), 500):
                batch = hashes[i:i + 500]
                placeholders = ",".join("?" for _ in batch)
                params = [h for h, _ in batch]
                rows = self._conn.execute(
                    f"SELECT content_hash, dim, embedding FROM embedding_cache WHERE content_hash IN ({placeholders})",
                    params,
                ).fetchall()
                for content_hash, dim, blob in rows:
                    results[content_hash] = list(struct.unpack(f"{dim}f", blob))
        return results

    def put_batch(self, items: list[tuple[str, str, list[float]]]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO embedding_cache (content_hash, model_name, dim, embedding) VALUES (?, ?, ?, ?)",
                [(h, m, len(e), struct.pack(f"{len(e)}f", *e)) for h, m, e in items],
            )
            self._conn.commit()

    def prune_orphans(self, known_hashes: set[str]) -> None:
        with self._lock:
            all_rows = self._conn.execute("SELECT content_hash FROM embedding_cache").fetchall()
            to_delete = [r[0] for r in all_rows if r[0] not in known_hashes]
            for i in range(0, len(to_delete), 500):
                batch = to_delete[i:i + 500]
                placeholders = ",".join("?" for _ in batch)
                self._conn.execute(
                    f"DELETE FROM embedding_cache WHERE content_hash IN ({placeholders})", batch
                )
            self._conn.commit()


def _content_hash(model_name: str, text: str) -> str:
    return hashlib.sha256(f"{model_name}:{text}".encode()).hexdigest()[:16]


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", cache: EmbeddingCache | None = None):
        self._model_name = model_name
        self._model: TextEmbedding | None = None
        self._cache = cache
        self._lock = threading.RLock()

    def _get_model(self) -> TextEmbedding:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed(self, chunks: list[Chunk], batch_size: int = 64) -> None:
        if not chunks:
            return

        to_embed: list[tuple[int, str, str]] = []
        for i, chunk in enumerate(chunks):
            h = _content_hash(self._model_name, chunk.content)
            cached = self._cache.get(h, self._model_name) if self._cache else None
            if cached is not None:
                chunk.embedding = cached
            else:
                to_embed.append((i, h, chunk.content))

        if not to_embed:
            return

        model = self._get_model()
        texts = [t[2] for t in to_embed]
        embeddings = list(model.embed(texts, batch_size=batch_size))

        cache_items: list[tuple[str, str, list[float]]] = []
        for (idx, h, _), emb in zip(to_embed, embeddings):
            vec = list(emb)
            chunks[idx].embedding = vec
            cache_items.append((h, self._model_name, vec))

        if self._cache and cache_items:
            self._cache.put_batch(cache_items)

    @lru_cache(maxsize=256)
    def embed_query(self, query: str) -> tuple[float, ...]:
        model = self._get_model()
        emb = list(model.embed([query]))[0]
        return tuple(emb)

    def embed_query_list(self, query: str) -> list[float]:
        return list(self.embed_query(query))
