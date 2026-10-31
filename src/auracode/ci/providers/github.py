"""GitHub Actions CI Provider Adapter."""

from __future__ import annotations

from pathlib import Path

from auracode.ci.parser import WorkflowParser
from auracode.ci.providers.base import BaseCiAdapter
from auracode.ci.schemas import CiJobDefinition


class GitHubActionsAdapter(BaseCiAdapter):
    """Adapter for GitHub Actions workflows (.github/workflows/*.yml)."""

    def __init__(self, parser: WorkflowParser | None = None) -> None:
        self.parser = parser or WorkflowParser()

    @property
    def name(self) -> str:
        return "github-actions"

    def detect(self, repo_path: str | Path) -> bool:
        repo = Path(repo_path)
        wf_dir = repo / ".github" / "workflows"
        if not wf_dir.is_dir():
            return False
        return any(wf_dir.glob("*.yml")) or any(wf_dir.glob("*.yaml"))

    def parse_workflows(self, repo_path: str | Path) -> list[CiJobDefinition]:
        repo = Path(repo_path)
        files = self.parser.discover_workflows(repo)
        all_jobs: list[CiJobDefinition] = []
        for file in files:
            jobs = self.parser.parse_file(file)
            all_jobs.extend(jobs)
        return all_jobs
