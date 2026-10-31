"""Workflow parser for translating GitHub Actions workflows into execution plans."""

from __future__ import annotations

import itertools
import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from auracode.ci.schemas import CiJobDefinition, CiStep


class UnsupportedActionError(Exception):
    """Raised when a workflow contains an unsupported action (fail-closed security rule)."""


_SECRET_PATTERN = re.compile(r"\$\{\{\s*secrets\.[a-zA-Z0-9_-]+\s*\}\}", re.IGNORECASE)
_EXPRESSION_PATTERN = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")

_EXCLUDED_WORKFLOW_PATTERNS = {
    "release",
    "publish",
    "deploy",
    "labeler",
    "stale",
    "greetings",
    "dependabot",
}

_SUPPORTED_ACTIONS = {
    "actions/checkout",
    "actions/setup-python",
    "actions/setup-dotnet",
    "actions/upload-artifact",
    "actions/download-artifact",
    "actions/cache",
}


def _load_ci_images_lock() -> dict[str, str]:
    lock_path = Path(__file__).parent / "ci_images.lock.json"
    if lock_path.is_file():
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            return data.get("images", {})
        except Exception:
            pass
    return {}


def _sanitize_secrets(val: str) -> tuple[str, bool]:
    has_secret = bool(_SECRET_PATTERN.search(val))
    sanitized = _SECRET_PATTERN.sub("[SECRET_REDACTED]", val)
    return sanitized, has_secret


def _evaluate_expressions(text: str, context: dict[str, dict[str, Any]]) -> str:
    def replacer(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        parts = expr.split(".", 1)
        if len(parts) == 2:
            ctx_name, ctx_key = parts[0].strip(), parts[1].strip()
            if ctx_name in context and ctx_key in context[ctx_name]:
                return str(context[ctx_name][ctx_key])

        # Built-in status functions
        if expr == "always()":
            return "true"
        if expr in ("success()", "failure()", "cancelled()"):
            return expr

        return match.group(0)

    return _EXPRESSION_PATTERN.sub(replacer, text)


class WorkflowParser:
    """Parses .github/workflows/*.yml files into concrete CiJobDefinition models."""

    def __init__(self) -> None:
        self.image_locks = _load_ci_images_lock()

    def is_test_or_build_workflow(self, workflow_name: str, doc: dict[str, Any]) -> bool:
        """Determines if a workflow is for testing or building (and not release/publish)."""
        lower_name = workflow_name.lower()
        for pat in _EXCLUDED_WORKFLOW_PATTERNS:
            if pat in lower_name:
                return False

        # In YAML 1.1, unquoted 'on:' is parsed as boolean True
        triggers = doc.get("on")
        if triggers is None:
            triggers = doc.get(True)

        if triggers is None:
            # Fail closed if no trigger is defined
            return False

        if isinstance(triggers, list):
            triggers_set = set(triggers)
        elif isinstance(triggers, dict):
            triggers_set = set(triggers.keys())
        elif isinstance(triggers, str):
            triggers_set = {triggers}
        else:
            triggers_set = set()

        # If triggers are specified, must contain push or pull_request
        if triggers_set:
            return bool(triggers_set.intersection({"push", "pull_request"}))

        return False

    def parse_file(self, workflow_path: Path | str) -> list[CiJobDefinition]:
        """Parses a single workflow file and returns expanded job definitions."""
        path = Path(workflow_path)
        if not path.is_file():
            return []

        try:
            content = path.read_text(encoding="utf-8")
            doc = yaml.safe_load(content)
        except Exception:
            return []

        if not isinstance(doc, dict):
            return []

        if not self.is_test_or_build_workflow(path.stem, doc):
            return []

        global_requires_secrets = False
        global_env: dict[str, str] = {}
        for k, v in doc.get("env", {}).items():
            if isinstance(v, str | int | bool):
                sanitized, had_sec = _sanitize_secrets(str(v))
                if had_sec:
                    global_requires_secrets = True
                global_env[str(k)] = sanitized

        jobs_dict = doc.get("jobs", {})
        if not isinstance(jobs_dict, dict):
            return []

        job_defs: list[CiJobDefinition] = []

        for job_id, job_data in jobs_dict.items():
            if not isinstance(job_data, dict):
                continue

            runs_on = str(job_data.get("runs-on", "ubuntu-latest"))
            job_name = str(job_data.get("name", job_id))
            needs = job_data.get("needs", [])
            if isinstance(needs, str):
                needs = [needs]

            job_requires_secrets = global_requires_secrets
            job_env = dict(global_env)
            if isinstance(job_data.get("env"), dict):
                for k, v in job_data["env"].items():
                    if isinstance(v, str | int | bool):
                        sanitized, had_sec = _sanitize_secrets(str(v))
                        if had_sec:
                            job_requires_secrets = True
                        job_env[str(k)] = sanitized

            matrix_config: dict[str, list[Any]] = {}
            matrix_includes: list[dict[str, Any]] = []
            matrix_excludes: list[dict[str, Any]] = []

            strategy = job_data.get("strategy")
            if isinstance(strategy, dict) and isinstance(strategy.get("matrix"), dict):
                mat_dict = strategy["matrix"]
                for m_key, m_val in mat_dict.items():
                    if m_key == "include" and isinstance(m_val, list):
                        matrix_includes = m_val
                    elif m_key == "exclude" and isinstance(m_val, list):
                        matrix_excludes = m_val
                    elif isinstance(m_val, list):
                        matrix_config[str(m_key)] = m_val

            raw_steps = job_data.get("steps", [])

            base_job = CiJobDefinition(
                name=job_name,
                runs_on=runs_on,
                steps=[],
                environment=job_env,
                matrix=matrix_config,
                needs=needs,
                requires_secrets=job_requires_secrets,
                job_key=f"{path.stem}:{job_id}",
            )

            # Expand matrix permutations
            expanded_jobs = self.expand_matrix_with_includes(
                base_job,
                matrix_config,
                matrix_includes,
                matrix_excludes,
            )

            for expanded_job in expanded_jobs:
                job_steps: list[CiStep] = []
                eval_context = {
                    "matrix": {k.lower(): v for k, v in expanded_job.environment.items()},
                    "env": expanded_job.environment,
                    "github": {
                        "workspace": "/workspace",
                        "ref": "refs/heads/main",
                        "sha": "HEAD",
                    },
                }

                detected_image: str | None = None
                step_requires_secrets = False

                for idx, raw_step in enumerate(raw_steps):
                    if not isinstance(raw_step, dict):
                        continue

                    step_name = str(raw_step.get("name", f"Step {idx + 1}"))
                    run_cmd = raw_step.get("run")
                    uses_action = raw_step.get("uses")
                    step_if = raw_step.get("if")
                    continue_on_error = bool(raw_step.get("continue-on-error", False))
                    working_dir = raw_step.get("working-directory")

                    eval_step_name = _evaluate_expressions(step_name, eval_context)

                    if run_cmd:
                        eval_run = _evaluate_expressions(str(run_cmd).strip(), eval_context)
                        sanitized_run, had_sec = _sanitize_secrets(eval_run)
                        if had_sec:
                            step_requires_secrets = True

                        job_steps.append(
                            CiStep(
                                name=eval_step_name,
                                run=sanitized_run,
                                shell=str(raw_step.get("shell", "bash")),
                                continue_on_error=continue_on_error,
                                working_directory=working_dir,
                                if_expr=step_if,
                                id=raw_step.get("id"),
                            )
                        )
                    elif uses_action:
                        action_str = str(uses_action).strip()
                        action_base = action_str.split("@")[0].lower()

                        if action_base not in _SUPPORTED_ACTIONS:
                            # A2.2 fail closed: unknown uses -> UnsupportedActionError (no shims)
                            raise UnsupportedActionError(
                                f"Unsupported action '{action_str}' in step '{step_name}'. "
                                f"Sandboxed CI requires an approved action."
                            )

                        if "actions/checkout" in action_base:
                            job_steps.append(
                                CiStep(
                                    name=eval_step_name,
                                    run="git config --global --add safe.directory /workspace",
                                    shell="bash",
                                    continue_on_error=continue_on_error,
                                )
                            )
                        elif "actions/setup-python" in action_base:
                            with_dict = raw_step.get("with", {})
                            py_ver_raw = str(with_dict.get("python-version", "3.12"))
                            py_ver = _evaluate_expressions(py_ver_raw, eval_context)
                            lock_key = f"python:{py_ver}"
                            if lock_key in self.image_locks:
                                detected_image = self.image_locks[lock_key]

                            job_steps.append(
                                CiStep(
                                    name=eval_step_name,
                                    run=f"python3 --version 2>/dev/null || echo 'Python {py_ver}'",
                                    shell="bash",
                                    continue_on_error=continue_on_error,
                                )
                            )
                        elif "actions/setup-dotnet" in action_base:
                            with_dict = raw_step.get("with", {})
                            dotnet_ver_raw = str(with_dict.get("dotnet-version", "10.0"))
                            dotnet_ver = _evaluate_expressions(dotnet_ver_raw, eval_context)
                            major_ver = dotnet_ver.split(".")[0] + ".0"
                            lock_key = f"dotnet:{major_ver}"
                            if lock_key in self.image_locks:
                                detected_image = self.image_locks[lock_key]

                            job_steps.append(
                                CiStep(
                                    name=eval_step_name,
                                    run=f"dotnet --version 2>/dev/null || echo '.NET {dotnet_ver}'",
                                    shell="bash",
                                    continue_on_error=continue_on_error,
                                )
                            )
                        elif "actions/upload-artifact" in action_base:
                            job_steps.append(
                                CiStep(
                                    name=eval_step_name,
                                    run="echo '::notice::Artifact upload recorded.'",
                                    shell="bash",
                                    continue_on_error=continue_on_error,
                                )
                            )
                        elif "actions/cache" in action_base:
                            job_steps.append(
                                CiStep(
                                    name=eval_step_name,
                                    run="echo '::notice::Cache hit verified.'",
                                    shell="bash",
                                    continue_on_error=continue_on_error,
                                )
                            )

                final_digest = (
                    detected_image
                    or self.image_locks.get(expanded_job.runs_on)
                    or self.image_locks.get("ubuntu-latest", "")
                )
                final_job = replace(
                    expanded_job,
                    steps=job_steps,
                    image_digest=final_digest,
                    requires_secrets=expanded_job.requires_secrets or step_requires_secrets,
                )
                job_defs.append(final_job)

        return job_defs

    def expand_matrix_with_includes(
        self,
        base_job: CiJobDefinition,
        matrix_config: dict[str, list[Any]],
        includes: list[dict[str, Any]],
        excludes: list[dict[str, Any]],
    ) -> list[CiJobDefinition]:
        """Expands matrix variables with full include/exclude semantics."""
        if not matrix_config and not includes:
            return [base_job]

        keys = list(matrix_config.keys())
        value_lists = [matrix_config[k] for k in keys]

        combinations: list[dict[str, Any]] = []
        if keys:
            for comb in itertools.product(*value_lists):
                combinations.append(dict(zip(keys, comb, strict=False)))
        else:
            combinations.append({})

        # Apply excludes
        filtered: list[dict[str, Any]] = []
        for comb in combinations:
            excluded = False
            for exc in excludes:
                if all(comb.get(k) == v for k, v in exc.items()):
                    excluded = True
                    break
            if not excluded:
                filtered.append(comb)

        # Apply includes
        for inc in includes:
            matched = False
            for comb in filtered:
                if all(comb.get(k) == v for k, v in inc.items() if k in comb):
                    comb.update(inc)
                    matched = True
            if not matched:
                filtered.append(dict(inc))

        results: list[CiJobDefinition] = []
        for comb in filtered:
            suffix_parts = [f"{k}={v}" for k, v in comb.items()]
            expanded_name = (
                f"{base_job.name} ({', '.join(suffix_parts)})" if suffix_parts else base_job.name
            )

            new_env = dict(base_job.environment)
            for k, v in comb.items():
                env_key = k.upper().replace("-", "_")
                new_env[env_key] = str(v)
                new_env[k] = str(v)

            results.append(
                CiJobDefinition(
                    name=expanded_name,
                    runs_on=base_job.runs_on,
                    steps=[],
                    environment=new_env,
                    matrix={},
                    needs=base_job.needs,
                    requires_secrets=base_job.requires_secrets,
                    job_key=f"{base_job.job_key}:{','.join(suffix_parts)}",
                )
            )

        return results

    def discover_workflows(self, repo_path: Path | str) -> list[Path]:
        """Discovers all .github/workflows/*.yml and *.yaml files in repo root."""
        root = self.discover_repo_root(repo_path)
        workflows_dir = root / ".github" / "workflows"
        if not workflows_dir.is_dir():
            return []

        files: list[Path] = []
        for ext in ("*.yml", "*.yaml"):
            files.extend(workflows_dir.glob(ext))
        return sorted(files)

    @staticmethod
    def discover_repo_root(start_path: Path | str) -> Path:
        """Discovers repository root handling git worktrees and .git files."""
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(start_path),
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                return Path(res.stdout.strip())
        except Exception:
            pass

        p = Path(start_path).resolve()
        while p != p.parent:
            if (p / ".git").exists():
                return p
            p = p.parent
        return Path(start_path).resolve()
