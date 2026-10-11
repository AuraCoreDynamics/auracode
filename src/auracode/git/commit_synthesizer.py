"""Conventional commit message synthesizer from staged Git diffs."""

from __future__ import annotations

import subprocess
import uuid
from typing import TYPE_CHECKING

import structlog

from auracode.models.request import EngineRequest, RequestIntent

if TYPE_CHECKING:
    from auracode.engine.core import AuraCodeEngine

log = structlog.get_logger()


class CommitSynthesizer:
    """Synthesizes conventional commit messages and commits staged changes."""

    def __init__(self, engine: AuraCodeEngine) -> None:
        self.engine = engine

    async def generate_commit_message(self, repo_path: str = ".") -> str:
        """Inspect git diff --staged and generate a Conventional Commit message.

        Args:
            repo_path: Path to the git repository.

        Returns:
            Formatted commit title and optional body.
        """
        try:
            proc = subprocess.run(
                ["git", "diff", "--staged"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff_text = proc.stdout.strip()
        except Exception as exc:
            return f"Error reading staged diff: {exc}"

        if not diff_text:
            return "Empty diff: no staged changes."

        prompt = (
            "Generate a concise, professional Conventional Commit message "
            "(format: `type(scope): subject` with optional body) for the following git diff.\n\n"
            "Rules:\n"
            "- Use standard types: feat, fix, docs, style, refactor, test, chore.\n"
            "- Keep the first line under 72 characters.\n"
            "- Return ONLY the commit message text, with no markdown fences or commentary.\n\n"
            f"```diff\n{diff_text[:3500]}\n```"
        )

        req = EngineRequest(
            request_id=f"commit_syn_{uuid.uuid4().hex[:8]}",
            intent=RequestIntent.GENERATE_CODE,
            prompt=prompt,
            adapter_name="opencode",
        )

        resp = await self.engine.execute(req)
        if resp.error:
            return f"Error generating commit message: {resp.error}"

        msg = resp.content.strip()
        if msg.startswith("```"):
            lines = msg.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            msg = "\n".join(lines).strip()

        return msg

    async def commit_staged(
        self,
        repo_path: str = ".",
        message: str | None = None,
        push: bool = False,
    ) -> tuple[bool, str]:
        """Commit staged changes using the synthesized or provided commit message."""
        commit_msg = message or await self.generate_commit_message(repo_path)
        if "Empty diff" in commit_msg or commit_msg.startswith("Error"):
            return False, commit_msg

        try:
            proc = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode != 0:
                return False, f"Git commit failed: {proc.stderr.strip()}"

            commit_output = proc.stdout.strip()

            if push:
                push_proc = subprocess.run(
                    ["git", "push"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if push_proc.returncode != 0:
                    return (
                        True,
                        f"Committed successfully, but push failed: {push_proc.stderr.strip()}",
                    )
                commit_output += f"\n{push_proc.stdout.strip()}"

            return True, commit_output
        except Exception as exc:
            return False, f"Exception during git commit: {exc}"
