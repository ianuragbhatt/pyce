"""Lossy compression quality detection."""

from __future__ import annotations

import re


def has_quality(original: str, compressed: str) -> bool:
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", original))
    identifiers = {i for i in identifiers if len(i) > 2}
    if not identifiers:
        return True

    compressed_lower = compressed.lower()
    matched = sum(1 for i in identifiers if i.lower() in compressed_lower)
    return (matched / len(identifiers)) >= 0.4
