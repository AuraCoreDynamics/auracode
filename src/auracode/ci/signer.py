"""Cryptographic attestation and signature verification for CI task results.

Implements ECDSA P-256 signing matching AuraGrid Layer0Gatekeeper / CiResultSigner.
"""

from __future__ import annotations

import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from auracode.ci.schemas import CiTaskResult, CiTaskStatus


def generate_key_pair() -> tuple[str, str]:
    """Generates an ECDSA P-256 key pair returning (pub_hex, priv_hex) in DER format."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    pub_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pub_bytes.hex(), priv_bytes.hex()


def canonicalize_payload(
    job_id: str,
    idempotency_key: str,
    tree_hash: str | None,
    image_digest: str | None,
    status: CiTaskStatus,
    exit_code: int,
    fencing_token: int,
    stdout_sha256: str,
) -> str:
    """Generates RFC 8785 canonical JSON matching AuraGrid CiResultSigner."""
    status_str = status.value if hasattr(status, "value") else str(status)
    payload = {
        "exitCode": exit_code,
        "fencingToken": fencing_token,
        "idempotencyKey": idempotency_key or "",
        "imageDigest": image_digest or "",
        "jobId": job_id,
        "status": status_str,
        "stdoutSha256": stdout_sha256 or "",
        "treeHash": tree_hash or "",
    }
    # Deterministic alphabetical key order, no extra spaces
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sign_payload(canonical_json: str, private_key_hex: str) -> str:
    """Signs canonical payload with ECDSA P-256 private key and returns hex DER signature."""
    priv_bytes = bytes.fromhex(private_key_hex)
    private_key = serialization.load_der_private_key(priv_bytes, password=None)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise ValueError("Expected ECDSA P-256 private key.")

    sig_bytes = private_key.sign(
        canonical_json.encode("utf-8"),
        ec.ECDSA(hashes.SHA256()),
    )
    return sig_bytes.hex()


def verify_signature(
    canonical_json: str,
    signature_hex: str,
    trusted_public_keys_hex: list[str],
) -> bool:
    """Verifies an ECDSA P-256 signature against a list of trusted public keys."""
    if not signature_hex or not trusted_public_keys_hex:
        return False

    try:
        sig_bytes = bytes.fromhex(signature_hex)
    except Exception:
        return False

    data = canonical_json.encode("utf-8")

    for pub_hex in trusted_public_keys_hex:
        try:
            pub_bytes = bytes.fromhex(pub_hex)
            public_key = serialization.load_der_public_key(pub_bytes)
            if isinstance(public_key, ec.EllipticCurvePublicKey):
                public_key.verify(sig_bytes, data, ec.ECDSA(hashes.SHA256()))
                return True
        except Exception:
            continue

    return False


def verify_task_result(result: CiTaskResult, trusted_public_keys_hex: list[str]) -> bool:
    """Verifies that a CiTaskResult is authentically attested by a trusted key."""
    canonical = canonicalize_payload(
        job_id=result.job_id,
        idempotency_key=result.idempotency_key or "",
        tree_hash=result.tree_hash,
        image_digest=result.image_digest,
        status=result.status,
        exit_code=result.exit_code,
        fencing_token=result.fencing_token,
        stdout_sha256=result.stdout_sha256,
    )
    return verify_signature(canonical, result.node_signature, trusted_public_keys_hex)
