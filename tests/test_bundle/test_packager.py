"""Unit tests for AuraGrid application bundle packaging and validation."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from auracode.bundle.manifest import ManifestValidator
from auracode.bundle.packager import BundlePackager


@pytest.fixture
def sample_manifest_data() -> dict:
    return {
        "schemaVersion": "1.0",
        "appId": "testapp",
        "name": "Test Application",
        "version": "1.0.0",
        "description": "A test app for grid deployment",
        "author": "AuraGrid Tests",
        "installer": {
            "path": "scripts/install.sh",
            "args": ["--quiet"],
            "requiredOs": "linux",
        },
        "startup": {
            "path": "bin/testapp",
            "args": ["--port", "8080"],
        },
        "services": {
            "worker": {
                "path": "bin/worker",
                "args": ["run"],
                "autoRestart": True,
            }
        },
        "cellGovernance": {
            "targetCells": ["gpu-cell-1", "worker-cell"],
            "requiredOs": "linux",
            "minRamMb": 1024,
            "requiresGpu": True,
            "gpuMinVramMb": 4096,
        },
    }


def test_manifest_validator_valid(sample_manifest_data: dict, tmp_path: Path) -> None:
    manifest_file = tmp_path / "app.manifest.json"
    manifest_file.write_text(json.dumps(sample_manifest_data), encoding="utf-8")

    is_valid, errors = ManifestValidator.validate_file(manifest_file)
    assert is_valid is True
    assert errors == []


def test_manifest_validator_path_traversal(sample_manifest_data: dict, tmp_path: Path) -> None:
    sample_manifest_data["startup"]["path"] = "../../../etc/passwd"
    manifest_file = tmp_path / "app.manifest.json"
    manifest_file.write_text(json.dumps(sample_manifest_data), encoding="utf-8")

    is_valid, errors = ManifestValidator.validate_file(manifest_file)
    assert is_valid is False
    assert any("safe relative path" in err for err in errors)


def test_manifest_validator_absolute_path(sample_manifest_data: dict, tmp_path: Path) -> None:
    sample_manifest_data["installer"]["path"] = "/usr/bin/install"
    manifest_file = tmp_path / "app.manifest.json"
    manifest_file.write_text(json.dumps(sample_manifest_data), encoding="utf-8")

    is_valid, errors = ManifestValidator.validate_file(manifest_file)
    assert is_valid is False
    assert any("safe relative path" in err for err in errors)


def test_manifest_validator_invalid_governance(sample_manifest_data: dict, tmp_path: Path) -> None:
    sample_manifest_data["cellGovernance"]["minRamMb"] = 16  # < 64 MB
    manifest_file = tmp_path / "app.manifest.json"
    manifest_file.write_text(json.dumps(sample_manifest_data), encoding="utf-8")

    is_valid, errors = ManifestValidator.validate_file(manifest_file)
    assert is_valid is False
    assert any("at least 64 MB" in err for err in errors)


def test_bundle_packager_success(sample_manifest_data: dict, tmp_path: Path) -> None:
    src_dir = tmp_path / "app_source"
    src_dir.mkdir()
    (src_dir / "bin").mkdir()
    (src_dir / "scripts").mkdir()

    # Write files
    (src_dir / "app.manifest.json").write_text(
        json.dumps(sample_manifest_data),
        encoding="utf-8",
    )
    (src_dir / "bin" / "testapp").write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    (src_dir / "bin" / "worker").write_text("#!/bin/sh\necho worker\n", encoding="utf-8")
    (src_dir / "scripts" / "install.sh").write_text("echo install\n", encoding="utf-8")
    # Ignored file
    (src_dir / "__pycache__").mkdir()
    (src_dir / "__pycache__" / "cached.pyc").write_text("bytecode", encoding="utf-8")

    out_bundle = tmp_path / "testapp.aurabundle"
    result_path = BundlePackager.pack(src_dir, out_bundle)
    assert result_path == out_bundle
    assert out_bundle.exists()

    # Inspect
    info = BundlePackager.inspect(out_bundle)
    assert info["app_id"] == "testapp"
    assert info["name"] == "Test Application"
    assert info["version"] == "1.0.0"
    assert len(info["sha256"]) == 64
    assert "app.manifest.json" in info["files"]
    assert "bin/testapp" in info["files"]
    assert not any("__pycache__" in f for f in info["files"])
    assert info["cell_governance"]["min_ram_mb"] == 1024


def test_bundle_packager_missing_manifest(tmp_path: Path) -> None:
    src_dir = tmp_path / "empty_dir"
    src_dir.mkdir()
    out_bundle = tmp_path / "fail.aurabundle"

    with pytest.raises(ValueError, match="Required manifest file missing"):
        BundlePackager.pack(src_dir, out_bundle)


def test_bundle_inspect_detects_corrupt(tmp_path: Path) -> None:
    bad_zip = tmp_path / "corrupt.aurabundle"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("some_random_file.txt", "data")

    with pytest.raises(ValueError, match="missing root app.manifest.json"):
        BundlePackager.inspect(bad_zip)
