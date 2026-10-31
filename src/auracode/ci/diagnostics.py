"""Untrusted CI diagnostic ingestion, categorization, and fingerprinting."""

from __future__ import annotations

import hashlib
import re

from auracode.ci.schemas import CiDiagnosticEntry

# Regex patterns for C# and Python compiler/linter diagnostics
_CS_ERROR_REGEX = re.compile(
    r"(?P<file>(?:[a-zA-Z]:[\\/])?[a-zA-Z0-9_\-\./\\]+\.(?:cs|csproj))"
    r"\((?P<line>\d+),\d+\):\s*(?P<category>error|warning)\s*"
    r"(?P<rule>CS\d+|NU\d+|MSB\d+):\s*(?P<msg>[^\r\n]+)"
)

_RUFF_ERROR_REGEX = re.compile(
    r"(?P<file>(?:[a-zA-Z]:[\\/])?[a-zA-Z0-9_\-\./\\]+\.py):"
    r"(?P<line>\d+):\d+:\s*(?P<rule>[A-Z]+\d+)\s*(?P<msg>[^\r\n]+)"
)

_PYTEST_FAILURE_REGEX = re.compile(
    r"FAILED\s+(?P<file>(?:[a-zA-Z]:[\\/])?[a-zA-Z0-9_\-\./\\]+)::(?P<msg>[a-zA-Z0-9_\-]+)"
)


class DiagnosticExtractor:
    """Extracts structured diagnostic entries from untrusted raw log strings."""

    def extract(self, log_content: str) -> list[CiDiagnosticEntry]:
        """Extracts and sanitizes error diagnostics from raw stdout/stderr."""
        if not log_content:
            return []

        entries: list[CiDiagnosticEntry] = []
        seen_keys: set[str] = set()

        for line in log_content.splitlines():
            # Sanitize untrusted line
            sanitized = line.strip()[:500]
            if not sanitized:
                continue

            # 1. Match C# compiler / NuGet diagnostics
            cs_match = _CS_ERROR_REGEX.search(sanitized)
            if cs_match:
                entry = CiDiagnosticEntry(
                    file=cs_match.group("file"),
                    line=int(cs_match.group("line")),
                    rule_id=cs_match.group("rule"),
                    message=cs_match.group("msg").strip(),
                    category=cs_match.group("category"),
                )
                key = f"{entry.file}:{entry.line}:{entry.rule_id}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    entries.append(entry)
                continue

            # 2. Match Ruff diagnostics
            ruff_match = _RUFF_ERROR_REGEX.search(sanitized)
            if ruff_match:
                entry = CiDiagnosticEntry(
                    file=ruff_match.group("file"),
                    line=int(ruff_match.group("line")),
                    rule_id=ruff_match.group("rule"),
                    message=ruff_match.group("msg").strip(),
                    category="error",
                )
                key = f"{entry.file}:{entry.line}:{entry.rule_id}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    entries.append(entry)
                continue

            # 3. Match Pytest test failure
            pytest_match = _PYTEST_FAILURE_REGEX.search(sanitized)
            if pytest_match:
                entry = CiDiagnosticEntry(
                    file=pytest_match.group("file"),
                    line=None,
                    rule_id="PYTEST_FAIL",
                    message=pytest_match.group("msg").strip(),
                    category="error",
                )
                key = f"{entry.file}:{entry.rule_id}:{entry.message}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    entries.append(entry)

        return entries

    @staticmethod
    def fingerprint(entries: list[CiDiagnosticEntry]) -> str:
        """Computes a deterministic hash fingerprint representing the set of diagnostics."""
        sorted_keys = sorted(
            f"{e.file or ''}:{e.line or 0}:{e.rule_id or ''}:{e.message}" for e in entries
        )
        payload = "|".join(sorted_keys).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]
