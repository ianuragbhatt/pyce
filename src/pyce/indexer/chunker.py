"""Tree-sitter Python AST chunking."""

from __future__ import annotations

from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from pyce.models import Chunk, ChunkType


_PY_LANGUAGE = Language(tspython.language())

_FUNCTION_TYPES = {"function_definition", "async_function_definition"}
_CLASS_TYPES = {"class_definition"}
_DECORATED_TYPES = {"decorated_definition"}
_CALL_TYPES = {"call"}


class Chunker:
    def __init__(self):
        self._parser = Parser(_PY_LANGUAGE)

    def chunk(self, source: str, file_path: str) -> list[Chunk]:
        try:
            tree = self._parser.parse(source.encode("utf-8"))
            return self._extract_chunks(tree.root_node, source, file_path)
        except Exception:
            return [self._fallback_chunk(source, file_path)]

    def chunk_text(self, source: str, file_path: str, language: str) -> list[Chunk]:
        """
        Best-effort chunking for non-Python text/config files.

        We keep this intentionally simple: store a single MODULE chunk so retrieval
        can surface config/docs without forcing assistants to open files directly.
        """
        lines = source.split("\n")
        content = source[:5000]
        chunk_id = Chunk.make_id(file_path, 1, len(lines), content)
        return [
            Chunk(
                id=chunk_id,
                content=content,
                chunk_type=ChunkType.MODULE,
                file_path=file_path,
                start_line=1,
                end_line=len(lines),
                language=language,
            )
        ]

    def chunk_with_imports(self, source: str, file_path: str) -> tuple[list[Chunk], list[str]]:
        chunks = self.chunk(source, file_path)
        imports = self._extract_imports(source)
        return chunks, imports

    def chunk_with_relationships(
        self, source: str, file_path: str
    ) -> tuple[list[Chunk], list[str], dict[str, set[str]]]:
        """
        Chunk Python plus extract a lightweight call graph.

        Returns:
        - chunks: function/class/module chunks
        - imports: imported module strings ("pkg.subpkg")
        - calls: mapping of caller function name -> set of callee names (best-effort, local names only)
        """
        chunks, imports = self.chunk_with_imports(source, file_path)
        calls = self._extract_calls_by_function(source)
        return chunks, imports, calls

    def _extract_chunks(self, root: Node, source: str, file_path: str) -> list[Chunk]:
        chunks: list[Chunk] = []
        lines = source.split("\n")

        for node in root.children:
            if node.type in _FUNCTION_TYPES:
                chunks.append(self._make_chunk(node, lines, file_path, ChunkType.FUNCTION))
            elif node.type in _CLASS_TYPES:
                chunks.append(self._make_chunk(node, lines, file_path, ChunkType.CLASS))
            elif node.type in _DECORATED_TYPES:
                defn = node.child_by_field_name("definition")
                if defn and defn.type in _FUNCTION_TYPES:
                    chunks.append(self._make_chunk(node, lines, file_path, ChunkType.FUNCTION))
                elif defn and defn.type in _CLASS_TYPES:
                    chunks.append(self._make_chunk(node, lines, file_path, ChunkType.CLASS))
                else:
                    chunks.append(self._make_chunk(node, lines, file_path, ChunkType.MODULE))

        if not chunks:
            chunks.append(self._fallback_chunk(source, file_path))

        return chunks

    def _make_chunk(self, node: Node, lines: list[str], file_path: str, chunk_type: ChunkType) -> Chunk:
        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        content = "\n".join(lines[node.start_point[0]:node.end_point[0] + 1])
        chunk_id = Chunk.make_id(file_path, start_line, end_line, content)
        return Chunk(
            id=chunk_id,
            content=content,
            chunk_type=chunk_type,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
        )

    def _fallback_chunk(self, source: str, file_path: str) -> Chunk:
        lines = source.split("\n")
        content = source[:5000]
        chunk_id = Chunk.make_id(file_path, 1, len(lines), content)
        return Chunk(
            id=chunk_id,
            content=content,
            chunk_type=ChunkType.MODULE,
            file_path=file_path,
            start_line=1,
            end_line=len(lines),
        )

    def _extract_imports(self, source: str) -> list[str]:
        imports: list[str] = []
        try:
            tree = self._parser.parse(source.encode("utf-8"))
            for node in tree.root_node.children:
                if node.type == "import_statement":
                    for child in node.children:
                        if child.type == "dotted_name":
                            imports.append(child.text.decode("utf-8"))
                elif node.type == "import_from_statement":
                    module = node.child_by_field_name("module")
                    if module:
                        imports.append(module.text.decode("utf-8"))
        except Exception:
            pass
        return imports

    def _extract_calls_by_function(self, source: str) -> dict[str, set[str]]:
        calls_by_fn: dict[str, set[str]] = {}
        try:
            tree = self._parser.parse(source.encode("utf-8"))
            root = tree.root_node
            for node in root.children:
                fn_node = None
                if node.type in _FUNCTION_TYPES:
                    fn_node = node
                elif node.type in _DECORATED_TYPES:
                    defn = node.child_by_field_name("definition")
                    if defn and defn.type in _FUNCTION_TYPES:
                        fn_node = node

                if fn_node is None:
                    continue

                name_node = fn_node.child_by_field_name("name")
                if not name_node:
                    continue
                fn_name = name_node.text.decode("utf-8")
                callees = calls_by_fn.setdefault(fn_name, set())

                stack = [fn_node]
                while stack:
                    cur = stack.pop()
                    if cur.type in _CALL_TYPES:
                        func = cur.child_by_field_name("function")
                        if func:
                            raw = func.text.decode("utf-8")
                            # best-effort: foo(), obj.foo(), pkg.mod.foo()
                            name = raw.split(".")[-1]
                            if name and name.isidentifier():
                                callees.add(name)
                    stack.extend(reversed(cur.children))
        except Exception:
            return calls_by_fn
        return calls_by_fn
