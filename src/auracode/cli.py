"""Unified CLI entry-point for AuraCode."""

from __future__ import annotations

import asyncio

import click

from auracode import __version__
from auracode.ci.cli import ci


class _DefaultGroup(click.Group):
    """A Click group that invokes the REPL when no subcommand is given."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # If no args or only global options (--config), invoke the default (repl).
        # But if a known subcommand is present, let Click handle it normally.
        not_subcommand = args and args[0].startswith("-")
        excluded = ("--help", "--version")
        if not args or (not_subcommand and args[0] not in excluded):
            args = ["repl"] + args
        return super().parse_args(ctx, args)


@click.group(cls=_DefaultGroup)
@click.version_option(version=__version__, package_name="auracode")
@click.option("--config", type=click.Path(), default=None, help="Path to auracode.yaml")
@click.option("--allow-write", is_flag=True, default=False, help="Allow agent to write files.")
@click.option(
    "--allow-shell", is_flag=True, default=False, help="Allow agent to execute shell commands."
)
@click.option("--unsafe", is_flag=True, default=False, help="Allow destructive shell commands.")
@click.pass_context
def main(
    ctx: click.Context,
    config: str | None,
    allow_write: bool,
    allow_shell: bool,
    unsafe: bool,
) -> None:
    """AuraCode -- terminal-native, vendor-agnostic AI coding assistant."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config
    ctx.obj["permissions"] = {
        "allow_file_write": allow_write,
        "allow_shell_commands": allow_shell,
        "allow_destructive_shell_commands": unsafe,
    }


@main.command()
@click.pass_context
def repl(ctx: click.Context) -> None:
    """Launch the interactive console (default)."""
    from auracode.app import create_application
    from auracode.repl.console import AuraCodeConsole

    engine, adapters, _, prefs = create_application(
        ctx.obj.get("config_path"),
        permissions_override=ctx.obj.get("permissions"),
    )
    console = AuraCodeConsole(
        engine,
        adapters,
        default_adapter_name=engine.config.default_adapter,
        preferences_manager=prefs,
    )
    console.run_sync()


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Check AuraCode health and show component status."""
    from auracode.app import create_application

    engine, adapters, backends, _ = create_application(ctx.obj.get("config_path"))
    click.echo("AuraCode Status")
    click.echo(f"  Adapters: {', '.join(adapters.list_adapters()) or 'none'}")
    healthy = asyncio.run(engine.router.health_check())
    click.echo(f"  Router: {'healthy' if healthy else 'unavailable'}")
    models = asyncio.run(engine.router.list_models())
    click.echo(f"  Models: {len(models)} available")


@main.command()
@click.pass_context
def models(ctx: click.Context) -> None:
    """List available models."""
    from auracode.app import create_application

    engine, _, _, _ = create_application(ctx.obj.get("config_path"))
    model_list = asyncio.run(engine.router.list_models())
    if not model_list:
        click.echo("No models available.")
        return
    for m in model_list:
        tags = f" [{', '.join(m.tags)}]" if m.tags else ""
        click.echo(f"  {m.model_id} ({m.provider}){tags}")


@main.command()
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """Run AuraCode Model Context Protocol (MCP) server over standard I/O (stdio)."""
    from auracode.app import create_application
    from auracode.mcp_server import run_stdio_server

    engine, _, _, _ = create_application(
        ctx.obj.get("config_path"),
        permissions_override=ctx.obj.get("permissions"),
    )
    run_stdio_server(engine)


@main.command()
@click.option("--port", default=8741, help="Port for API shim server")
@click.option("--host", default="0.0.0.0", help="Bind address")
@click.pass_context
def serve(ctx: click.Context, port: int, host: str) -> None:
    """Start the OpenAI-compatible API shim server (Standalone offline mode)."""
    try:
        import aiohttp.web as web  # noqa: F401
    except ImportError:
        click.echo("Error: API shim requires 'aiohttp'. Install with: pip install auracode[api]")
        raise SystemExit(1)

    from auracode.app import create_application
    from auracode.catalog_registration import CatalogRegistrar
    from auracode.shim.server import create_app

    engine, _, _, _ = create_application(ctx.obj.get("config_path"))
    click.echo(f"Starting AuraCode API shim on {host}:{port}")
    app = create_app(engine)

    mcp_endpoint = f"http://{host}:{port}"
    registrar = CatalogRegistrar(
        mcp_endpoint=mcp_endpoint,
        aurarouter_url=engine.config.aurarouter_url,
    )

    async def on_startup(_app: web.Application) -> None:
        task = asyncio.create_task(registrar.start_with_retry())
        task.add_done_callback(
            lambda t: (
                t.exception()
                and __import__("logging")
                .getLogger(__name__)
                .error("Catalog registration task failed: %s", t.exception())
                if not t.cancelled() and t.exception()
                else None
            )
        )

    async def on_shutdown(_app: web.Application) -> None:
        await registrar.stop()

    import aiohttp.web as web

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host=host, port=port)


@main.command()
@click.option(
    "--preflight-command",
    "-p",
    default=None,
    help="Verification command to execute before triggering lifecycle restarts.",
)
@click.pass_context
def poller(ctx: click.Context, preflight_command: str | None) -> None:
    """Start the Git post-receive poller for collaborative offline coding."""
    import time

    from auracode.git.mirror_service import GitMirrorService
    from auracode.git.poller import GitMirrorPoller
    from auracode.grid.lifecycle_client import LifecycleManagementClient

    mirror = GitMirrorService()
    client = LifecycleManagementClient()
    poller = GitMirrorPoller(
        mirror,
        client,
        preflight_command=preflight_command,
    )

    click.echo("Starting AuraCode Git poller...")
    poller.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("Stopping AuraCode Git poller...")
        poller.stop()


@main.command()
@click.option("--port", default=8741, help="Port for Mission Command web UI")
@click.option("--host", default="0.0.0.0", help="Bind address")
@click.option("--open-browser", is_flag=True, default=False, help="Open browser on start")
@click.option("--auth-token", default=None, help="Bearer token required for API and remote UI")
@click.pass_context
def ui(
    ctx: click.Context,
    port: int,
    host: str,
    open_browser: bool,
    auth_token: str | None,
) -> None:
    """Launch the Mission Command Web Flight Deck (Standalone offline mode)."""
    try:
        import aiohttp.web as web  # noqa: F401
    except ImportError:
        click.echo(
            "Error: Mission Command UI requires 'aiohttp'. Install with: pip install auracode[api]"
        )
        raise SystemExit(1)

    import webbrowser

    from auracode.app import create_application
    from auracode.shim.server import create_app

    engine, _, _, _ = create_application(ctx.obj.get("config_path"))
    if auth_token:
        engine.config.auth_token = auth_token

    app = create_app(engine)
    ui_url = f"http://{host}:{port}/ui"
    click.echo(f"AuraCode Mission Command running at {ui_url}")

    if open_browser:
        webbrowser.open(ui_url)

    import aiohttp.web as web

    web.run_app(app, host=host, port=port)


@main.group()
def fleet() -> None:
    """Manage multi-project workspaces in Mission Command."""


@fleet.command("add")
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
def fleet_add(path: str) -> None:
    """Register a new workspace directory."""
    from auracode.engine.fleet_manager import FleetWorkspaceManager

    mgr = FleetWorkspaceManager()
    info = mgr.register(path)
    click.echo(f"Registered workspace: {info['name']} ({info['path']}) [branch: {info['branch']}]")


@fleet.command("remove")
@click.argument("path", type=click.Path())
def fleet_remove(path: str) -> None:
    """Unregister a workspace directory."""
    from auracode.engine.fleet_manager import FleetWorkspaceManager

    mgr = FleetWorkspaceManager()
    if mgr.unregister(path):
        click.echo(f"Unregistered workspace: {path}")
    else:
        click.echo(f"Workspace not found in fleet: {path}", err=True)


@fleet.command("list")
def fleet_list() -> None:
    """List all registered workspaces."""
    import asyncio

    from auracode.engine.fleet_manager import FleetWorkspaceManager

    mgr = FleetWorkspaceManager()
    workspaces = asyncio.run(mgr.list_workspaces())
    click.echo(f"Registered Workspaces ({len(workspaces)}):")
    for ws in workspaces:
        status_flag = "DIRTY" if ws["dirty"] else "CLEAN"
        conflict_flag = f" [conflicts: {ws['conflict_count']}]" if ws["conflict_count"] > 0 else ""
        click.echo(
            f"  - {ws['name']:<20} {ws['path']} ({ws['branch']}) [{status_flag}]{conflict_flag}"
        )


@main.group()
def bundle() -> None:
    """Manage AuraGrid application bundles (.aurabundle)."""


@bundle.command("pack")
@click.option(
    "--source",
    "-s",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    help="Source directory containing app.manifest.json.",
)
@click.option(
    "--out",
    "-o",
    type=click.Path(),
    default=None,
    help="Output .aurabundle archive path.",
)
def bundle_pack(source: str, out: str | None) -> None:
    """Pack an application directory into a sealed .aurabundle archive."""
    from pathlib import Path

    from auracode.bundle.packager import BundlePackager

    src_path = Path(source).resolve()
    out_path = Path(out).resolve() if out else src_path / f"{src_path.name}.aurabundle"
    try:
        res = BundlePackager.pack(source_dir=src_path, output_file=out_path)
        click.echo(f"Successfully packed bundle: {res}")
    except Exception as exc:
        click.echo(f"Error packing bundle: {exc}", err=True)
        raise SystemExit(1)


@bundle.command("validate")
@click.argument("target", default="app.manifest.json", type=click.Path(exists=True))
def bundle_validate(target: str) -> None:
    """Validate an app.manifest.json file or .aurabundle archive."""
    from pathlib import Path

    from auracode.bundle.manifest import ManifestValidator
    from auracode.bundle.packager import BundlePackager

    path = Path(target).resolve()
    if path.suffix in (".aurabundle", ".zip"):
        try:
            info = BundlePackager.inspect(path)
            gov = info.get("cell_governance", {})
            click.echo(f"Bundle is valid: {info['name']} v{info['version']} ({info['app_id']})")
            click.echo(f"  SHA-256: {info['sha256']}")
            click.echo(f"  Files: {info['file_count']}")
            click.echo(f"  Target cells: {', '.join(gov.get('target_cells', [])) or 'any'}")
            click.echo(f"  Required OS: {gov.get('required_os', 'any')}")
            click.echo(f"  Min RAM: {gov.get('min_ram_mb', 512)} MB")
        except Exception as exc:
            click.echo(f"Invalid bundle: {exc}", err=True)
            raise SystemExit(1)
    else:
        is_valid, errors = ManifestValidator.validate_file(path)
        if is_valid:
            click.echo(f"Manifest {path.name} is valid.")
        else:
            click.echo(f"Manifest {path.name} has errors:", err=True)
            for err in errors:
                click.echo(f"  - {err}", err=True)
            raise SystemExit(1)


@bundle.command("inspect")
@click.argument("bundle_path", type=click.Path(exists=True))
def bundle_inspect(bundle_path: str) -> None:
    """Inspect the contents and governance requirements of a bundle."""
    from pathlib import Path

    from auracode.bundle.packager import BundlePackager

    path = Path(bundle_path).resolve()
    try:
        info = BundlePackager.inspect(path)
        click.echo(f"Bundle: {info['name']} (ID: {info['app_id']}, Version: {info['version']})")
        click.echo(f"SHA-256: {info['sha256']}")
        click.echo(f"Files ({info['file_count']}):")
        for f in info["files"][:20]:
            click.echo(f"  - {f}")
        if len(info["files"]) > 20:
            click.echo(f"  ... and {len(info['files']) - 20} more")
    except Exception as exc:
        click.echo(f"Error inspecting bundle: {exc}", err=True)
        raise SystemExit(1)


main.add_command(ci)

if __name__ == "__main__":
    main()
