"""Unified CLI entry-point for AuraCode."""

from __future__ import annotations

import asyncio

import click


class _DefaultGroup(click.Group):
    """A Click group that invokes the REPL when no subcommand is given."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # If no args or only global options (--config), invoke the default (repl).
        # But if a known subcommand is present, let Click handle it normally.
        if not args or (args and args[0].startswith("-") and args[0] not in ("--help", "--version")):
            args = ["repl"] + args
        return super().parse_args(ctx, args)


@click.group(cls=_DefaultGroup)
@click.version_option(package_name="auracode")
@click.option("--config", type=click.Path(), default=None, help="Path to auracode.yaml")
@click.pass_context
def main(ctx: click.Context, config: str | None) -> None:
    """AuraCode -- terminal-native, vendor-agnostic AI coding assistant."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@main.command()
@click.pass_context
def repl(ctx: click.Context) -> None:
    """Launch the interactive console (default)."""
    from auracode.app import create_application
    from auracode.repl.console import AuraCodeConsole

    engine, adapters, _, prefs = create_application(ctx.obj.get("config_path"))
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
@click.option("--port", default=8741, help="Port for API shim server")
@click.option("--host", default="127.0.0.1", help="Bind address")
@click.pass_context
def serve(ctx: click.Context, port: int, host: str) -> None:
    """Start the OpenAI-compatible API shim server."""
    try:
        import aiohttp.web as web  # noqa: F401
    except ImportError:
        click.echo("Error: API shim requires 'aiohttp'. Install with: pip install auracode[api]")
        raise SystemExit(1)

    from auracode.app import create_application
    from auracode.shim.server import create_app

    engine, _, _, _ = create_application(ctx.obj.get("config_path"))
    click.echo(f"Starting AuraCode API shim on {host}:{port}")
    app = create_app(engine)
    import aiohttp.web as web

    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
