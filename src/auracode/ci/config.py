"""Keyring-backed configuration and credential store for AuraCode CI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SERVICE_NAME = "auracode-ci"


@dataclass
class CiConfig:
    """Persistent configuration for AuraCode CI."""

    default_grid_endpoint: str = "http://loopback:5000"
    timeout_sec: int = 600
    container_engine: str = "podman"
    image_mappings: dict[str, str] = field(
        default_factory=lambda: {
            "ubuntu-latest": (
                "sha256:4f4fb700ef54461cfa02571ae0db9a0dc1e0cdb55774843d52d829b64776350a"
            ),
            "ubuntu-22.04": (
                "sha256:4f4fb700ef54461cfa02571ae0db9a0dc1e0cdb55774843d52d829b64776350a"
            ),
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CiConfig:
        return cls(
            default_grid_endpoint=data.get("default_grid_endpoint", "http://loopback:5000"),
            timeout_sec=int(data.get("timeout_sec", 600)),
            container_engine=data.get("container_engine", "podman"),
            image_mappings=dict(data.get("image_mappings", {})),
        )


class CiConfigStore:
    """Secure credential and configuration store backed by OS keyring and local JSON."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or (Path.home() / ".auracode")
        self.config_file = self.config_dir / "ci_config.json"
        self._config = self._load()

    @property
    def config(self) -> CiConfig:
        return self._config

    def _load(self) -> CiConfig:
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                return CiConfig.from_dict(data)
            except Exception:
                return CiConfig()
        return CiConfig()

    def save(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(self._config.to_dict(), indent=2),
            encoding="utf-8",
        )

    def get_credential(self, service: str, account: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(service, account)
        except Exception:
            return None

    def set_credential(self, service: str, account: str, secret: str) -> bool:
        try:
            import keyring

            keyring.set_password(service, account, secret)
            return True
        except Exception:
            return False

    def delete_credential(self, service: str, account: str) -> bool:
        try:
            import keyring

            keyring.delete_password(service, account)
            return True
        except Exception:
            return False
