"""Structured artifact parser and transactional executor.

Parses strict JSON payloads returned by AuraRouter when the intent is
actionable (``edit_code``, ``generate_code``) and applies the requested
file modifications to disk.  All operations are transactional — if any
single modification fails the entire batch is rolled back.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

log = structlog.get_logger()

# ------------------------------------------------------------------ #
# Data models
# ------------------------------------------------------------------ #

_REQUIRED_MOD_FIELDS = {"file_path", "modification_type", "content", "language"}


@dataclass(frozen=True)
class FileModification:
    """A single file modification from the router's structured response."""

    file_path: str
    modification_type: str  # "full_rewrite" | "unified_diff"
    content: str
    language: str


@dataclass(frozen=True)
class ArtifactPayload:
    """Parsed structured artifact response from AuraRouter."""

    modifications: list[FileModification]


@dataclass
class ExecutionResult:
    """Result of executing a single file modification."""

    file_path: str
    success: bool
    modification_type: str
    error: str | None = None
    strategy_used: str | None = None  # "strict" | "fuzzy" | None (for full_rewrite)


# ------------------------------------------------------------------ #
# Parser
# ------------------------------------------------------------------ #


def parse_artifact_payload(raw: str) -> ArtifactPayload | None:
    """Attempt to parse raw content as a structured artifact payload.

    Returns ``None`` if *raw* is not valid JSON or does not conform to
    the expected schema.  Does **not** raise on non-JSON content.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    mods_raw = data.get("modifications")
    if not isinstance(mods_raw, list):
        return None

    modifications: list[FileModification] = []
    for idx, entry in enumerate(mods_raw):
        if not isinstance(entry, dict):
            log.warning("artifact.skip_entry", index=idx, reason="not a dict")
            continue
        missing = _REQUIRED_MOD_FIELDS - entry.keys()
        if missing:
            log.warning("artifact.skip_entry", index=idx, missing=sorted(missing))
            continue
        modifications.append(
            FileModification(
                file_path=entry["file_path"],
                modification_type=entry["modification_type"],
                content=entry["content"],
                language=entry["language"],
            )
        )

    return ArtifactPayload(modifications=modifications)


# ------------------------------------------------------------------ #
# Unified-diff application helpers
# ------------------------------------------------------------------ #

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class _Hunk:
    """Parsed unified-diff hunk."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    context_before: list[str] = field(default_factory=list)


def _parse_hunks(diff_text: str) -> list[_Hunk]:
    """Extract hunks from a unified diff string."""
    hunks: list[_Hunk] = []
    current: _Hunk | None = None

    for line in diff_text.splitlines(keepends=True):
        stripped = line.rstrip("\n\r")

        # Skip file headers
        if stripped.startswith("---") or stripped.startswith("+++"):
            continue

        m = _HUNK_RE.match(stripped)
        if m:
            current = _Hunk(
                old_start=int(m.group(1)),
                old_count=int(m.group(2)) if m.group(2) is not None else 1,
                new_start=int(m.group(3)),
                new_count=int(m.group(4)) if m.group(4) is not None else 1,
            )
            hunks.append(current)
            continue

        if current is None:
            continue

        if stripped.startswith("-"):
            current.removed.append(stripped[1:])
        elif stripped.startswith("+"):
            current.added.append(stripped[1:])
        elif stripped.startswith(" "):
            # context line — track only before any removals/additions
            if not current.removed and not current.added:
                current.context_before.append(stripped[1:])

    return hunks


def _apply_strict(original: str, hunks: list[_Hunk]) -> str | None:
    """Apply hunks by line number (strict mode).

    Returns the patched text, or ``None`` if any hunk fails to match.
    """
    lines = original.splitlines(keepends=False)

    # Apply hunks in reverse order so earlier line numbers stay valid.
    for hunk in reversed(hunks):
        start = hunk.old_start - 1  # 0-based
        end = start + len(hunk.removed)

        if start < 0 or end > len(lines):
            return None

        # Verify the removed lines actually match.
        for i, expected in enumerate(hunk.removed):
            if start + i >= len(lines) or lines[start + i] != expected:
                return None

        lines[start:end] = hunk.added

    return "\n".join(lines) + ("\n" if original.endswith("\n") else "")


def _apply_fuzzy(original: str, hunks: list[_Hunk]) -> str | None:
    """Apply hunks via search-and-replace (fuzzy fallback).

    For each hunk, locate the removed block as a contiguous substring
    and replace it with the added block.  Returns ``None`` if any hunk
    cannot be matched.
    """
    result = original
    for hunk in hunks:
        if not hunk.removed and hunk.added:
            # Pure addition — not possible to locate by replacement;
            # fall back to appending after context if available.
            if hunk.context_before:
                anchor = "\n".join(hunk.context_before)
                addition = "\n".join(hunk.added)
                idx = result.find(anchor)
                if idx == -1:
                    return None
                insert_at = idx + len(anchor)
                result = result[:insert_at] + "\n" + addition + result[insert_at:]
            else:
                # No anchor — append at end.
                result = result + "\n".join(hunk.added) + "\n"
            continue

        old_block = "\n".join(hunk.removed)
        new_block = "\n".join(hunk.added)

        idx = result.find(old_block)
        if idx == -1:
            return None

        result = result[:idx] + new_block + result[idx + len(old_block) :]

    return result


# ------------------------------------------------------------------ #
# Transactional executor
# ------------------------------------------------------------------ #


@dataclass
class _Backup:
    """Pre-flight backup entry."""

    path: Path
    existed: bool
    original_content: str | None  # None when file did not exist


def execute_modifications(
    payload: ArtifactPayload,
    working_directory: str,
) -> list[ExecutionResult]:
    """Execute all file modifications transactionally.

    If **any** modification fails, every previously-applied change is
    rolled back — original files are restored and newly-created files
    are deleted.
    """
    work_dir = Path(working_directory).resolve()
    results: list[ExecutionResult] = []
    backups: list[_Backup] = []

    # --- Pre-flight: resolve paths and collect backups ---------------
    resolved_paths: list[Path | None] = []
    for mod in payload.modifications:
        target = (work_dir / mod.file_path).resolve()
        if not _is_within(target, work_dir):
            results.append(
                ExecutionResult(
                    file_path=mod.file_path,
                    success=False,
                    modification_type=mod.modification_type,
                    error="path traversal rejected",
                )
            )
            resolved_paths.append(None)
            continue

        existed = target.is_file()
        original = target.read_text(encoding="utf-8") if existed else None
        backups.append(_Backup(path=target, existed=existed, original_content=original))
        resolved_paths.append(target)
        results.append(
            ExecutionResult(
                file_path=mod.file_path,
                success=True,  # optimistic; updated below on failure
                modification_type=mod.modification_type,
            )
        )

    # Check if any path-validation failures already occurred.
    if any(not r.success for r in results):
        _rollback(backups, results)
        return results

    # --- Apply modifications -----------------------------------------
    backup_idx = 0
    for i, mod in enumerate(payload.modifications):
        target = resolved_paths[i]
        if target is None:
            continue  # already failed (path traversal)

        try:
            if mod.modification_type == "full_rewrite":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(mod.content, encoding="utf-8")
                results[i].strategy_used = None

            elif mod.modification_type == "unified_diff":
                if not target.is_file() and backups[backup_idx].original_content is None:
                    raise ValueError("cannot apply diff to non-existent file")

                original = backups[backup_idx].original_content or ""
                hunks = _parse_hunks(mod.content)
                if not hunks:
                    raise ValueError("no valid hunks found in diff")

                # Tier 1 — strict
                patched = _apply_strict(original, hunks)
                if patched is not None:
                    target.write_text(patched, encoding="utf-8")
                    results[i].strategy_used = "strict"
                else:
                    # Tier 2 — fuzzy
                    patched = _apply_fuzzy(original, hunks)
                    if patched is not None:
                        target.write_text(patched, encoding="utf-8")
                        results[i].strategy_used = "fuzzy"
                    else:
                        raise ValueError("diff application failed (strict and fuzzy)")

            else:
                raise ValueError(f"unknown modification_type: {mod.modification_type!r}")

        except Exception as exc:
            results[i].success = False
            results[i].error = str(exc)
            _rollback(backups, results)
            return results

        backup_idx += 1

    return results


def _is_within(child: Path, parent: Path) -> bool:
    """Return True if *child* is inside *parent* (both resolved)."""
    try:
        return child.is_relative_to(parent)
    except (TypeError, AttributeError):
        # Fallback for Python < 3.9
        return str(child).startswith(str(parent) + os.sep) or child == parent


def _rollback(backups: list[_Backup], results: list[ExecutionResult]) -> None:
    """Restore every backed-up file to its original state."""
    for backup in backups:
        try:
            if backup.existed:
                if backup.original_content is not None:
                    backup.path.write_text(backup.original_content, encoding="utf-8")
            else:
                # File was newly created — delete it.
                if backup.path.is_file():
                    backup.path.unlink()
        except OSError:
            log.error("artifact.rollback_failed", path=str(backup.path))
