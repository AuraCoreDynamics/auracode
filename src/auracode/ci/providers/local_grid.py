"""Local and AuraGrid CI Runner Adapter."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from auracode.ci.config import CiConfigStore
from auracode.ci.hooks import find_shell
from auracode.ci.parser import WorkflowParser
from auracode.ci.providers.base import BaseCiAdapter
from auracode.ci.schemas import (
    CiExecutionMode,
    CiJobDefinition,
    CiStepResult,
    CiTaskResult,
    CiTaskStatus,
)
from auracode.ci.signer import canonicalize_payload, generate_key_pair, sign_payload


def _load_sandbox_profile() -> dict:
    profile_path = Path(__file__).parent.parent / "ci-sandbox-profile.v1.json"
    if profile_path.is_file():
        try:
            return json.loads(profile_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


class LocalGridAdapter(BaseCiAdapter):
    """Executes CI workflows locally via sandboxed OCI container."""

    def __init__(
        self,
        config_store: CiConfigStore | None = None,
        parser: WorkflowParser | None = None,
    ) -> None:
        self.config_store = config_store or CiConfigStore()
        self.parser = parser or WorkflowParser()
        self.profile = _load_sandbox_profile()
        self._pub_key, self._priv_key = generate_key_pair()

    @property
    def name(self) -> str:
        return "local-grid"

    @property
    def public_key_hex(self) -> str:
        return self._pub_key

    def detect(self, repo_path: str | Path) -> bool:
        repo = Path(repo_path)
        wf_dir = repo / ".github" / "workflows"
        return wf_dir.is_dir() or (repo / ".gitlab-ci.yml").is_file()

    def parse_workflows(self, repo_path: str | Path) -> list[CiJobDefinition]:
        repo = Path(repo_path)
        files = self.parser.discover_workflows(repo)
        all_jobs: list[CiJobDefinition] = []
        for file in files:
            all_jobs.extend(self.parser.parse_file(file))
        return all_jobs

    def detect_container_engine(self) -> str | None:
        """Detects if podman or docker is installed and in PATH."""
        for engine in ("podman", "docker"):
            if shutil.which(engine):
                return engine
        return None

    def is_container_engine_live(self, engine: str | None) -> bool:
        """Verifies if container engine daemon/machine is actually responsive."""
        if not engine or not shutil.which(engine):
            return False
        try:
            res = subprocess.run([engine, "info"], capture_output=True, timeout=3, check=False)
            return res.returncode == 0
        except Exception:
            return False

    def execute_job_locally(
        self,
        repo_path: str | Path,
        job: CiJobDefinition,
        commit_sha: str | None = None,
    ) -> CiTaskResult:
        """Executes a parsed job definition inside a sandboxed container."""
        repo = Path(repo_path).resolve()
        start_time = time.time()
        engine = self.detect_container_engine() or "podman"

        # Resolve image digest from job or config mappings
        image_digest = job.image_digest or self.config_store.config.image_mappings.get(
            job.runs_on,
            self.config_store.config.image_mappings.get("ubuntu-latest", "ubuntu:24.04"),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir) / "workspace"
            work_dir.mkdir(parents=True, exist_ok=True)

            # Materialize workspace from git commit or copy safely
            has_worktree = False
            if commit_sha and (repo / ".git").exists():
                try:
                    wt_res = subprocess.run(
                        ["git", "worktree", "add", "--detach", str(work_dir), commit_sha],
                        cwd=str(repo),
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    has_worktree = wt_res.returncode == 0
                except Exception:
                    has_worktree = False

            if not has_worktree:
                # Fallback to copy repository files into temporary work directory
                shutil.copytree(
                    repo,
                    work_dir,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "obj", "bin", ".venv"),
                )

            # Create entrypoint shell script with step markers and strict Unix LF line endings
            auragrid_dir = work_dir / ".auragrid"
            auragrid_dir.mkdir(parents=True, exist_ok=True)
            script_file = auragrid_dir / "entrypoint.sh"

            script_lines = [
                "#!/bin/bash",
                "set -u",
                "mkdir -p /home/ci/.dotnet /home/ci/.cache/pip /home/ci/.nuget/packages "
                "2>/dev/null || true",
                "cd /workspace",
                "",
            ]

            step_name_map: dict[str, str] = {}
            for idx, step in enumerate(job.steps):
                step_name = step.name or f"step_{idx}"
                safe_name = step_name.replace(":", "_").replace("\n", " ").replace('"', '\\"')
                step_name_map[safe_name] = step.name or step_name
                script_lines.append(f"echo '::step-start::{safe_name}'")
                script_lines.append(
                    "_step_start=$(date +%s%3N 2>/dev/null || "
                    "python3 -c 'import time; print(int(time.time()*1000))' 2>/dev/null || "
                    "date +%s)"
                )
                script_lines.append("(")
                if step.working_directory:
                    script_lines.append(f"  cd {step.working_directory} && \\")
                script_lines.append(f"  {step.run}")
                script_lines.append(")")
                script_lines.append("_step_exit=$?")
                script_lines.append(
                    "_step_end=$(date +%s%3N 2>/dev/null || "
                    "python3 -c 'import time; print(int(time.time()*1000))' 2>/dev/null || "
                    "date +%s)"
                )
                script_lines.append("_step_dur=$(( _step_end - _step_start ))")
                script_lines.append(f'echo "::step-exit::{safe_name}:$_step_exit:$_step_dur"')
                if not step.continue_on_error:
                    script_lines.append("if [ $_step_exit -ne 0 ]; then")
                    script_lines.append("  exit $_step_exit")
                    script_lines.append("fi")
                script_lines.append("")

            script_content = "\n".join(script_lines) + "\n"
            script_file.write_bytes(script_content.encode("utf-8"))

            pids_limit = self.profile.get("pidsLimit", 512)
            nofile_limit = self.profile.get("nofileLimit", 4096)
            default_net = self.profile.get("defaultNetwork", "none")
            default_user = self.profile.get("defaultUser", "1000:1000")

            cmd = [
                engine,
                "run",
                "--rm",
                "--init",
                f"--pids-limit={pids_limit}",
                f"--ulimit=nofile={nofile_limit}:{nofile_limit}",
                "--memory=2048m",
                "--memory-swap=2048m",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--read-only",
                f"--network={default_net}",
                "--tmpfs",
                "/tmp:size=1g,mode=1777",
                "--tmpfs",
                "/home/ci:size=2g,mode=0700",
                "--user",
                default_user,
                "--label",
                "auragrid.ci=1",
                "-v",
                f"{work_dir}:/workspace:rw",
            ]

            if engine == "podman":
                cmd.append("--userns=keep-id")

            # Environment from profile
            profile_env = self.profile.get("env", {})
            for k, v in profile_env.items():
                cmd.extend(["-e", f"{k}={v}"])

            # Environment from job
            for k, v in job.environment.items():
                cmd.extend(["-e", f"{k}={v}"])

            cmd.extend([image_digest, "bash", "/workspace/.auragrid/entrypoint.sh"])

            stdout_data = ""
            exit_code = 0
            failed_step: str | None = None
            step_results: list[CiStepResult] = []

            try:
                is_live = self.is_container_engine_live(engine)
                if is_live and engine:
                    proc = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=self.config_store.config.timeout_sec,
                    )
                else:
                    sh_bin = find_shell() or "bash"
                    env_vars = dict(os.environ)
                    env_vars.update(self.profile.get("env", {}))
                    env_vars.update(job.environment)
                    env_vars["CI"] = "true"
                    env_vars["AURA_GRID_JOB_ID"] = job.name
                    target_script = script_file.relative_to(work_dir).as_posix()
                    proc = subprocess.run(
                        [sh_bin, target_script],
                        cwd=str(work_dir),
                        capture_output=True,
                        text=True,
                        env=env_vars,
                        check=False,
                        timeout=self.config_store.config.timeout_sec,
                    )
                stdout_data = proc.stdout + "\n" + proc.stderr
                exit_code = proc.returncode

                # Parse step exit markers
                for line in stdout_data.splitlines():
                    if line.startswith("::step-exit::"):
                        parts = line[len("::step-exit::") :].rsplit(":", 2)
                        if len(parts) == 3:
                            s_name, s_code_str, s_dur_str = parts[0], parts[1], parts[2]
                            try:
                                s_code = int(s_code_str)
                                s_dur = int(s_dur_str)
                                resolved_name = step_name_map.get(s_name, s_name)
                                step_results.append(
                                    CiStepResult(
                                        name=resolved_name,
                                        exit_code=s_code,
                                        duration_ms=s_dur,
                                    )
                                )
                                if s_code != 0 and failed_step is None:
                                    failed_step = resolved_name
                                    exit_code = s_code
                            except ValueError:
                                pass

                if exit_code != 0 and failed_step is None:
                    failed_step = "ExecutionFailed"
            except subprocess.TimeoutExpired:
                exit_code = 124
                failed_step = "Timeout"
                stdout_data = f"Job timed out after {self.config_store.config.timeout_sec}s."
            except Exception as ex:
                exit_code = 1
                failed_step = "LaunchError"
                stdout_data = str(ex)
            finally:
                if has_worktree:
                    try:
                        subprocess.run(
                            ["git", "worktree", "remove", "--force", str(work_dir)],
                            cwd=str(repo),
                            capture_output=True,
                            check=False,
                        )
                    except Exception:
                        pass

            duration_ms = int((time.time() - start_time) * 1000)
            stdout_sha = hashlib.sha256(stdout_data.encode("utf-8")).hexdigest()

            status = CiTaskStatus.PASSED if exit_code == 0 else CiTaskStatus.FAILED

            canonical = canonicalize_payload(
                job_id=job.name,
                idempotency_key=f"local-{job.name}",
                tree_hash=commit_sha,
                image_digest=image_digest,
                status=status,
                exit_code=exit_code,
                fencing_token=1,
                stdout_sha256=stdout_sha,
            )
            node_sig = sign_payload(canonical, self._priv_key)

            return CiTaskResult(
                job_id=job.name,
                status=status,
                exit_code=exit_code,
                execution_mode=CiExecutionMode.WRAPPED_CONTAINER,
                duration_ms=duration_ms,
                fencing_token=1,
                node_id="local",
                node_signature=node_sig,
                stdout_sha256=stdout_sha,
                failed_step_name=failed_step,
                diagnostic_summary=stdout_data[:1000] if exit_code != 0 else None,
                step_results=step_results,
                tree_hash=commit_sha,
                image_digest=image_digest,
                idempotency_key=f"local-{job.name}",
            )
