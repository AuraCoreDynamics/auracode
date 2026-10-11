"""Deterministic .aurabundle archive packager and inspector."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from auracode.bundle.manifest import AppManifest, ManifestValidator

EXCLUDED_PATTERNS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    ".DS_Store",
    ".eggs",
    "*.egg-info",
}


class BundlePackager:
    """Creates sealed, tamper-evident .aurabundle archives for AuraGrid deployment."""

    @classmethod
    def _is_excluded(cls, rel_path: Path) -> bool:
        """Check whether a relative path matches excluded dev patterns."""
        for part in rel_path.parts:
            if part in EXCLUDED_PATTERNS:
                return True
            if part.endswith(".pyc") or part.endswith(".egg-info"):
                return True
        return False

    @classmethod
    def pack(
        cls,
        source_dir: Path | str,
        output_file: Path | str,
        manifest_path: Path | str | None = None,
    ) -> Path:
        """Pack a source directory into an .aurabundle (ZIP) archive."""
        src = Path(source_dir).resolve()
        out = Path(output_file).resolve()
        if not src.is_dir():
            raise ValueError(f"Source directory does not exist: {src}")

        manifest_file = (
            Path(manifest_path).resolve() if manifest_path else src / "app.manifest.json"
        )

        if not manifest_file.is_file():
            raise ValueError(f"Required manifest file missing: {manifest_file}")

        is_valid, errors = ManifestValidator.validate_file(manifest_file)
        if not is_valid:
            err_msg = "; ".join(errors)
            raise ValueError(f"Manifest validation failed: {err_msg}")

        out.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # First write root app.manifest.json deterministically
            manifest_bytes = manifest_file.read_bytes()
            manifest_info = zipfile.ZipInfo("app.manifest.json")
            manifest_info.external_attr = 0o644 << 16
            zf.writestr(manifest_info, manifest_bytes)

            # Write remaining files in sorted order
            for file_path in sorted(src.rglob("*")):
                if file_path.is_file():
                    rel = file_path.relative_to(src)
                    if rel == Path("app.manifest.json"):
                        continue  # Already written at root
                    if cls._is_excluded(rel):
                        continue

                    # Ensure standard forward slash for archive paths
                    arcname = rel.as_posix()
                    file_info = zipfile.ZipInfo(arcname)
                    file_info.external_attr = 0o644 << 16
                    zf.writestr(file_info, file_path.read_bytes())

        return out

    @classmethod
    def inspect(cls, bundle_path: Path | str) -> dict[str, Any]:
        """Inspect bundle contents and manifest metadata without extracting."""
        bundle = Path(bundle_path).resolve()
        if not bundle.is_file():
            raise ValueError(f"Bundle file not found: {bundle}")

        hasher = hashlib.sha256()
        with open(bundle, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()

        with zipfile.ZipFile(bundle, "r") as zf:
            namelist = zf.namelist()
            if "app.manifest.json" not in namelist:
                raise ValueError("Corrupt bundle: missing root app.manifest.json")

            manifest_raw = zf.read("app.manifest.json").decode("utf-8")
            try:
                manifest_dict = json.loads(manifest_raw)
                manifest = AppManifest.model_validate(manifest_dict)
            except Exception as exc:
                raise ValueError(f"Failed to decode manifest in bundle: {exc}") from exc

            # Verify no members escape bundle root
            for name in namelist:
                if name.startswith("/") or name.startswith("\\") or ".." in name.split("/"):
                    raise ValueError(f"Path traversal detected in archive entry: {name}")

        return {
            "app_id": manifest.app_id,
            "name": manifest.name,
            "version": manifest.version,
            "sha256": digest,
            "file_count": len(namelist),
            "files": namelist,
            "cell_governance": manifest.cell_governance.model_dump(),
            "manifest": manifest.model_dump(),
        }
