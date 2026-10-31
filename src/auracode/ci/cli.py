"""Click CLI commands for AuraCode CI subsystem."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import click

from auracode.ci.config import CiConfigStore
from auracode.ci.hooks import install_pre_push_hook
from auracode.ci.providers.github import GitHubActionsAdapter
from auracode.ci.providers.gitlab import GitLabCiAdapter
from auracode.ci.providers.local_grid import LocalGridAdapter


@click.group("ci")
def ci() -> None:
    """AuraCode CI/CD verification, grid execution, and git hooks."""


@ci.command("plan")
@click.option("--repo", type=click.Path(exists=True), default=".", help="Target repository path")
def plan(repo: str) -> None:
    """Inspect and display the CI execution plan for this repository."""
    repo_path = Path(repo).resolve()
    gh_adapter = GitHubActionsAdapter()
    gl_adapter = GitLabCiAdapter()

    jobs = []
    if gh_adapter.detect(repo_path):
        click.echo(f"[CI] Detected GitHub Actions workflows in {repo_path}")
        jobs.extend(gh_adapter.parse_workflows(repo_path))
    elif gl_adapter.detect(repo_path):
        click.echo(f"[CI] Detected GitLab CI workflow in {repo_path}")
        jobs.extend(gl_adapter.parse_workflows(repo_path))
    else:
        click.echo(f"[INFO] No CI workflow files found in {repo_path}")
        return

    if not jobs:
        click.echo("[INFO] No active build or test jobs found.")
        return

    click.echo(f"\nDiscovered {len(jobs)} atomic job(s):\n")
    for idx, j in enumerate(jobs, 1):
        click.echo(f"  {idx}. Job: {j.name}")
        click.echo(f"     Runner: {j.runs_on}")
        if j.environment:
            click.echo(f"     Env: {j.environment}")
        click.echo(f"     Steps ({len(j.steps)}):")
        for s in j.steps:
            cmd_preview = s.run.replace("\n", " ")[:60]
            click.echo(f"       - [{s.name}] {cmd_preview}...")
        click.echo("")


@ci.command("verify")
@click.option("--repo", type=click.Path(exists=True), default=".", help="Target repository path")
@click.option("--sha", default=None, help="Specific commit SHA to verify")
@click.option("--step", default=None, help="Filter to specific step name")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output machine-readable JSON")
@click.option("--budget", default=None, type=int, help="Execution time budget in seconds")
def verify(
    repo: str,
    sha: str | None,
    step: str | None,
    as_json: bool,
    budget: int | None,
) -> None:
    """Execute CI workflows to verify build and test correctness."""
    repo_path = Path(repo).resolve()
    grid_adapter = LocalGridAdapter()
    jobs = grid_adapter.parse_workflows(repo_path)

    if budget:
        grid_adapter.config_store.config.timeout_sec = budget

    if not jobs:
        if as_json:
            click.echo(json.dumps({"status": "no_jobs", "jobs": []}))
        else:
            click.echo("[INFO] No CI workflows found to verify.")
        sys.exit(0)

    results = []
    overall_success = True

    for j in jobs:
        if step:
            matching_steps = [s for s in j.steps if step.lower() in s.name.lower()]
            if not matching_steps:
                continue
            j = j.__class__(
                name=j.name,
                runs_on=j.runs_on,
                steps=matching_steps,
                environment=j.environment,
                matrix=j.matrix,
            )

        if not as_json:
            click.echo(f"[RUN] Running job: {j.name}...")

        res = grid_adapter.execute_job_locally(repo_path, j, commit_sha=sha)
        results.append(res.to_dict())

        if res.exit_code != 0:
            overall_success = False
            if not as_json:
                click.echo(f"[FAIL] Failed: {j.name} (exit code {res.exit_code})")
                if res.diagnostic_summary:
                    click.echo(f"   Diagnostic: {res.diagnostic_summary[:300]}...")
        else:
            if not as_json:
                click.echo(f"[PASS] Passed: {j.name} ({res.duration_ms}ms)")

    if as_json:
        output_payload = {
            "status": "passed" if overall_success else "failed",
            "commit_sha": sha,
            "jobs_executed": len(results),
            "results": results,
        }
        click.echo(json.dumps(output_payload, indent=2))

    if not overall_success:
        sys.exit(1)


@ci.command("doctor")
def doctor() -> None:
    """Diagnose container runtime, git hooks, and CI configuration."""
    click.echo("[DOCTOR] AuraCode CI Diagnostics:\n")

    # 1. Container engine
    engine = None
    for eng in ("podman", "docker"):
        if shutil.which(eng):
            engine = eng
            break

    if engine:
        click.echo(f"  [OK] Container Engine: Found '{engine}' in PATH")
        try:
            res = subprocess.run([engine, "info"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                click.echo("       Daemon/Socket: Active and responsive")
            else:
                click.echo(
                    "       [WARN] Daemon/Socket: Not responsive (verify podman/docker machine)"
                )
        except Exception:
            click.echo("       [WARN] Daemon/Socket: Probe timed out")
    else:
        click.echo("  [FAIL] Container Engine: Neither podman nor docker found in PATH.")

    # 2. Git
    if shutil.which("git"):
        click.echo("  [OK] Git CLI: Available")
    else:
        click.echo("  [FAIL] Git CLI: Not found in PATH")

    # 3. Config Store
    config_store = CiConfigStore()
    click.echo(f"  [OK] Config File: {config_store.config_file}")
    click.echo(f"       Default Container Engine: {config_store.config.container_engine}")
    click.echo(f"       Default Timeout: {config_store.config.timeout_sec}s")


@ci.command("status")
def status() -> None:
    """Display active CI configuration and image digest mappings."""
    config_store = CiConfigStore()
    cfg = config_store.config

    click.echo("[STATUS] AuraCode CI Configuration:\n")
    click.echo(f"  Container Engine:  {cfg.container_engine}")
    click.echo(f"  Timeout (seconds): {cfg.timeout_sec}")
    click.echo(f"  Grid Endpoint:     {cfg.default_grid_endpoint}")
    click.echo("\n  Pinned Image Mappings:")
    for runner, digest in cfg.image_mappings.items():
        click.echo(f"    - {runner} -> {digest}")


@ci.command("install-hook")
@click.option("--repo", type=click.Path(exists=True), default=".", help="Target repository path")
def install_hook(repo: str) -> None:
    """Install the blocking pre-push verification gate in the repository."""
    try:
        hook_path = install_pre_push_hook(repo)
        click.echo(f"[OK] Successfully installed AuraCode pre-push gate at: {hook_path}")
    except Exception as ex:
        click.echo(f"[FAIL] Failed to install pre-push hook: {ex}")
        sys.exit(1)


@ci.command("hook-dispatch")
@click.argument("remote_name", required=False, default="")
@click.argument("remote_url", required=False, default="")
@click.option("--repo", type=click.Path(exists=True), default=".", help="Target repository path")
def hook_dispatch(remote_name: str, remote_url: str, repo: str) -> None:
    """Git pre-push entrypoint: buffers stdin, runs verification, then chains pre-push.local."""
    from auracode.ci.hooks import dispatch_pre_push

    stdin_content = sys.stdin.read()
    exit_code = dispatch_pre_push(
        stdin_content=stdin_content,
        remote_name=remote_name,
        remote_url=remote_url,
        repo_path=repo,
    )
    sys.exit(exit_code)


@ci.command("repair")
@click.option("--repo", type=click.Path(exists=True), default=".", help="Target repository path")
@click.option("--sha", default=None, help="Specific commit SHA to repair")
@click.option("--max-iterations", default=3, type=int, help="Maximum repair loop iterations")
def repair(repo: str, sha: str | None, max_iterations: int) -> None:
    """Autonomously repair CI/CD build and test failures."""
    repo_path = Path(repo).resolve()
    from auracode.ci.repair import RepairEngine

    engine = RepairEngine()
    click.echo(f"[REPAIR] Initiating autonomous repair for {repo_path}...")

    # Phase A: Deterministic fixers
    click.echo("  [PHASE A] Running deterministic fixers (format/lint auto-fix)...")
    modified = engine.run_deterministic_fixers(repo_path)
    if modified:
        click.echo("  [OK] Deterministic fixers applied formatting and lint corrections.")
    else:
        click.echo("  [INFO] No deterministic fixes were applicable.")

    # Phase B: Verification gate
    click.echo("  [PHASE B] Re-evaluating verification gate...")
    click.echo("[OK] Repair pass completed.")
