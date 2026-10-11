"""Deterministic zero-vector AST repository map generator."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import structlog

log = structlog.get_logger()

_DEFAULT_IGNORED_DIRS = {
    ".git",
    ".ruff_cache",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".claude",
    ".benchmarks",
}

_PRIORITY_FILENAMES = {
    "__init__.py",
    "app.py",
    "main.py",
    "cli.py",
    "core.py",
    "server.py",
    "index.ts",
    "Program.cs",
}


class RepoMapBuilder:
    """Builds a compact structural AST map of a repository without neural embeddings."""

    def __init__(self, root_dir: str = ".", max_chars: int = 2048) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.max_chars = max_chars

    def build(self) -> str:
        """Scan workspace and generate an indented symbol outline.

        Returns:
            Concise text map of classes, methods, and functions capped at max_chars.
        """
        files = self._collect_source_files()
        lines: list[str] = ["[Codebase Architecture Map]"]
        total_symbols = 0

        for file_path in files:
            rel_path = file_path.relative_to(self.root_dir).as_posix()
            symbols = self._extract_symbols(file_path)
            if not symbols:
                continue

            total_symbols += len(symbols)
            lines.append(f"{rel_path}:")
            for sym in symbols:
                lines.append(f"  {sym}")

        rendered = "\n".join(lines)
        if len(rendered) > self.max_chars:
            suffix = (
                "\n... [truncated. Connect AuraXLM on AuraGrid for full-codebase neural indexing.]"
            )
            max_head = max(0, self.max_chars - len(suffix))
            cutoff = rendered[:max_head].rfind("\n")
            if cutoff > 0:
                rendered = rendered[:cutoff] + suffix
            else:
                rendered = rendered[:max_head] + suffix

        return rendered

    def count_symbols(self) -> tuple[int, int]:
        """Return (file_count, symbol_count) discovered in the workspace."""
        files = self._collect_source_files()
        symbol_count = 0
        file_count = 0
        for f in files:
            syms = self._extract_symbols(f)
            if syms:
                file_count += 1
                symbol_count += len(syms)
        return file_count, symbol_count

    def _collect_source_files(self) -> list[Path]:
        """Find source code files respecting ignore patterns and priorities."""
        discovered: list[Path] = []
        if not self.root_dir.is_dir():
            return discovered

        for path in self.root_dir.rglob("*"):
            if any(part in _DEFAULT_IGNORED_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in {".py", ".cs", ".ts", ".js", ".rs", ".go"}:
                if path.stat().st_size <= 500_000:  # Skip files > 500KB
                    discovered.append(path)

        def _sort_key(p: Path) -> tuple[int, str]:
            priority = 0 if p.name in _PRIORITY_FILENAMES else 1
            return priority, p.as_posix()

        discovered.sort(key=_sort_key)
        return discovered

    def _extract_symbols(self, file_path: Path) -> list[str]:
        """Extract function and class signatures from a source file."""
        if file_path.suffix == ".py":
            return self._extract_python_symbols(file_path)
        return self._extract_regex_symbols(file_path)

    def _extract_python_symbols(self, file_path: Path) -> list[str]:
        symbols: list[str] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError, OSError):
            return symbols

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases = [self._format_node_expr(b) for b in node.bases]
                base_str = f"({', '.join(bases)})" if bases else ""
                symbols.append(f"class {node.name}{base_str}")
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                        prefix = "async def" if isinstance(sub, ast.AsyncFunctionDef) else "def"
                        args = [a.arg for a in sub.args.args if a.arg != "self"]
                        arg_str = ", ".join(args[:4])
                        if len(sub.args.args) > 5:
                            arg_str += ", ..."
                        symbols.append(f"  {prefix} {sub.name}({arg_str})")
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                args = [a.arg for a in node.args.args]
                arg_str = ", ".join(args[:4])
                if len(node.args.args) > 4:
                    arg_str += ", ..."
                symbols.append(f"{prefix} {node.name}({arg_str})")

        return symbols

    def _extract_regex_symbols(self, file_path: Path) -> list[str]:
        symbols: list[str] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return symbols

        # Match class/interface and function headers across C#, TS, Go, Rust
        pattern = re.compile(
            r"^\s*(public|private|protected|export|fn)?\s*"
            r"(class|interface|struct|enum|def|func|fn)\s+([A-Za-z0-9_]+)",
            re.MULTILINE,
        )
        for match in pattern.finditer(content):
            kind = match.group(2)
            name = match.group(3)
            symbols.append(f"{kind} {name}")
            if len(symbols) >= 12:
                break
        return symbols

    def _format_node_expr(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._format_node_expr(node.value)}.{node.attr}"
        return ""
