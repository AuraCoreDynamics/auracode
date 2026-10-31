"""Tests for Python CI result attestation and verification."""

from auracode.ci.schemas import CiExecutionMode, CiTaskResult, CiTaskStatus
from auracode.ci.signer import (
    canonicalize_payload,
    generate_key_pair,
    sign_payload,
    verify_signature,
    verify_task_result,
)


def test_signer_roundtrip() -> None:
    pub_hex, priv_hex = generate_key_pair()

    canonical = canonicalize_payload(
        job_id="job-python-1",
        idempotency_key="idem-py-1",
        tree_hash="tree-py",
        image_digest="repo@sha256:11223344",
        status=CiTaskStatus.PASSED,
        exit_code=0,
        fencing_token=42,
        stdout_sha256="aabbccddeeff",
    )

    sig = sign_payload(canonical, priv_hex)
    assert sig
    assert verify_signature(canonical, sig, [pub_hex])


def test_signer_detects_tampering() -> None:
    pub_hex, priv_hex = generate_key_pair()

    canonical = canonicalize_payload(
        job_id="job-python-1",
        idempotency_key="idem-py-1",
        tree_hash="tree-py",
        image_digest="repo@sha256:11223344",
        status=CiTaskStatus.FAILED,
        exit_code=1,
        fencing_token=42,
        stdout_sha256="aabbccddeeff",
    )

    # Node signs failure
    sig = sign_payload(canonical, priv_hex)

    # Attacker crafts forged result claiming it passed
    tampered_result = CiTaskResult(
        job_id="job-python-1",
        status=CiTaskStatus.PASSED,
        exit_code=0,
        execution_mode=CiExecutionMode.WRAPPED_CONTAINER,
        duration_ms=1000,
        fencing_token=42,
        node_id="volunteer-1",
        node_signature=sig,
        stdout_sha256="aabbccddeeff",
        tree_hash="tree-py",
        image_digest="repo@sha256:11223344",
        idempotency_key="idem-py-1",
    )

    assert not verify_task_result(tampered_result, [pub_hex])


def test_signer_rejects_untrusted_key() -> None:
    _, priv_hex = generate_key_pair()
    other_pub, _ = generate_key_pair()

    canonical = canonicalize_payload(
        job_id="job-python-1",
        idempotency_key="idem-py-1",
        tree_hash="tree-py",
        image_digest="repo@sha256:11223344",
        status=CiTaskStatus.PASSED,
        exit_code=0,
        fencing_token=42,
        stdout_sha256="aabbccddeeff",
    )

    sig = sign_payload(canonical, priv_hex)
    result = CiTaskResult(
        job_id="job-python-1",
        status=CiTaskStatus.PASSED,
        exit_code=0,
        execution_mode=CiExecutionMode.WRAPPED_CONTAINER,
        duration_ms=1000,
        fencing_token=42,
        node_id="volunteer-1",
        node_signature=sig,
        stdout_sha256="aabbccddeeff",
        tree_hash="tree-py",
        image_digest="repo@sha256:11223344",
        idempotency_key="idem-py-1",
    )

    assert not verify_task_result(result, [other_pub])
