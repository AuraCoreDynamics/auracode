"""Tests for the upgraded Spyder IDE plugin and AuraSeed mvenv switcher."""

from __future__ import annotations

import os
from pathlib import Path

from auracode.adapters.spyder_bridge import (
    SpyderAuraCodeBridge,
    SpyderAuraCodePlugin,
)


def test_spyder_bridge_basics(tmp_path: Path):
    sample_file = tmp_path / "geo_processor.py"
    sample_file.write_text(
        "class GeoRaster:\n    def process_tile(self, x: int):\n        return x * 2\n",
        encoding="utf-8",
    )

    bridge = SpyderAuraCodeBridge(workspace_root=tmp_path)
    map_text = bridge.get_repo_map()
    assert "GeoRaster" in map_text
    assert "process_tile" in map_text

    # Verify launch_ui returns cockpit URL
    url = bridge.launch_ui(host="localhost", port=8741)
    assert "http://localhost:8741/ui" in url


def test_spyder_mvenv_discovery_and_switching(tmp_path: Path, monkeypatch):
    mvenv_dir = tmp_path / "auramist_geo"
    mvenv_dir.mkdir(parents=True)
    scripts_dir = mvenv_dir / ("Scripts" if os.name == "nt" else "bin")
    scripts_dir.mkdir(parents=True)
    py_exe = scripts_dir / ("python.exe" if os.name == "nt" else "python")
    py_exe.write_text("", encoding="utf-8")

    meta_file = mvenv_dir / ".mvenv.json"
    meta_file.write_text(
        '{"name": "auramist_geo", "python_version": "3.11.8", '
        '"packages": ["rasterio", "voxelvault"]}',
        encoding="utf-8",
    )

    monkeypatch.setenv("AURASEED_MVENV_ROOT", str(tmp_path))

    bridge = SpyderAuraCodeBridge(workspace_root=tmp_path)
    mvenvs = bridge.get_mvenvs()
    assert len(mvenvs) >= 1
    geo_mvenv = next((m for m in mvenvs if m["name"] == "auramist_geo"), None)
    assert geo_mvenv is not None
    assert geo_mvenv["python_version"] == "3.11.8"

    # Test switching to the mvenv
    switch_res = bridge.switch_mvenv("auramist_geo")
    assert switch_res["success"] is True
    assert os.environ.get("AURASEED_ACTIVE_MVENV") == "auramist_geo"
    assert os.environ.get("VIRTUAL_ENV") == str(mvenv_dir)

    # Switching to nonexistent mvenv returns error
    fail_res = bridge.switch_mvenv("nonexistent_mvenv")
    assert fail_res["success"] is False


def test_spyder_plugin_instantiation(tmp_path: Path):
    plugin = SpyderAuraCodePlugin(workspace_root=str(tmp_path))
    assert plugin.NAME == "auracode"
    assert plugin.bridge is not None
    assert plugin.widget is not None
