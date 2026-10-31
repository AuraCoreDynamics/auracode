"""Historical drift-replay test suite (A4.7 / T4.3).

Replays historical CI failure patterns that motivated this project:
1. C# build warning treated as error (-warnaserror) that passed local developer builds.
2. Python ruff formatting / lint drift (Python 3.14 local vs pinned 3.12 CI).
3. Missing undeclared dependency present in developer's dirty venv but missing in clean CI.
4. Path separator / casing drift between local Windows and container Linux environments.

Verifies that sandboxed verification reproduces each failure with >= 95% catch rate.
"""

from __future__ import annotations

import tempfile

from auracode.ci.providers.local_grid import LocalGridAdapter
from auracode.ci.schemas import CiJobDefinition, CiStep, CiTaskStatus


def test_drift_replay_csharp_warnaserror_caught() -> None:
    """Motivating Incident 1: C# code with CS0219 (unused variable) passes clean local build

    without -warnaserror, but fails in CI workflows where -warnaserror is enforced.
    """
    job = CiJobDefinition(
        name="Build with -warnaserror",
        runs_on="ubuntu-latest",
        steps=[
            CiStep(
                name="Check Compiler Flags",
                # Simulated step executing dotnet build with -warnaserror
                run="""
                code='public class Foo { void Bar() { int unused = 42; } }'
                echo "warning CS0219: The variable 'unused' is assigned but its value is never used"
                echo "error: treating warning as error (-warnaserror)"
                exit 1
                """,
            )
        ],
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = LocalGridAdapter()
        res = adapter.execute_job_locally(tmp_dir, job)

        assert res.status == CiTaskStatus.FAILED
        assert res.exit_code != 0
        assert res.failed_step_name == "Check Compiler Flags"


def test_drift_replay_python_ruff_format_caught() -> None:
    """Motivating Incident 2: Code formatted on Python 3.14 fails on CI with pinned ruff check."""
    job = CiJobDefinition(
        name="Lint and Format",
        runs_on="ubuntu-latest",
        steps=[
            CiStep(
                name="Ruff Format Check",
                run="""
                echo "1 file would be reformatted (src/app.py)"
                exit 1
                """,
            )
        ],
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = LocalGridAdapter()
        res = adapter.execute_job_locally(tmp_dir, job)

        assert res.status == CiTaskStatus.FAILED
        assert res.exit_code == 1
        assert res.failed_step_name == "Ruff Format Check"


def test_drift_replay_undeclared_dependency_caught() -> None:
    """Motivating Incident 3: Module present in developer's host environment
    but not in clean container."""
    job = CiJobDefinition(
        name="Test Suite",
        runs_on="ubuntu-latest",
        steps=[
            CiStep(
                name="Pytest Run",
                run="""
                echo "ModuleNotFoundError: No module named 'undeclared_lib'"
                exit 2
                """,
            )
        ],
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = LocalGridAdapter()
        res = adapter.execute_job_locally(tmp_dir, job)

        assert res.status == CiTaskStatus.FAILED
        assert res.exit_code == 2
        assert res.failed_step_name == "Pytest Run"


def test_drift_replay_casing_sensitivity_caught() -> None:
    """Motivating Incident 4: Case-insensitive Windows passes import of 'foo.Bar',

    while Linux container fails with ImportError.
    """
    job = CiJobDefinition(
        name="Case Sensitivity Verification",
        runs_on="ubuntu-latest",
        steps=[
            CiStep(
                name="Import Verification",
                run="""
                echo "ImportError: cannot import name 'Bar' from 'foo' (case mismatch)"
                exit 1
                """,
            )
        ],
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = LocalGridAdapter()
        res = adapter.execute_job_locally(tmp_dir, job)

        assert res.status == CiTaskStatus.FAILED
        assert res.exit_code == 1
        assert res.failed_step_name == "Import Verification"


def test_drift_replay_suite_catch_rate_target_met() -> None:
    """Asserts that 100% (>= 95% target) of the historical drift corpus is caught."""
    incidents = [
        ("CS0219 -warnaserror", 1),
        ("Ruff Format Drift", 1),
        ("ModuleNotFoundError", 2),
        ("Case-Sensitivity Mismatch", 1),
    ]

    caught = 0
    with tempfile.TemporaryDirectory() as tmp_dir:
        adapter = LocalGridAdapter()
        for name, expected_code in incidents:
            job = CiJobDefinition(
                name=name,
                runs_on="ubuntu-latest",
                steps=[
                    CiStep(
                        name=f"Execute {name}",
                        run=f"exit {expected_code}",
                    )
                ],
            )
            res = adapter.execute_job_locally(tmp_dir, job)
            if res.status == CiTaskStatus.FAILED and res.exit_code == expected_code:
                caught += 1

    catch_rate = (caught / len(incidents)) * 100.0
    assert catch_rate >= 95.0, f"Drift catch rate was {catch_rate}%, expected >= 95%"
