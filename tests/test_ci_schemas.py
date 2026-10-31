"""Tests for AuraCode CI schemas and contracts."""

import pytest

from auracode.ci.protocols import (
    ICiProviderAdapter,
)
from auracode.ci.schemas import (
    CiExecutionMode,
    CiJobDefinition,
    CiJobPriority,
    CiStep,
    CiTaskRequest,
    CiTaskResult,
    CiWorkspaceRef,
)


def test_ci_step_roundtrip() -> None:
    step = CiStep(name="build", run="dotnet build", shell="bash", timeout_sec=120)
    data = step.to_dict()
    restored = CiStep.from_dict(data)
    assert restored == step


def test_ci_task_request_validation() -> None:
    ws = CiWorkspaceRef(
        commit_sha="a" * 40,
        tree_hash="b" * 40,
        bundle_uri="file:///tmp/bundle.tar.gz",
        bundle_sha256="c" * 64,
    )
    req = CiTaskRequest(
        job_id="job-1",
        workspace_ref=ws,
        image_digest="sha256:" + "0" * 64,
        steps=[CiStep(name="test", run="pytest")],
        environment={"FOO": "bar", "PYTHON_VERSION": "3.12"},
        priority=CiJobPriority.PRE_PUSH_GATE,
    )
    assert req.priority == CiJobPriority.PRE_PUSH_GATE
    d = req.to_dict()
    restored = CiTaskRequest.from_dict(d)
    assert restored.job_id == "job-1"
    assert restored.image_digest == "sha256:" + "0" * 64


def test_ci_task_request_rejects_unpinned_image() -> None:
    ws = CiWorkspaceRef("a" * 40, "b" * 40, "uri", "sha")
    with pytest.raises(ValueError, match="must be a pinned sha256"):
        CiTaskRequest(
            job_id="job-1",
            workspace_ref=ws,
            image_digest="ubuntu:latest",  # mutable tag rejected
            steps=[],
        )


def test_ci_task_request_rejects_invalid_env_key() -> None:
    ws = CiWorkspaceRef("a" * 40, "b" * 40, "uri", "sha")
    with pytest.raises(ValueError, match="violates POSIX shell standard"):
        CiTaskRequest(
            job_id="job-1",
            workspace_ref=ws,
            image_digest="sha256:" + "0" * 64,
            steps=[],
            environment={"bad-key; rm -rf /": "val"},
        )


def test_ci_task_result_roundtrip() -> None:
    res = CiTaskResult(
        job_id="job-1",
        exit_code=0,
        execution_mode=CiExecutionMode.WRAPPED_CONTAINER,
        duration_ms=4500,
        fencing_token=42,
        node_id="node-alpha",
        node_signature="sig123",
        stdout_sha256="abc",
    )
    d = res.to_dict()
    restored = CiTaskResult.from_dict(d)
    assert restored == res


def test_protocols_runtime_checkable() -> None:
    class DummyAdapter:
        @property
        def name(self) -> str:
            return "dummy"

        def detect(self, repo_path: str) -> bool:
            return True

        def parse_workflows(self, repo_path: str) -> list[CiJobDefinition]:
            return []

        def supports_matrix(self) -> bool:
            return False

    adapter = DummyAdapter()
    assert isinstance(adapter, ICiProviderAdapter)


def test_ci_sandbox_profile_contract() -> None:
    import json
    from pathlib import Path

    ci_dir = Path(__file__).parent.parent / "src" / "auracode" / "ci"
    profile_path = ci_dir / "ci-sandbox-profile.v1.json"
    assert profile_path.is_file()

    with profile_path.open(encoding="utf-8") as f:
        profile = json.load(f)

    assert profile["version"] == "1.0"
    assert profile["pidsLimit"] == 512
    assert profile["nofileLimit"] == 4096
    assert profile["readOnly"] is True
    assert profile["defaultNetwork"] == "none"
    assert profile["userns"] == "keep-id"
    assert any(m["destination"] == "/tmp" for m in profile["tmpfsMounts"])
    assert any(m["destination"] == "/home/ci" for m in profile["tmpfsMounts"])
    assert profile["env"]["HOME"] == "/home/ci"
