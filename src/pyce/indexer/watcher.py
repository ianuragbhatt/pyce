"""File system watcher for automatic re-indexing."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent


class _DebouncedHandler(FileSystemEventHandler):
    def __init__(self, callback, debounce_ms: int = 500, include_extensions: list[str] | None = None):
        super().__init__()
        self._callback = callback
        self._debounce_ms = debounce_ms
        self._allowed = {e.lower() for e in (include_extensions or [".py"])}
        self._pending: set[str] = set()
        self._timer: threading.Timer | None = None
        self._lock = threading.RLock()

    def on_modified(self, event):
        if not event.is_directory and _matches_allowed(event.src_path, self._allowed):
            self._schedule(event.src_path)

    def on_created(self, event):
        if not event.is_directory and _matches_allowed(event.src_path, self._allowed):
            self._schedule(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and _matches_allowed(event.src_path, self._allowed):
            self._schedule(event.src_path)

    def _schedule(self, path: str) -> None:
        with self._lock:
            self._pending.add(path)
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_ms / 1000.0, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            paths = list(self._pending)
            self._pending.clear()
        if paths:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._callback(paths), loop)
                else:
                    loop.run_until_complete(self._callback(paths))
            except RuntimeError:
                pass


class FileWatcher:
    def __init__(self, project_root: Path, callback, debounce_ms: int = 500, include_extensions: list[str] | None = None):
        self._root = project_root
        self._handler = _DebouncedHandler(callback, debounce_ms, include_extensions=include_extensions)
        self._observer = Observer()

    def start(self) -> None:
        self._observer.schedule(self._handler, str(self._root), recursive=True)
        self._observer.daemon = True
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=5)


def _matches_allowed(path: str, allowed: set[str]) -> bool:
    lower = path.lower()
    # handle filename-only entries like "dockerfile"
    basename = lower.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in basename:
        ext = "." + basename.rsplit(".", 1)[-1]
        return ext in allowed
    return basename in allowed
