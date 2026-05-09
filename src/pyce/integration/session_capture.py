"""Session history and decision tracking."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SessionCapture:
    def __init__(self, sessions_dir: Path):
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._session_id: str | None = None
        self._decisions: list[dict] = []
        self._code_areas: list[dict] = []
        self._touched_files: set[str] = set()
        self._lock = threading.RLock()

    def start_session(self) -> str:
        with self._lock:
            self._session_id = uuid.uuid4().hex[:12]
            self._decisions = []
            self._code_areas = []
            self._touched_files = set()
            return self._session_id

    def record_decision(self, decision: str, reason: str = "") -> None:
        with self._lock:
            self._decisions.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "decision": decision,
                "reason": reason,
            })

    def record_code_area(self, file_path: str, description: str = "") -> None:
        with self._lock:
            self._code_areas.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "file_path": file_path,
                "description": description,
            })
            self._touched_files.add(file_path)

    def touch_files(self, file_paths: list[str]) -> None:
        with self._lock:
            self._touched_files.update(file_paths)

    def end_session(self) -> Path | None:
        with self._lock:
            if not self._session_id:
                return None

            session_data = {
                "session_id": self._session_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "decisions": self._decisions,
                "code_areas": self._code_areas,
                "touched_files": sorted(self._touched_files),
            }

            path = self._dir / f"{self._session_id}.json"
            with open(path, "w") as f:
                json.dump(session_data, f, indent=2)

            self._session_id = None
            return path

    def recall_decisions(self, query: str = "", limit: int = 10) -> list[dict]:
        decisions: list[dict] = []
        for path in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                with open(path) as f:
                    data = json.load(f)
                for d in data.get("decisions", []):
                    if query and query.lower() not in d.get("decision", "").lower():
                        continue
                    decisions.append(d)
                    if len(decisions) >= limit:
                        return decisions
            except (json.JSONDecodeError, OSError):
                continue
        return decisions

    def get_recent_areas(self, limit: int = 20) -> list[dict]:
        areas: list[dict] = []
        for path in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                with open(path) as f:
                    data = json.load(f)
                for a in data.get("code_areas", []):
                    areas.append(a)
                    if len(areas) >= limit:
                        return areas
            except (json.JSONDecodeError, OSError):
                continue
        return areas
