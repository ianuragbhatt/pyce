"""SQLite graph store for code relationships."""

from __future__ import annotations

import json
import threading

from pyce.models import EdgeType, GraphEdge, GraphNode, NodeType
from pyce.storage.sqlite_compat import sqlite3


class GraphStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._init_tables()

    def _init_tables(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    properties TEXT DEFAULT '{}'
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    PRIMARY KEY (source_id, target_id, edge_type)
                )
            """)
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type)")
            self._conn.commit()

    def ingest_nodes(self, nodes: list[GraphNode]) -> None:
        if not nodes:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO nodes (id, node_type, name, file_path, properties) VALUES (?, ?, ?, ?, ?)",
                [(n.id, n.node_type.value, n.name, n.file_path, json.dumps(n.properties)) for n in nodes],
            )
            self._conn.commit()

    def ingest_edges(self, edges: list[GraphEdge]) -> None:
        if not edges:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO edges (source_id, target_id, edge_type, properties) VALUES (?, ?, ?, ?)",
                [(e.source_id, e.target_id, e.edge_type.value, json.dumps(e.properties)) for e in edges],
            )
            self._conn.commit()

    def neighbors_for_files(self, file_paths: list[str], edge_types: list[EdgeType] | None = None) -> list[tuple[str, str, str]]:
        if not file_paths:
            return []
        with self._lock:
            placeholders = ",".join("?" for _ in file_paths)
            type_filter = ""
            params: list = list(file_paths)
            if edge_types:
                type_placeholders = ",".join("?" for _ in edge_types)
                type_filter = f"AND e.edge_type IN ({type_placeholders})"
                params.extend(et.value for et in edge_types)

            rows = self._conn.execute(f"""
                SELECT DISTINCT e.target_id, e.edge_type, n.file_path
                FROM edges e
                JOIN nodes n ON n.id = e.target_id
                WHERE e.source_id IN (SELECT id FROM nodes WHERE file_path IN ({placeholders}))
                {type_filter}
            """, params).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]

    def get_neighbors(self, node_id: str, edge_type: EdgeType | None = None) -> list[GraphNode]:
        with self._lock:
            if edge_type:
                rows = self._conn.execute(
                    "SELECT n.id, n.node_type, n.name, n.file_path, n.properties FROM nodes n JOIN edges e ON n.id = e.target_id WHERE e.source_id = ? AND e.edge_type = ?",
                    (node_id, edge_type.value),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT n.id, n.node_type, n.name, n.file_path, n.properties FROM nodes n JOIN edges e ON n.id = e.target_id WHERE e.source_id = ?",
                    (node_id,),
                ).fetchall()
            return [GraphNode(id=r[0], node_type=NodeType(r[1]), name=r[2], file_path=r[3], properties=json.loads(r[4])) for r in rows]

    def delete_by_files(self, file_paths: list[str]) -> None:
        if not file_paths:
            return
        with self._lock:
            for fp in file_paths:
                node_ids = [r[0] for r in self._conn.execute(
                    "SELECT id FROM nodes WHERE file_path = ?", (fp,)
                ).fetchall()]
                if node_ids:
                    placeholders = ",".join("?" for _ in node_ids)
                    self._conn.execute(f"DELETE FROM nodes WHERE id IN ({placeholders})", node_ids)
                    self._conn.execute(f"DELETE FROM edges WHERE source_id IN ({placeholders})", node_ids)
                    self._conn.execute(f"DELETE FROM edges WHERE target_id IN ({placeholders})", node_ids)
            self._conn.commit()

    def get_all_nodes(self) -> list[GraphNode]:
        with self._lock:
            rows = self._conn.execute("SELECT id, node_type, name, file_path, properties FROM nodes").fetchall()
            return [GraphNode(id=r[0], node_type=NodeType(r[1]), name=r[2], file_path=r[3], properties=json.loads(r[4])) for r in rows]

    def get_all_edges(self) -> list[GraphEdge]:
        with self._lock:
            rows = self._conn.execute("SELECT source_id, target_id, edge_type, properties FROM edges").fetchall()
            return [GraphEdge(source_id=r[0], target_id=r[1], edge_type=EdgeType(r[2]), properties=json.loads(r[3])) for r in rows]
