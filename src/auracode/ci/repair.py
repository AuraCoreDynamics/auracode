"""Closed-loop autonomous repair engine with strict anti-gaming boundaries."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from auracode.ci.diagnostics import DiagnosticExtractor

_BANNED_SUPPRESSION_PATTERNS = [
    "# noqa",
    "# ruff: noqa",
    "# pragma: no cover",
    "#pragma warning disable",
    "# pragma warning disable",
    "[suppressmessage",
    "<nowarn>",
    "<warningsnotaserrors>",
    "<treatwarningsaserrors>false",
    "# type: ignore",
    "# nosec",
    "#nullable disable",
    "# nullable disable",
    "@pytest.mark.skip",
    "@pytest.mark.xfail",
    "pytest.skip(",
    "pytest.mark.xfail",
    "@unittest.skip",
    "[fact(skip",
    "[theory(skip",
    "[ignore",
]

_RESTRICTED_PATH_PATTERNS = [
    ".github/workflows",
    ".gitlab-ci.yml",
    "pyproject.toml",
    "ruff.toml",
    ".ruff.toml",
    "directory.build.props",
    "directory.build.targets",
    "directory.packages.props",
    ".editorconfig",
    ".pre-commit-config.yaml",
    "setup.cfg",
    "tox.ini",
    "conftest.py",
    "global.json",
    ".csproj",
]


class BannedSuppressionError(Exception):
    """Raised when an auto-repair attempt attempts to game verification via suppression."""


class OscillationDetectedError(Exception):
    """Raised when an auto-repair loop oscillates between alternating error states."""


class RepairEngine:
    """Orchestrates bounded, closed-loop code repair on isolated git worktrees."""

    def __init__(self, extractor: DiagnosticExtractor | None = None) -> None:
        self.extractor = extractor or DiagnosticExtractor()

    def validate_patch_hygiene(self, patch_diff: str) -> None:
        """Inspects diff to ensure no banned suppression hacks or workflow edits are introduced.

        Rules (A4.5):
        1. Scans ADDED lines only ('+' prefix, not '+++'). Removing suppressions is allowed.
        2. Detects and rejects forbidden paths.
        3. Rejects rename, delete, binary and mode-change hunks.
        """
        lines = patch_diff.splitlines()

        # Reject structural gaming hunks
        for line in lines:
            lower = line.lower().strip()
            if (
                lower.startswith("rename from ")
                or lower.startswith("rename to ")
                or lower.startswith("deleted file mode ")
                or lower.startswith("git binary patch")
                or lower.startswith("old mode ")
                or lower.startswith("new mode ")
            ):
                raise BannedSuppressionError(
                    f"Patch rejected: structural hunk '{line.strip()}' is forbidden."
                )

        # Suppression check: added lines ONLY
        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                line_lower = line[1:].lower()
                for pattern in _BANNED_SUPPRESSION_PATTERNS:
                    if pattern in line_lower:
                        raise BannedSuppressionError(
                            f"Patch rejected: introduces banned suppression token '{pattern}'"
                        )

        # Path check
        for line in lines:
            if line.startswith("+++ b/") or line.startswith("--- a/"):
                line_lower = line.lower()
                for restricted in _RESTRICTED_PATH_PATTERNS:
                    if restricted in line_lower:
                        raise BannedSuppressionError(
                            "Patch rejected: unauthorized modification of "
                            f"restricted path or CI workflow '{restricted}'"
                        )

    def run_deterministic_fixers(self, repo_path: Path | str) -> bool:
        """Runs fast deterministic code fixers inside the repository or isolated worktree.

        Detects modifications using git diff / status, not exit codes.
        """
        repo = Path(repo_path).resolve()

        # Python deterministic fixers
        if shutil.which("ruff"):
            try:
                subprocess.run(
                    ["ruff", "check", "--fix", "."],
                    cwd=repo,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                subprocess.run(
                    ["ruff", "format", "."],
                    cwd=repo,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:
                pass

        # C# deterministic fixers
        if shutil.which("dotnet") and any(repo.glob("*.sln*")):
            try:
                subprocess.run(
                    ["dotnet", "format"],
                    cwd=repo,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:
                pass

        # A4.2: Detect modifications via git diff, not exit codes
        try:
            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            return bool(status_proc.stdout.strip())
        except Exception:
            return False

    def create_isolated_worktree(
        self,
        repo_path: Path | str,
        commit_sha: str,
        worktree_dir: Path | str,
    ) -> str:
        """Creates an isolated git worktree without modifying the working directory or branch.

        Refuses if branch already exists; NEVER uses -B force reset.
        """
        repo = Path(repo_path).resolve()
        worktree = Path(worktree_dir).resolve()
        short_sha = commit_sha[:8] if len(commit_sha) >= 8 else commit_sha

        # Find unique, unused repair branch
        attempt = 1
        branch_name = f"auracode/repair/{short_sha}-{attempt}"
        while self._branch_exists(repo, branch_name):
            attempt += 1
            branch_name = f"auracode/repair/{short_sha}-{attempt}"

        res = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree), commit_sha],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Failed to create isolated repair worktree: {res.stderr.strip()}")

        return branch_name

    def cleanup_worktree(
        self,
        repo_path: Path | str,
        worktree_dir: Path | str,
        delete_branch: bool = False,
        branch_name: str | None = None,
    ) -> None:
        """Safely removes an isolated repair worktree and optionally removes its branch."""
        repo = Path(repo_path).resolve()
        worktree = Path(worktree_dir).resolve()

        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            cwd=repo,
            capture_output=True,
            check=False,
        )

        if delete_branch and branch_name:
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=repo,
                capture_output=True,
                check=False,
            )

    @staticmethod
    def _branch_exists(repo: Path, branch_name: str) -> bool:
        res = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"],
            cwd=repo,
            capture_output=True,
            check=False,
        )
        return res.returncode == 0

    def compute_commit_trailers(
        self,
        iteration: int,
        fencing_token: int,
        node_id: str,
        diagnostic: str = "",
        model: str = "auracode-repair-v1",
        prompt_sha256: str = "",
        attestation: str = "",
    ) -> str:
        """Constructs conventional git trailers recording autonomous repair provenance (A4.6)."""
        trailers = [
            f"Repair-Diagnostic: {diagnostic or 'auto-repair'}",
            f"Model: {model}",
            f"Prompt-Sha256: {prompt_sha256}",
            f"Verified-By: {node_id}",
            f"Repair-Attestation: {attestation}",
            f"Aura-Repair-Iteration: {iteration}",
            f"Aura-Repair-Fencing-Token: {fencing_token}",
            f"Aura-Repair-Node: {node_id}",
        ]
        return "\n".join(trailers)

    def verify_bounds(
        self,
        iteration: int,
        current_fingerprint: str,
        current_count: int,
        fingerprint_history: list[str],
        count_history: list[int],
        max_iterations: int = 3,
    ) -> None:
        """Verifies iteration limits, decreasing diagnostic counts, and oscillation absence."""
        if iteration > max_iterations:
            msg = f"Repair loop aborted: exceeded max iteration limit ({max_iterations})"
            raise ValueError(msg)

        if current_fingerprint in fingerprint_history:
            msg = f"Repair loop aborted: oscillation detected to state '{current_fingerprint}'"
            raise OscillationDetectedError(msg)

        if count_history and current_count >= count_history[-1]:
            msg = (
                "Repair loop aborted: count did not decrease "
                f"({current_count} >= {count_history[-1]})"
            )
            raise ValueError(msg)
