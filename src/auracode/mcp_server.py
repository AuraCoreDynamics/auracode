"""Reverse-MCP server — exposes AuraCode capabilities as MCP tools."""

from __future__ import annotations

import uuid
from typing import Any


def create_mcp_server(engine: Any) -> Any | None:
    """Create an MCP server exposing AuraCode capabilities as tools.

    Returns ``None`` if the ``mcp`` package is not installed.
    """
    try:
        from mcp.server import FastMCP
    except ImportError:
        return None

    server = FastMCP("auracode")

    def _build_request(
        prompt: str,
        intent: str,
        adapter: str = "mcp",
        execution_mode: str = "standard",
        routing_preference: str = "auto",
        sovereignty_enforcement: str = "none",
        retrieval_mode: str = "disabled",
        context_session: Any = None,
    ):
        """Build an EngineRequest with typed execution policy."""
        from auracode.models.request import (
            EngineRequest,
            ExecutionMode,
            ExecutionPolicy,
            LatencyBudget,
            RequestIntent,
            RetrievalMode,
            RetrievalPolicy,
            RoutingPreference,
            SovereigntyEnforcement,
            SovereigntyPolicy,
        )

        try:
            req_intent = RequestIntent(intent)
        except ValueError:
            req_intent = RequestIntent.GENERATE_CODE

        try:
            mode = ExecutionMode(execution_mode)
        except ValueError:
            mode = ExecutionMode.STANDARD

        try:
            routing = RoutingPreference(routing_preference)
        except ValueError:
            routing = RoutingPreference.AUTO

        try:
            sov = SovereigntyEnforcement(sovereignty_enforcement)
        except ValueError:
            sov = SovereigntyEnforcement.NONE

        try:
            ret = RetrievalMode(retrieval_mode)
        except ValueError:
            ret = RetrievalMode.DISABLED

        policy = ExecutionPolicy(
            mode=mode,
            routing=routing,
            sovereignty=SovereigntyPolicy(enforcement=sov),
            retrieval=RetrievalPolicy(mode=ret),
            latency=LatencyBudget(),
        )

        return EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=req_intent,
            prompt=prompt,
            adapter_name=adapter,
            execution_policy=policy,
            context=context_session,
        )

    @server.tool()
    async def auracode_generate(
        prompt: str,
        intent: str = "generate_code",
        execution_mode: str = "standard",
        routing_preference: str = "auto",
    ) -> str:
        """Generate code using AuraCode's engine."""
        req = _build_request(
            prompt,
            intent,
            execution_mode=execution_mode,
            routing_preference=routing_preference,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_plan(
        prompt: str,
        execution_mode: str = "standard",
    ) -> str:
        """Plan an architecture or implementation approach."""
        req = _build_request(prompt, "plan", execution_mode=execution_mode)
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_refactor(
        prompt: str,
        execution_mode: str = "standard",
    ) -> str:
        """Refactor code according to the given instructions."""
        req = _build_request(prompt, "refactor", execution_mode=execution_mode)
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_review_diff(
        prompt: str,
        sovereignty_enforcement: str = "none",
    ) -> str:
        """Review a code diff for correctness and security."""
        req = _build_request(
            prompt,
            "review_diff",
            sovereignty_enforcement=sovereignty_enforcement,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_security_review(
        prompt: str,
        sovereignty_enforcement: str = "warn",
    ) -> str:
        """Security-focused code review."""
        req = _build_request(
            prompt,
            "security_review",
            sovereignty_enforcement=sovereignty_enforcement,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_trace() -> str:
        """Return the last execution trace metadata."""
        # The engine doesn't store last response globally, so return
        # what the MCP server can observe.
        return "Use /trace in the REPL for execution trace. MCP trace support pending."

    @server.tool()
    async def auracode_explain(file_path: str) -> str:
        """Explain a file's contents."""
        from pathlib import Path

        from auracode.models.context import FileContext, SessionContext

        content: str | None = None
        p = Path(file_path)
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = None

        file_ctx = FileContext(
            path=str(p),
            content=content,
            language=p.suffix.lstrip(".") or None,
        )
        session = SessionContext(
            session_id=str(uuid.uuid4()),
            working_directory=str(p.parent),
            files=[file_ctx],
        )
        req = _build_request(
            f"Explain the contents of {file_path}",
            "explain_code",
            context_session=session,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_review(file_path: str) -> str:
        """Review code in a file."""
        from pathlib import Path

        from auracode.models.context import FileContext, SessionContext

        content: str | None = None
        p = Path(file_path)
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = None

        file_ctx = FileContext(
            path=str(p),
            content=content,
            language=p.suffix.lstrip(".") or None,
        )
        session = SessionContext(
            session_id=str(uuid.uuid4()),
            working_directory=str(p.parent),
            files=[file_ctx],
        )
        req = _build_request(
            f"Review the code in {file_path}",
            "review",
            context_session=session,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_models() -> str:
        """List available models."""
        models = await engine.router.list_models()
        if not models:
            return "No models available"
        return "\n".join(f"{m.model_id} ({m.provider})" for m in models)

    from pathlib import Path

    def _safe_resolve(file_path: str, working_dir: str) -> Path | None:
        """Resolve *file_path* and verify it lives under *working_dir*.

        Returns the resolved ``Path`` on success, or ``None`` if the path
        escapes the working directory (path-traversal protection).
        """
        base = Path(working_dir).resolve()
        target = (base / file_path).resolve()
        is_same = str(target) == str(base)
        is_under = str(target).startswith(str(base) + "\\") or str(target).startswith(
            str(base) + "/"
        )
        if not (is_same or is_under):
            return None
        return target

    @server.tool()
    async def auracode_read_file(path: str) -> str:
        """Read a file from the local filesystem."""
        working_dir = getattr(engine.config, "working_directory", ".")
        resolved = _safe_resolve(path, working_dir)
        if resolved is None:
            return f"Error: Path '{path}' is outside the working directory."

        if not resolved.is_file():
            return f"Error: {path} is not a file or does not exist."

        try:
            return resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"Error reading file: {e}"

    @server.tool()
    async def auracode_write_file(path: str, content: str) -> str:
        """Write a file to the local filesystem. Requires allow_file_write permission."""
        from auracode.utils.journal import FileJournal

        if not engine.config.permissions.allow_file_write:
            return "Error: File write permission denied. Restart with --allow-write."

        working_dir = getattr(engine.config, "working_directory", ".")
        resolved = _safe_resolve(path, working_dir)
        if resolved is None:
            return f"Error: Path '{path}' is outside the working directory."

        before_content = None
        if resolved.exists():
            before_content = resolved.read_text(encoding="utf-8", errors="replace")

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")

            # Record in journal (Task 2.3)
            if not hasattr(engine, "_journal"):
                engine._journal = FileJournal()
            engine._journal.record(str(resolved), "write", before_content, content)

            return f"Successfully wrote to {resolved}"
        except Exception as e:
            return f"Error writing file: {e}"

    @server.tool()
    async def auracode_edit_file(path: str, old_text: str, new_text: str) -> str:
        """Edit a file by replacing old_text with new_text. Requires allow_file_write."""
        from auracode.utils.journal import FileJournal

        if not engine.config.permissions.allow_file_write:
            return "Error: File write permission denied. Restart with --allow-write."

        working_dir = getattr(engine.config, "working_directory", ".")
        resolved = _safe_resolve(path, working_dir)
        if resolved is None:
            return f"Error: Path '{path}' is outside the working directory."

        if not resolved.is_file():
            return f"Error: {path} is not a file."

        content = resolved.read_text(encoding="utf-8", errors="replace")
        if old_text not in content:
            return f"Error: old_text not found in {path}"

        new_content = content.replace(old_text, new_text)
        try:
            resolved.write_text(new_content, encoding="utf-8")

            # Record in journal (Task 2.3)
            if not hasattr(engine, "_journal"):
                engine._journal = FileJournal()
            engine._journal.record(
                str(resolved),
                "edit",
                content,
                new_content,
                {"old_text": old_text, "new_text": new_text},
            )

            return f"Successfully edited {resolved}"
        except Exception as e:
            return f"Error editing file: {e}"

    @server.tool()
    async def auracode_bash(command: str) -> str:
        """Execute a shell command. Requires allow_shell_commands."""
        import shlex
        import subprocess
        import sys

        if not engine.config.permissions.allow_shell_commands:
            return "Error: Shell command permission denied. Restart with --allow-shell."

        if not engine.config.permissions.allow_destructive_shell_commands:
            import re

            destructive_patterns = [
                r"rm\s",
                r"mv\s",
                r"git\s+reset",
                r"git\s+clean",
                r"powershell",
                r"pwsh",
                r"del\s",
                r"rmdir\s",
                r"rd\s",
                r"format\s",
            ]
            if any(re.search(p, command) for p in destructive_patterns):
                return "Error: Destructive command blocked. Restart with --unsafe to allow."

        try:
            if sys.platform == "win32":
                # Windows: use cmd.exe explicitly instead of shell=True
                args = ["cmd.exe", "/c", command]
            else:
                # Unix: parse into argument list for safe execution
                args = shlex.split(command)
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return (
                f"Exit code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"
            )
        except Exception as e:
            return f"Error executing command: {e}"

    @server.tool()
    async def auracode_act(
        prompt: str,
        verify_command: str | None = None,
        max_attempts: int = 3,
    ) -> str:
        """Execute autonomous self-healing agent loop with verification gates."""
        from auracode.models.verification import RemediationBudget, VerificationCommand

        req = _build_request(prompt, "generate_code")
        verif = VerificationCommand(command=verify_command) if verify_command else None
        budget = RemediationBudget(max_attempts=max_attempts)
        try:
            result = await engine.execute_loop(req, verification=verif, budget=budget)
            lines = [f"Status: {result.status}"]
            if result.snapshot_id:
                lines.append(f"Rollback Snapshot: {result.snapshot_id}")
            if result.remediations:
                lines.append(f"Remediations: {len(result.remediations)} attempts")
            if result.final_response and result.final_response.content:
                lines.append(f"Output:\n{result.final_response.content}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error executing act loop: {e}"

    @server.tool()
    async def auracode_repomap(root_dir: str = ".", max_chars: int = 2048) -> str:
        """Generate lightweight deterministic AST structural repo-map (<2KB)."""
        from auracode.engine.repo_map import RepoMapBuilder

        try:
            builder = RepoMapBuilder(root_dir=root_dir, max_chars=max_chars)
            return builder.build()
        except Exception as e:
            return f"Error building repo-map: {e}"

    @server.tool()
    async def auracode_conflicts(root_dir: str = ".") -> str:
        """Scan workspace for active Git conflict marker blocks."""
        import json

        from auracode.git.conflict_resolver import ConflictMarkerParser

        try:
            conflicted = ConflictMarkerParser.find_conflicted_files(root_dir)
            files = [str(p) for p in conflicted]
            return json.dumps({"count": len(files), "files": files})
        except Exception as e:
            return f"Error scanning conflicts: {e}"

    @server.tool()
    async def auracode_resolve_conflicts(file_path: str) -> str:
        """Resolve 3-way merge conflict markers in a file using AI."""
        from pathlib import Path

        from auracode.git.conflict_resolver import MergeConflictResolver

        try:
            resolver = MergeConflictResolver(engine)
            success, msg = await resolver.resolve_file(Path(file_path))
            return f"Success: {success} - {msg}"
        except Exception as e:
            return f"Error resolving conflict: {e}"

    @server.tool()
    async def auracode_rollback(snapshot_id: str) -> str:
        """Roll back filesystem modifications to a snapshot checkpoint."""
        journal = getattr(engine, "_journal", None)
        if not journal:
            return "Error: No file journal active on engine."
        try:
            restored = journal.rollback_snapshot(snapshot_id)
            return (
                f"Successfully restored {len(restored)} files to snapshot {snapshot_id}: "
                f"{', '.join(restored)}"
            )
        except KeyError:
            return f"Error: Snapshot {snapshot_id} not found."
        except Exception as e:
            return f"Error during rollback: {e}"

    @server.tool()
    async def auracode_synthesize_commit(repo_path: str = ".") -> str:
        """Synthesize a Conventional Commit message from staged Git diffs."""
        from auracode.git.commit_synthesizer import CommitSynthesizer

        try:
            synthesizer = CommitSynthesizer(engine)
            msg = await synthesizer.synthesize_message(repo_path)
            return msg
        except Exception as e:
            return f"Error synthesizing commit: {e}"

    @server.tool()
    async def auracode_bundle_pack(source_dir: str, output_path: str) -> str:
        """Pack an application directory into a sealed .aurabundle archive."""
        from pathlib import Path

        from auracode.bundle.packager import BundlePackager

        try:
            packed = BundlePackager.pack(Path(source_dir), Path(output_path))
            info = BundlePackager.inspect(packed)
            return f"Packed bundle: {packed} (SHA-256: {info['sha256']})"
        except Exception as e:
            return f"Error packing bundle: {e}"

    @server.tool()
    async def auracode_bundle_validate(bundle_path: str) -> str:
        """Validate an app.manifest.json file or .aurabundle archive."""
        import json
        from pathlib import Path

        from auracode.bundle.manifest import ManifestValidator
        from auracode.bundle.packager import BundlePackager

        try:
            p = Path(bundle_path)
            if p.suffix in (".aurabundle", ".zip"):
                info = BundlePackager.inspect(p)
                return json.dumps({"valid": True, "bundle": info})
            is_valid, errors = ManifestValidator.validate_file(p)
            return json.dumps({"valid": is_valid, "errors": errors})
        except Exception as e:
            return f"Error validating bundle: {e}"

    @server.tool()
    async def auracode_ide_get_diagnostics(file_path: str = "", severity: str = "") -> str:
        """Expose active IDE compiler/linter diagnostics for near-zero latency self-healing."""
        from auracode.shim.ide_state import ide_state

        diags = ide_state.get_diagnostics(
            file_path=file_path or None,
            severity=severity or None,
        )
        if not diags:
            return "No active diagnostics found in connected IDE."

        lines = [f"Found {len(diags)} diagnostic(s):"]
        for d in diags:
            src = f" ({d.source})" if d.source else ""
            lines.append(
                f"- [{d.severity.upper()}] {d.file_path}:{d.line}:{d.col} - {d.message}{src}"
            )
        return "\n".join(lines)

    @server.tool()
    async def auracode_ide_get_active_buffer() -> str:
        """Expose current active IDE file buffer and selection for zero-latency inspection."""
        import json

        from auracode.shim.ide_state import ide_state

        buf = ide_state.get_active_buffer()
        if not buf:
            return "No active buffer recorded from connected IDE."
        return json.dumps(buf, indent=2)

    @server.tool()
    async def auracode_ide_get_open_buffers() -> str:
        """List all open editor buffers and diagnostic counts in connected IDE."""
        import json

        from auracode.shim.ide_state import ide_state

        buffers = ide_state.get_open_buffers()
        return json.dumps({"count": len(buffers), "buffers": buffers}, indent=2)

    @server.tool()
    async def auragrid_app_init(
        name: str,
        template: str = "tier1",
        runtime: str = "python",
        target_dir: str = "",
        managed_venv: str = "aurarouter",
        description: str = "",
    ) -> str:
        """Scaffold a new AuraGrid application manifest with schema auto-completion."""
        import argparse
        import json
        from pathlib import Path

        try:
            from auragrid.cli import _handle_init

            dest_dir = Path(target_dir) if target_dir else Path.cwd() / name
            args = argparse.Namespace(
                name=str(dest_dir),
                template=template,
                runtime=runtime,
                managed_venv=managed_venv,
                description=description,
            )
            _handle_init(args)
            manifest_path = dest_dir / "app.manifest.json"
            if manifest_path.exists():
                with open(manifest_path, encoding="utf-8") as f:
                    manifest_data = json.load(f)
                manifest_data["appId"] = name
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest_data, f, indent=2)
                return json.dumps(
                    {
                        "status": "success",
                        "path": str(manifest_path),
                        "template": template,
                        "manifest": manifest_data,
                    },
                    indent=2,
                )
            return f"Scaffolded in {dest_dir}"
        except Exception as e:
            return f"Error initializing app manifest: {e}"

    @server.tool()
    async def auragrid_app_validate(path: str = ".") -> str:
        """Validate an AuraGrid application manifest (app.manifest.json) or .agp package."""
        import json
        from pathlib import Path

        try:
            from auragrid.cli import _validate_target

            target = str(Path(path).resolve())
            is_valid, errors, warnings, manifest = _validate_target(target)
            return json.dumps(
                {
                    "valid": is_valid,
                    "target": target,
                    "appId": manifest.get("appId") if manifest else None,
                    "version": manifest.get("version") if manifest else None,
                    "errors": errors,
                    "warnings": warnings,
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"valid": False, "error": str(e)})

    @server.tool()
    async def auragrid_app_pack(
        directory: str = ".",
        output: str = "",
        sign_key: str = "",
        force: bool = False,
    ) -> str:
        """Package an application folder into a secure .agp bundle with SHA-256 checksums."""
        import json
        from pathlib import Path

        try:
            from auragrid.cli import _validate_target, build_agp_package

            src_dir = str(Path(directory).resolve())
            if not force:
                is_valid, errors, warnings, manifest = _validate_target(src_dir)
                if not is_valid:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": "Pre-flight validation failed",
                            "errors": errors,
                            "warnings": warnings,
                        },
                        indent=2,
                    )

            manifest_path = Path(src_dir) / "app.manifest.json"
            app_id = "app"
            version = "1.0.0"
            if manifest_path.exists():
                with open(manifest_path, encoding="utf-8") as f:
                    m = json.load(f)
                    app_id = m.get("appId", app_id)
                    version = m.get("version", version)

            out_path = output or str(Path(src_dir) / f"{app_id}-{version}.agp")
            key_path = sign_key if sign_key else None
            packed_count, excluded_count = build_agp_package(src_dir, out_path, key_path)

            return json.dumps(
                {
                    "status": "success",
                    "package_path": str(Path(out_path).resolve()),
                    "appId": app_id,
                    "version": version,
                    "files_packaged": packed_count,
                    "files_excluded": excluded_count,
                    "signed": bool(key_path),
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @server.tool()
    async def auragrid_app_deploy(
        package_path: str,
        url: str = "http://localhost:7077",
        reconcile: bool = True,
    ) -> str:
        """Deploy an application bundle (.agp) or manifest (.json) to an active AuraGrid node."""
        import json
        from pathlib import Path

        import httpx

        try:
            p = Path(package_path).resolve()
            if not p.exists():
                return json.dumps({"status": "error", "message": f"Package file not found: {p}"})

            headers = {
                "Content-Type": "application/octet-stream",
                "X-Deploy-Immediately": "true" if reconcile else "false",
            }

            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                with open(p, "rb") as f:
                    content = f.read()

                resp = await client.post(
                    f"{url.rstrip('/')}/api/catalog/upload",
                    headers=headers,
                    content=content,
                )

                if resp.status_code in (200, 201, 202):
                    return json.dumps(
                        {
                            "status": "success",
                            "http_status": resp.status_code,
                            "response": resp.json()
                            if resp.headers.get("content-type", "").startswith("application/json")
                            else resp.text,
                        },
                        indent=2,
                    )
                else:
                    return json.dumps(
                        {
                            "status": "error",
                            "http_status": resp.status_code,
                            "message": resp.text,
                        },
                        indent=2,
                    )
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @server.tool()
    async def auragrid_app_logs(
        mas_id: str = "",
        count: int = 50,
        url: str = "http://localhost:7077",
    ) -> str:
        """Fetch live logs from active AuraGrid node or MAS instance."""
        import json

        import httpx

        try:
            endpoint = (
                f"{url.rstrip('/')}/api/logs/{mas_id}" if mas_id else f"{url.rstrip('/')}/api/logs"
            )
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                resp = await client.get(endpoint)
                if resp.status_code == 200:
                    entries = resp.json() or []
                    recent = entries[-count:]
                    return json.dumps({"count": len(recent), "entries": recent}, indent=2)
                return json.dumps(
                    {"status": "error", "http_status": resp.status_code, "message": resp.text}
                )
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    @server.tool()
    async def auragrid_get_topology(
        url: str = "http://localhost:7077",
    ) -> str:
        """Query active AuraGrid cell topology, node health, active MAS instances,
        and registered services.
        """
        import json

        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                status_res = await client.get(f"{url.rstrip('/')}/api/status")
                services_res = await client.get(f"{url.rstrip('/')}/api/services")
                deployments_res = await client.get(f"{url.rstrip('/')}/api/deployments")

                topology: dict[str, Any] = {
                    "node_url": url,
                    "status": status_res.json() if status_res.status_code == 200 else None,
                    "services": services_res.json() if services_res.status_code == 200 else [],
                    "deployments": deployments_res.json()
                    if deployments_res.status_code == 200
                    else [],
                }
                return json.dumps(topology, indent=2)
        except Exception as e:
            return json.dumps({"status": "error", "node_url": url, "message": str(e)})

    return server
