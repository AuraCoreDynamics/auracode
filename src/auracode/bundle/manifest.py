"""AuraGrid application manifest models and governance validator."""

from __future__ import annotations

import json
from pathlib import Path, PurePath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CellGovernanceSpec(BaseModel):
    """Hardware and cell placement governance requirements."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    target_cells: list[str] = Field(default_factory=list, alias="targetCells")
    required_os: str = Field(default="any", alias="requiredOs")
    min_ram_mb: int = Field(default=512, alias="minRamMb")
    requires_gpu: bool = Field(default=False, alias="requiresGpu")
    gpu_min_vram_mb: int | None = Field(default=None, alias="gpuMinVramMb")


class InstallerSpec(BaseModel):
    """Specification for application installation script/command."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    path: str
    args: list[str] = Field(default_factory=list)
    required_os: str = Field(default="any", alias="requiredOs")


class StartupSpec(BaseModel):
    """Specification for primary application executable."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    path: str
    args: list[str] = Field(default_factory=list)


class ServiceSpec(BaseModel):
    """Specification for long-running daemon services."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    path: str
    args: list[str] = Field(default_factory=list)
    auto_restart: bool = Field(default=True, alias="autoRestart")


class AppManifest(BaseModel):
    """Root application governance manifest schema (app.manifest.json)."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    schema_version: str = Field(default="1.0", alias="schemaVersion")
    app_id: str = Field(alias="appId")
    name: str
    version: str
    description: str = ""
    author: str = ""
    installer: InstallerSpec | None = None
    startup: StartupSpec | None = None
    services: dict[str, ServiceSpec] = Field(default_factory=dict)
    cell_governance: CellGovernanceSpec = Field(
        default_factory=CellGovernanceSpec,
        alias="cellGovernance",
    )


class ManifestValidator:
    """Validates app.manifest.json files against schema and governance constraints."""

    @staticmethod
    def _is_safe_relative_path(path_str: str) -> bool:
        """Check that a path is strictly relative and contains no parent escapes."""
        if not path_str or not path_str.strip():
            return False
        clean = path_str.strip()
        if clean.startswith("/") or clean.startswith("\\"):
            return False
        pure = PurePath(clean)
        if pure.is_absolute():
            return False
        for part in pure.parts:
            if part in ("..", "~"):
                return False
            if ":" in part:  # Drive letters on Windows
                return False
        return True

    @classmethod
    def validate_data(cls, data: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate an in-memory dictionary representation of a manifest."""
        errors: list[str] = []
        try:
            manifest = AppManifest.model_validate(data)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                errors.append(f"Schema violation at {loc}: {err['msg']}")
            return False, errors

        # Verify entrypoint paths are strictly safe relative paths
        if manifest.installer and not cls._is_safe_relative_path(manifest.installer.path):
            errors.append(
                f"installer.path must be a safe relative path: {manifest.installer.path!r}"
            )

        if manifest.startup and not cls._is_safe_relative_path(manifest.startup.path):
            errors.append(f"startup.path must be a safe relative path: {manifest.startup.path!r}")

        for svc_name, svc_spec in manifest.services.items():
            if not cls._is_safe_relative_path(svc_spec.path):
                errors.append(
                    f"services[{svc_name}].path must be a safe relative path: {svc_spec.path!r}"
                )

        # Verify governance parameters
        if manifest.cell_governance.min_ram_mb < 64:
            errors.append("cell_governance.min_ram_mb must be at least 64 MB")

        if (
            manifest.cell_governance.requires_gpu
            and manifest.cell_governance.gpu_min_vram_mb is not None
            and manifest.cell_governance.gpu_min_vram_mb < 0
        ):
            errors.append("cell_governance.gpu_min_vram_mb cannot be negative")

        return len(errors) == 0, errors

    @classmethod
    def validate_file(cls, path: Path | str) -> tuple[bool, list[str]]:
        """Read and validate a manifest file on disk."""
        target = Path(path)
        if not target.is_file():
            return False, [f"Manifest file not found: {target}"]

        try:
            content = target.read_text(encoding="utf-8")
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            return False, [f"Invalid JSON in manifest: {exc}"]
        except Exception as exc:
            return False, [f"Failed to read manifest: {exc}"]

        if not isinstance(data, dict):
            return False, ["Root JSON value must be an object"]

        return cls.validate_data(data)
