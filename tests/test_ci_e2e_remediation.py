"""Tests for autonomous repair engine, anti-gaming boundaries, and diagnostic extraction."""

from pathlib import Path

import pytest

from auracode.ci.diagnostics import DiagnosticExtractor
from auracode.ci.repair import (
    BannedSuppressionError,
    OscillationDetectedError,
    RepairEngine,
)


def test_diagnostic_extractor_untrusted_log_sanitization() -> None:
    raw_log = """
Determining projects to restore...
C:\\foo\\Bar.cs(42,15): error CS0246: The type or namespace name 'MyType' could not be found
tests/test_app.py:18:1: E402 Module level import not at top of file
FAILED tests/test_math.py::test_division - ZeroDivisionError
Random untrusted stdout garbage with <script>alert(1)</script> and null bytes \0
"""
    extractor = DiagnosticExtractor()
    diagnostics = extractor.extract(raw_log)

    assert len(diagnostics) == 3

    # C# error
    assert diagnostics[0].file == "C:\\foo\\Bar.cs"
    assert diagnostics[0].line == 42
    assert diagnostics[0].rule_id == "CS0246"

    # Ruff error
    assert diagnostics[1].file == "tests/test_app.py"
    assert diagnostics[1].line == 18
    assert diagnostics[1].rule_id == "E402"

    # Pytest error
    assert diagnostics[2].file == "tests/test_math.py"
    assert diagnostics[2].rule_id == "PYTEST_FAIL"
    assert diagnostics[2].message == "test_division"


def test_diagnostic_fingerprinting_deterministic() -> None:
    extractor = DiagnosticExtractor()
    log1 = "tests/foo.py:10:1: E501 line too long\n"
    log2 = "tests/foo.py:10:1: E501 line too long\n"

    diag1 = extractor.extract(log1)
    diag2 = extractor.extract(log2)

    fp1 = DiagnosticExtractor.fingerprint(diag1)
    fp2 = DiagnosticExtractor.fingerprint(diag2)

    assert fp1 == fp2
    assert len(fp1) == 16


def test_anti_gaming_filter_blocks_suppression() -> None:
    engine = RepairEngine()

    # Rejects # noqa
    patch_noqa = """
--- a/src/app.py
+++ b/src/app.py
@@ -10,1 +10,1 @@
-import os
+import os  # noqa: F401
"""
    with pytest.raises(BannedSuppressionError, match="banned suppression token '# noqa'"):
        engine.validate_patch_hygiene(patch_noqa)

    # Rejects <NoWarn>
    patch_nowarn = """
--- a/src/App.csproj
+++ b/src/App.csproj
@@ -5,1 +5,1 @@
+<NoWarn>CS0246</NoWarn>
"""
    with pytest.raises(BannedSuppressionError, match="banned suppression token '<nowarn>'"):
        engine.validate_patch_hygiene(patch_nowarn)

    # Rejects [SuppressMessage]
    patch_suppress = """
--- a/src/Service.cs
+++ b/src/Service.cs
@@ -1,1 +1,1 @@
+[SuppressMessage("Category", "CS0117")]
"""
    with pytest.raises(
        BannedSuppressionError, match="banned suppression token '\\[suppressmessage'"
    ):
        engine.validate_patch_hygiene(patch_suppress)

    # Rejects uppercase NOQA
    patch_upper_noqa = """
--- a/src/app.py
+++ b/src/app.py
@@ -1,1 +1,1 @@
+import foo # NOQA
"""
    with pytest.raises(BannedSuppressionError, match="banned suppression token '# noqa'"):
        engine.validate_patch_hygiene(patch_upper_noqa)

    # Rejects @pytest.mark.skip
    patch_skip = """
--- a/tests/test_x.py
+++ b/tests/test_x.py
@@ -1,1 +1,1 @@
+@pytest.mark.skip(reason="gaming")
"""
    with pytest.raises(
        BannedSuppressionError, match="banned suppression token '@pytest.mark.skip'"
    ):
        engine.validate_patch_hygiene(patch_skip)

    # Rejects workflow YAML modification
    patch_wf = """
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -10,1 +10,1 @@
--warnaserror
"""
    with pytest.raises(BannedSuppressionError, match="restricted path or CI workflow"):
        engine.validate_patch_hygiene(patch_wf)

    # Rejects pyproject.toml modification
    patch_pyproject = """
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -1,1 +1,1 @@
+ignore = ["ALL"]
"""
    with pytest.raises(BannedSuppressionError, match="restricted path or CI workflow"):
        engine.validate_patch_hygiene(patch_pyproject)


def test_oscillation_detection() -> None:
    engine = RepairEngine()

    # Iteration 1: FP A, count 2
    # Iteration 2: FP B, count 1
    # Iteration 3: FP A (oscillated back to state A!)
    with pytest.raises(OscillationDetectedError, match="oscillation detected"):
        engine.verify_bounds(
            iteration=3,
            current_fingerprint="fp_state_A",
            current_count=1,
            fingerprint_history=["fp_state_A", "fp_state_B"],
            count_history=[2, 1],
            max_iterations=3,
        )


def test_strictly_decreasing_count_enforcement() -> None:
    engine = RepairEngine()

    # Diagnostic count did not decrease (2 -> 2)
    with pytest.raises(ValueError, match="count did not decrease"):
        engine.verify_bounds(
            iteration=2,
            current_fingerprint="fp_state_B",
            current_count=2,
            fingerprint_history=["fp_state_A"],
            count_history=[2],
            max_iterations=3,
        )


def test_commit_trailers_generation() -> None:
    engine = RepairEngine()
    trailers = engine.compute_commit_trailers(
        iteration=2,
        fencing_token=42,
        node_id="node-omega",
        diagnostic="CS0246",
        model="claude-3-7-sonnet",
        prompt_sha256="abc123sha",
        attestation="sig999",
    )
    assert "Aura-Repair-Iteration: 2" in trailers
    assert "Aura-Repair-Fencing-Token: 42" in trailers
    assert "Aura-Repair-Node: node-omega" in trailers
    assert "Repair-Diagnostic: CS0246" in trailers
    assert "Model: claude-3-7-sonnet" in trailers
    assert "Prompt-Sha256: abc123sha" in trailers
    assert "Verified-By: node-omega" in trailers
    assert "Repair-Attestation: sig999" in trailers


def test_removal_of_suppression_allowed() -> None:
    """A4.5: A patch that *removes* a # noqa or suppression must NOT be rejected."""
    engine = RepairEngine()
    patch_remove_noqa = """
--- a/src/clean.py
+++ b/src/clean.py
@@ -1,1 +1,1 @@
-import os  # noqa: F401
+import os
"""
    # Removing suppression is clean and must succeed
    engine.validate_patch_hygiene(patch_remove_noqa)


def test_structural_hunks_rejected() -> None:
    """A4.5: Rename, delete, binary and mode changes are forbidden in auto-repair patches."""
    engine = RepairEngine()

    rename_patch = """
diff --git a/src/old.py b/src/new.py
similarity index 100%
rename from src/old.py
rename to src/new.py
"""
    with pytest.raises(BannedSuppressionError, match="structural hunk"):
        engine.validate_patch_hygiene(rename_patch)

    delete_patch = """
diff --git a/src/test.py b/src/test.py
deleted file mode 100644
"""
    with pytest.raises(BannedSuppressionError, match="structural hunk"):
        engine.validate_patch_hygiene(delete_patch)


def test_all_r23_suppression_tokens_blocked() -> None:
    """A4.5: All tokens identified in Peer Review R23 are blocked on added lines."""
    engine = RepairEngine()

    tokens = [
        "# ruff: noqa",
        "#pragma warning disable CS0168",
        "#nullable disable",
        "<WarningsNotAsErrors>CS0168</WarningsNotAsErrors>",
        "<TreatWarningsAsErrors>false</TreatWarningsAsErrors>",
        "pytest.skip('bypassing')",
        "@pytest.mark.xfail",
    ]

    for tok in tokens:
        patch = f"""
--- a/src/code.py
+++ b/src/code.py
@@ -1,1 +1,1 @@
+{tok}
"""
        with pytest.raises(BannedSuppressionError):
            engine.validate_patch_hygiene(patch)


def test_isolated_worktree_invariant() -> None:
    """A4.1: Creating an isolated repair worktree must never mutate developer's HEAD or branch."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir) / "repo"
        repo.mkdir()

        # Initialize git repo and make a commit
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=repo, check=True)

        (repo / "file.txt").write_text("initial", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

        head_before = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()
        status_before = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        engine = RepairEngine()
        worktree_dir = Path(tmp_dir) / "isolated_wt"
        branch_name = engine.create_isolated_worktree(repo, head_before, worktree_dir)

        # Developer's working tree must be byte-identical!
        head_after = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()
        status_after = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        assert head_before == head_after
        assert status_before == status_after

        # Clean up worktree
        engine.cleanup_worktree(repo, worktree_dir, delete_branch=True, branch_name=branch_name)
