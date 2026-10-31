"""GitLab CI Provider Adapter."""

from __future__ import annotations

from pathlib import Path

import yaml

from auracode.ci.providers.base import BaseCiAdapter
from auracode.ci.schemas import CiJobDefinition, CiStep


class GitLabCiAdapter(BaseCiAdapter):
    """Adapter for GitLab CI configurations (.gitlab-ci.yml)."""

    @property
    def name(self) -> str:
        return "gitlab-ci"

    def detect(self, repo_path: str | Path) -> bool:
        repo = Path(repo_path)
        return (repo / ".gitlab-ci.yml").is_file()

    def parse_workflows(self, repo_path: str | Path) -> list[CiJobDefinition]:
        repo = Path(repo_path)
        ci_file = repo / ".gitlab-ci.yml"
        if not ci_file.is_file():
            return []

        try:
            content = ci_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except Exception:
            return []

        if not isinstance(data, dict):
            return []

        job_defs: list[CiJobDefinition] = []
        global_image = str(data.get("image", "ubuntu-latest"))

        for key, val in data.items():
            if key in ("stages", "variables", "default", "include") or key.startswith("."):
                continue

            if isinstance(val, dict) and "script" in val:
                raw_scripts = val["script"]
                if isinstance(raw_scripts, str):
                    script_lines = [raw_scripts]
                elif isinstance(raw_scripts, list):
                    script_lines = [str(line) for line in raw_scripts]
                else:
                    script_lines = []

                steps = [
                    CiStep(
                        name=f"{key}-step-{idx + 1}",
                        run=line,
                        shell="bash",
                    )
                    for idx, line in enumerate(script_lines)
                ]

                job_defs.append(
                    CiJobDefinition(
                        name=key,
                        runs_on=str(val.get("image", global_image)),
                        steps=steps,
                        environment={},
                        matrix={},
                    )
                )

        return job_defs
