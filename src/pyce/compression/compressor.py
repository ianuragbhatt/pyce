"""LLM-based chunk compression with truncation fallback."""

from __future__ import annotations

import re
import asyncio
import httpx

from pyce.config import CompressionConfig
from pyce.models import Chunk, ChunkType


_OLLAMA_TIMEOUT = 30.0


class Compressor:
    def __init__(self, config: CompressionConfig):
        self._config = config
        self._ollama_available: bool | None = None

    async def compress(self, chunk: Chunk, level: str = "standard") -> str:
        cached = None
        return self._truncation_compress(chunk, level)

    async def compress_with_llm(self, chunk: Chunk, level: str = "standard") -> str | None:
        if self._config.provider == "ollama":
            return await self._ollama_compress(chunk, level)
        elif self._config.provider == "openai":
            return await self._openai_compress(chunk, level)
        return None

    async def _ollama_compress(self, chunk: Chunk, level: str) -> str | None:
        if not await self._check_ollama():
            return None

        prompt = self._build_prompt(chunk, level)
        try:
            async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._config.base_url}/api/generate",
                    json={
                        "model": self._config.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 256},
                    },
                )
                resp.raise_for_status()
                result = resp.json().get("response", "").strip()
                if has_quality(chunk.content, result):
                    return result
                return None
        except Exception:
            return None

    async def _openai_compress(self, chunk: Chunk, level: str) -> str | None:
        if not self._config.api_key:
            return None

        prompt = self._build_prompt(chunk, level)
        try:
            async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._config.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._config.api_key}"},
                    json={
                        "model": self._config.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 256,
                    },
                )
                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"].strip()
                if has_quality(chunk.content, result):
                    return result
                return None
        except Exception:
            return None

    async def _check_ollama(self) -> bool:
        if self._ollama_available is not None:
            return self._ollama_available
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._config.base_url}/api/tags")
                self._ollama_available = resp.status_code == 200
        except Exception:
            self._ollama_available = False
        return self._ollama_available

    def _build_prompt(self, chunk: Chunk, level: str) -> str:
        type_hint = {
            ChunkType.FUNCTION: "Python function",
            ChunkType.CLASS: "Python class",
            ChunkType.MODULE: "Python module",
        }.get(chunk.chunk_type, "code")

        limits = {"minimal": 100, "standard": 300, "full": 800}
        limit = limits.get(level, 300)

        return (
            f"Compress this {type_hint} to under {limit} chars. "
            f"Keep the function/class signature, docstring if any, and key logic. "
            f"Remove comments, blank lines, and implementation details.\n\n"
            f"Code:\n{chunk.content[:2000]}"
        )

    def _truncation_compress(self, chunk: Chunk, level: str) -> str:
        limits = {"minimal": 100, "standard": 300, "full": 800}
        limit = limits.get(level, 300)

        if chunk.chunk_type in (ChunkType.FUNCTION, ChunkType.CLASS):
            return _extract_signature(chunk.content, limit)
        return chunk.content[:limit]


def _extract_signature(content: str, max_chars: int) -> str:
    lines = content.split("\n")
    result: list[str] = []
    in_body = False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if result:
                continue
            else:
                continue

        if not in_body:
            result.append(line)
            if stripped.endswith(":"):
                in_body = True
        elif stripped.startswith('"""') or stripped.startswith("'''"):
            result.append(line)
            if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                continue
        elif result and (result[-1].strip().startswith('"""') or result[-1].strip().startswith("'''")):
            result.append(line)
            if '"""' in stripped or "'''" in stripped:
                continue
        else:
            break

        if sum(len(r) for r in result) > max_chars:
            break

    return "\n".join(result) if result else content[:max_chars]


def has_quality(original: str, compressed: str) -> bool:
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", original))
    identifiers = {i for i in identifiers if len(i) > 2}
    if not identifiers:
        return True

    compressed_lower = compressed.lower()
    matched = sum(1 for i in identifiers if i.lower() in compressed_lower)
    return (matched / len(identifiers)) >= 0.4
