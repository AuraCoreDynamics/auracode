"""Spyder and Scientific Python IDE dockable plugin and bridge for AuraCode.

Integrates AuraCode's autonomous reasoning, self-healing execution loop,
AST repo-mapping, and AuraSeed managed virtual environment (mvenv) switching
directly into the Spyder IDE for geospatial and data science workflows
(e.g., AuraMist, VoxelVault, PyTorch, GDAL).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

from auracode.engine.repo_map import RepoMapBuilder

logger = logging.getLogger(__name__)


class SpyderAuraCodeBridge:
    """Core companion engine for Spyder and scientific Python IDE workflows."""

    def __init__(
        self,
        workspace_root: Path | str = ".",
        auracode_url: str = "http://127.0.0.1:8741",
        grid_url: str = "http://127.0.0.1:7077",
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.auracode_url = auracode_url.rstrip("/")
        self.grid_url = grid_url.rstrip("/")

    def launch_ui(self, host: str = "127.0.0.1", port: int = 8741) -> str:
        """Open the Mission Command operations deck in the default web browser."""
        url = f"http://{host}:{port}/ui"
        webbrowser.open(url)
        return f"Mission Command opened at: {url}"

    def get_repo_map(self, max_chars: int = 2048) -> str:
        """Inspect the structural AST architecture of the active project (<2KB)."""
        builder = RepoMapBuilder(root_dir=self.workspace_root, max_chars=max_chars)
        return builder.build()

    def verify(
        self,
        command: str = "pytest",
        timeout: int = 60,
    ) -> dict[str, int | str | bool]:
        """Run an interactive verification test suite and capture outcome."""
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "passed": res.returncode == 0,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }
        except Exception as exc:
            return {
                "passed": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Verification error: {exc}",
            }

    def get_mvenvs(self) -> list[dict[str, Any]]:
        """Discover AuraSeed managed virtual environments available on the system."""
        try:
            from auraseed.mvenv.manager import MvenvManager

            manager = MvenvManager()
            records = manager.catalog.list_records()
            return [
                {
                    "name": r.name,
                    "path": r.path,
                    "python_path": r.python_path,
                    "python_version": r.python_version,
                    "packages_count": len(r.packages),
                    "size_bytes": r.size_bytes,
                }
                for r in records
            ]
        except Exception as exc:
            logger.debug(f"AuraSeed MvenvManager not loaded: {exc}")

        # Fallback inspection of standard AuraSeed mvenv storage roots
        roots = [
            os.environ.get("AURASEED_MVENV_ROOT"),
            os.environ.get("AURAGRID_MVENV_ROOT"),
            Path.home() / ".auraseed" / "mvenv",
        ]
        results: list[dict[str, Any]] = []
        for root in roots:
            if not root:
                continue
            p = Path(root).resolve()
            if not p.is_dir():
                continue
            for entry in p.iterdir():
                if entry.is_dir():
                    meta = entry / ".mvenv.json"
                    py_exe = (
                        entry
                        / ("Scripts" if os.name == "nt" else "bin")
                        / ("python.exe" if os.name == "nt" else "python")
                    )
                    if py_exe.exists():
                        name = entry.name
                        py_ver = "unknown"
                        if meta.exists():
                            try:
                                d = json.loads(meta.read_text(encoding="utf-8"))
                                name = d.get("name", entry.name)
                                py_ver = d.get("python_version", "unknown")
                            except Exception:
                                pass
                        results.append(
                            {
                                "name": name,
                                "path": str(entry),
                                "python_path": str(py_exe),
                                "python_version": py_ver,
                                "packages_count": 0,
                                "size_bytes": 0,
                            }
                        )
        return results

    def switch_mvenv(self, name: str) -> dict[str, Any]:
        """Switch active virtual environment to the specified AuraSeed mvenv."""
        mvenvs = self.get_mvenvs()
        target = next((m for m in mvenvs if m["name"] == name), None)
        if not target:
            return {"success": False, "error": f"mvenv '{name}' not found."}

        python_path = target["python_path"]
        os.environ["VIRTUAL_ENV"] = target["path"]
        os.environ["AURASEED_ACTIVE_MVENV"] = name
        # Prepend to PATH for spawned child processes
        bin_dir = str(Path(python_path).parent)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

        return {
            "success": True,
            "name": name,
            "path": target["path"],
            "python_path": python_path,
            "message": f"Switched to AuraSeed mvenv '{name}' ({python_path})",
        }

    def get_grid_status(self) -> dict[str, Any]:
        """Query active status of the local AuraGrid node."""
        import urllib.request

        try:
            req = urllib.request.Request(
                f"{self.grid_url}/api/status",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"online": False, "error": str(exc), "grid_url": self.grid_url}
        return {"online": False, "grid_url": self.grid_url}


# ── Spyder Dockable UI Widget (Compatible with PyQt5, PyQt6, PySide) ──────


def _create_spyder_widget_class():
    """Lazily construct Qt widget class to prevent hard GUI dependencies during headless CLI."""
    try:
        from qtpy.QtWidgets import (
            QComboBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPushButton,
            QTabWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        class SpyderAuraCodeWidget(QWidget):
            """Dockable Spyder UI widget providing 4-tab control plane."""

            def __init__(self, bridge: SpyderAuraCodeBridge, parent=None):
                super().__init__(parent)
                self.bridge = bridge
                self._init_ui()

            def _init_ui(self):
                layout = QVBoxLayout(self)
                layout.setContentsMargins(4, 4, 4, 4)

                self.tabs = QTabWidget()
                layout.addWidget(self.tabs)

                # Tab 1: AI Cockpit & Act
                tab1 = QWidget()
                t1_layout = QVBoxLayout(tab1)
                self.status_label = QLabel("AuraCode: Ready")
                t1_layout.addWidget(self.status_label)

                self.prompt_edit = QLineEdit()
                self.prompt_edit.setPlaceholderText("Enter prompt or instruction for AuraCode...")
                t1_layout.addWidget(self.prompt_edit)

                h1 = QHBoxLayout()
                self.act_btn = QPushButton("Autonomous /act")
                self.act_btn.clicked.connect(self._run_act)
                self.cockpit_btn = QPushButton("Open Web Deck")
                self.cockpit_btn.clicked.connect(lambda: self.bridge.launch_ui())
                h1.addWidget(self.act_btn)
                h1.addWidget(self.cockpit_btn)
                t1_layout.addLayout(h1)

                self.output_edit = QTextEdit()
                self.output_edit.setReadOnly(True)
                t1_layout.addWidget(self.output_edit)
                self.tabs.addTab(tab1, "AuraCode")

                # Tab 2: Repo-Map
                tab2 = QWidget()
                t2_layout = QVBoxLayout(tab2)
                self.refresh_map_btn = QPushButton("Refresh AST Repo-Map")
                self.refresh_map_btn.clicked.connect(self._refresh_map)
                t2_layout.addWidget(self.refresh_map_btn)

                self.map_view = QTextEdit()
                self.map_view.setReadOnly(True)
                t2_layout.addWidget(self.map_view)
                self.tabs.addTab(tab2, "Repo-Map")

                # Tab 3: AuraSeed mvenv Switcher (for AuraMist / VoxelVault)
                tab3 = QWidget()
                t3_layout = QVBoxLayout(tab3)
                t3_layout.addWidget(QLabel("AuraSeed Managed Virtual Environments (mvenv):"))

                self.mvenv_combo = QComboBox()
                t3_layout.addWidget(self.mvenv_combo)

                h3 = QHBoxLayout()
                self.switch_mvenv_btn = QPushButton("Switch Active mvenv")
                self.switch_mvenv_btn.clicked.connect(self._switch_mvenv)
                self.refresh_mvenv_btn = QPushButton("Refresh mvenvs")
                self.refresh_mvenv_btn.clicked.connect(self._populate_mvenvs)
                h3.addWidget(self.switch_mvenv_btn)
                h3.addWidget(self.refresh_mvenv_btn)
                t3_layout.addLayout(h3)

                self.mvenv_info = QTextEdit()
                self.mvenv_info.setReadOnly(True)
                t3_layout.addWidget(self.mvenv_info)
                self.tabs.addTab(tab3, "AuraSeed mvenv")

                # Tab 4: AuraGrid Status
                tab4 = QWidget()
                t4_layout = QVBoxLayout(tab4)
                self.grid_status_view = QTextEdit()
                self.grid_status_view.setReadOnly(True)
                self.refresh_grid_btn = QPushButton("Check AuraGrid Status")
                self.refresh_grid_btn.clicked.connect(self._refresh_grid)
                t4_layout.addWidget(self.refresh_grid_btn)
                t4_layout.addWidget(self.grid_status_view)
                self.tabs.addTab(tab4, "AuraGrid")

                self._populate_mvenvs()
                self._refresh_map()

            def _refresh_map(self):
                map_text = self.bridge.get_repo_map(4096)
                self.map_view.setPlainText(map_text)

            def _populate_mvenvs(self):
                self.mvenv_combo.clear()
                mvenvs = self.bridge.get_mvenvs()
                if not mvenvs:
                    self.mvenv_combo.addItem("No mvenvs detected")
                    self.mvenv_info.setPlainText(
                        "No AuraSeed managed virtual environments found. "
                        "Create one using 'auraseed mvenv create <name>'."
                    )
                    return
                for m in mvenvs:
                    self.mvenv_combo.addItem(f"{m['name']} ({m['python_version']})", m["name"])
                self.mvenv_info.setPlainText(json.dumps(mvenvs, indent=2))

            def _switch_mvenv(self):
                idx = self.mvenv_combo.currentIndex()
                if idx < 0:
                    return
                mvenv_name = self.mvenv_combo.itemData(idx)
                if not mvenv_name:
                    return
                res = self.bridge.switch_mvenv(mvenv_name)
                if res.get("success"):
                    self.status_label.setText(f"Active mvenv: {mvenv_name}")
                    QMessageBox.information(self, "mvenv Switched", res.get("message", "Switched."))
                else:
                    QMessageBox.warning(self, "Switch Failed", res.get("error", "Error."))

            def _run_act(self):
                prompt = self.prompt_edit.text().strip()
                if not prompt:
                    return
                self.status_label.setText("Running autonomous /act verification...")
                self.output_edit.append(f"> Running /act: {prompt}")
                res = self.bridge.verify("pytest")
                self.output_edit.append(
                    f"Verification result: {'PASSED' if res['passed'] else 'FAILED'}"
                )
                if res.get("stdout"):
                    self.output_edit.append(str(res["stdout"]))
                self.status_label.setText("Ready")

            def _refresh_grid(self):
                status = self.bridge.get_grid_status()
                self.grid_status_view.setPlainText(json.dumps(status, indent=2))

        return SpyderAuraCodeWidget
    except ImportError:

        class FallbackWidget:
            """Headless fallback when Qt is not installed."""

            def __init__(self, bridge: SpyderAuraCodeBridge, parent=None):
                self.bridge = bridge

        return FallbackWidget


SpyderAuraCodeWidget = _create_spyder_widget_class()


# ── Spyder Plugin Definition ─────────────────────────────────────────────

try:
    from spyder.api.plugin_registration.decorators import on_plugin_available
    from spyder.api.plugins import Plugins, SpyderDockablePlugin

    class SpyderAuraCodePlugin(SpyderDockablePlugin):
        """First-class Spyder 5+ dockable plugin for AuraCode & AuraSeed mvenv."""

        NAME = "auracode"
        REQUIRES = []
        OPTIONAL = []
        TABIFY = [Plugins.Help]
        WIDGET_CLASS = SpyderAuraCodeWidget

        def get_name(self):
            return "AuraCode"

        def get_description(self):
            return (
                "Autonomous AI pair programmer and AuraSeed mvenv manager for scientific workflows."
            )

        def get_icon(self):
            return self.create_icon("code")

        def on_initialize(self):
            self.bridge = SpyderAuraCodeBridge()

        @on_plugin_available(plugin=Plugins.Preferences)
        def on_preferences_available(self):
            pass

        def check_compatibility(self):
            return True, ""

except ImportError:

    class SpyderAuraCodePlugin:
        """Fallback representation of the Spyder plugin when running in non-Spyder environments."""

        NAME = "auracode"

        def __init__(self, workspace_root: str = "."):
            self.bridge = SpyderAuraCodeBridge(workspace_root=workspace_root)
            self.widget = SpyderAuraCodeWidget(self.bridge)
