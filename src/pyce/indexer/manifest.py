"""SHA-256 manifest for incremental indexing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


class Manifest:
    def __init__(self, manifest_path: Path):
        self._path = manifest_path
        self._data: dict = {"schema_version": 1, "files": {}, "last_git_sha": ""}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path) as f:
                self._data = json.load(f)

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    def has_changed(self, file_path: str, content_hash: str) -> bool:
        return self._data["files"].get(file_path) != content_hash

    def update_file(self, file_path: str, content_hash: str) -> None:
        self._data["files"][file_path] = content_hash

    def remove_file(self, file_path: str) -> None:
        self._data["files"].pop(file_path, None)

    def get_files(self) -> dict[str, str]:
        return dict(self._data["files"])

    @staticmethod
    def hash_content(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()
