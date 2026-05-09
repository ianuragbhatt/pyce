"""Secret detection and redaction."""

from __future__ import annotations

import re
from pathlib import Path

from pyce.config import SECRET_CONTENT_PATTERNS, SECRET_PATTERNS


_SECRET_FILENAME_RE = [re.compile(p, re.IGNORECASE) for p in SECRET_PATTERNS]
_SECRET_CONTENT_RE = [re.compile(p) for p in SECRET_CONTENT_PATTERNS]

REDACTED = "[REDACTED]"


def is_secret_file(file_path: Path) -> bool:
    name = file_path.name
    path_str = str(file_path).replace("\\", "/")
    for pattern in _SECRET_FILENAME_RE:
        if pattern.search(name) or pattern.search(path_str):
            return True
    return False


def redact_secrets(content: str) -> str:
    for pattern in _SECRET_CONTENT_RE:
        content = pattern.sub(REDACTED, content)
    return content


def has_secrets(content: str) -> bool:
    for pattern in _SECRET_CONTENT_RE:
        if pattern.search(content):
            return True
    return False
