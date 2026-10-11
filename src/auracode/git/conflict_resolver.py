"""Git 3-way merge conflict parser and AI-driven semantic resolver."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from auracode.models.request import EngineRequest, RequestIntent
from auracode.routing.artifacts import parse_artifact_payload
from auracode.utils.journal import FileJournal

if TYPE_CHECKING:
    from auracode.engine.core import AuraCodeEngine

log = structlog.get_logger()

_CONFLICT_START_RE = re.compile(r"^<{7}\s*(.*)$")
_CONFLICT_BASE_RE = re.compile(r"^\|{7}\s*(.*)$")
_CONFLICT_MID_RE = re.compile(r"^={7}$")
_CONFLICT_END_RE = re.compile(r"^>{7}\s*(.*)$")

_DEFAULT_IGNORED = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
}


@dataclass(frozen=True)
class ConflictBlock:
    """Represents a single Git merge conflict block within a file."""

    start_line: int
    end_line: int
    ours_label: str
    ours_content: str
    theirs_label: str
    theirs_content: str
    base_content: str | None = None


class ConflictMarkerParser:
    """Parses standard Git conflict markers from text files."""

    @staticmethod
    def parse_text(text: str) -> list[ConflictBlock]:
        """Scan string content and extract all conflict blocks."""
        lines = text.splitlines(keepends=True)
        blocks: list[ConflictBlock] = []

        in_conflict = False
        in_base = False
        in_theirs = False

        start_line = 0
        ours_label = ""
        theirs_label = ""
        ours_lines: list[str] = []
        base_lines: list[str] = []
        theirs_lines: list[str] = []

        for idx, line in enumerate(lines, start=1):
            if not in_conflict:
                match_start = _CONFLICT_START_RE.match(line.rstrip("\r\n"))
                if match_start:
                    in_conflict = True
                    start_line = idx
                    ours_label = match_start.group(1).strip()
                    ours_lines.clear()
                    base_lines.clear()
                    theirs_lines.clear()
                    in_base = False
                    in_theirs = False
                continue

            match_base = _CONFLICT_BASE_RE.match(line.rstrip("\r\n"))
            if match_base and not in_theirs:
                in_base = True
                continue

            if _CONFLICT_MID_RE.match(line.rstrip("\r\n")):
                in_base = False
                in_theirs = True
                continue

            match_end = _CONFLICT_END_RE.match(line.rstrip("\r\n"))
            if match_end and in_theirs:
                theirs_label = match_end.group(1).strip()
                block = ConflictBlock(
                    start_line=start_line,
                    end_line=idx,
                    ours_label=ours_label,
                    ours_content="".join(ours_lines),
                    theirs_label=theirs_label,
                    theirs_content="".join(theirs_lines),
                    base_content="".join(base_lines) if base_lines else None,
                )
                blocks.append(block)
                in_conflict = False
                in_base = False
                in_theirs = False
                continue

            if in_theirs:
                theirs_lines.append(line)
            elif in_base:
                base_lines.append(line)
            else:
                ours_lines.append(line)

        return blocks

    @staticmethod
    def find_conflicted_files(root_dir: str = ".") -> list[Path]:
        """Search workspace for files containing Git conflict markers."""
        conflicted: list[Path] = []
        root_path = Path(root_dir).resolve()
        if not root_path.is_dir():
            return conflicted

        for p in root_path.rglob("*"):
            if any(part in _DEFAULT_IGNORED for part in p.parts):
                continue
            if p.is_file() and p.stat().st_size <= 1_000_000:
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    if "<<<<<<<" in content and "=======" in content and ">>>>>>>" in content:
                        conflicted.append(p)
                except OSError:
                    continue
        return sorted(conflicted)


class MergeConflictResolver:
    """Uses AuraCode engine to semantically resolve 3-way Git merge conflicts."""

    def __init__(self, engine: AuraCodeEngine, journal: FileJournal | None = None) -> None:
        self.engine = engine
        self.journal = journal or getattr(engine, "_journal", None) or FileJournal()

    async def resolve_file(self, target_path: Path | str) -> tuple[bool, str]:
        """Resolve all merge conflicts in a file transactionally.

        Args:
            target_path: Path to the conflicted file.

        Returns:
            Tuple of (success_boolean, status_message).
        """
        p = Path(target_path).resolve()
        if not p.is_file():
            return False, f"File does not exist: {target_path}"

        try:
            original_content = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return False, f"Could not read file: {exc}"

        blocks = ConflictMarkerParser.parse_text(original_content)
        if not blocks:
            return True, "No conflict markers detected in file."

        if hasattr(self.engine, "event_bus") and self.engine.event_bus:
            self.engine.event_bus.broadcast(
                "git.conflict_detected",
                {"file": str(p), "blocks": len(blocks)},
            )

        prompt = (
            f"Resolve the Git merge conflicts in `{p.name}`.\n\n"
            "Below is the complete file content including conflict markers "
            "(`<<<<<<<`, `=======`, `>>>>>>>`).\n"
            "Synthesize a clean, correct version reconciling both intents "
            "without any conflict markers.\n\n"
            f"```\n{original_content}\n```\n\n"
            "Respond with the complete resolved file content."
        )

        req = EngineRequest(
            request_id=f"conflict_res_{uuid.uuid4().hex[:8]}",
            intent=RequestIntent.EDIT_CODE,
            prompt=prompt,
            adapter_name="opencode",
        )

        resp = await self.engine.execute(req)
        if resp.error:
            return False, f"Engine execution error: {resp.error}"

        resolved_text = self._extract_resolved_content(resp.content, p.name)
        if not resolved_text:
            return False, "Failed to extract resolved file content from model response."

        # Verify no remaining conflict markers
        if any(marker in resolved_text for marker in ("<<<<<<<", "=======", ">>>>>>>")):
            return False, "Synthesized resolution still contained Git conflict markers."

        # Transactionally write and journal
        try:
            p.write_text(resolved_text, encoding="utf-8")
            self.journal.record(
                path=str(p),
                action="resolve_conflict",
                before_content=original_content,
                after_content=resolved_text,
                metadata={"resolved_blocks": len(blocks)},
            )
            log.info("conflict.resolved", file=str(p), blocks=len(blocks))
            if hasattr(self.engine, "event_bus") and self.engine.event_bus:
                self.engine.event_bus.broadcast(
                    "git.conflict_resolved",
                    {"file": str(p), "blocks": len(blocks)},
                )
            return True, f"Successfully resolved {len(blocks)} conflict block(s) in {p.name}."
        except OSError as exc:
            return False, f"Failed to write resolved file: {exc}"

    def _extract_resolved_content(self, raw_content: str, filename: str) -> str | None:
        """Extract clean file text from response, handling artifacts or markdown blocks."""
        payload = parse_artifact_payload(raw_content)
        if payload and payload.modifications:
            for mod in payload.modifications:
                if Path(mod.file_path).name == filename or mod.file_path == filename:
                    text = mod.content
                    return text if text.endswith("\n") else text + "\n"
            text = payload.modifications[0].content
            return text if text.endswith("\n") else text + "\n"

        text = raw_content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        if not text:
            return None
        return text if text.endswith("\n") else text + "\n"
