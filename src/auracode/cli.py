"""Unified CLI entry-point for AuraCode."""

from __future__ import annotations

import asyncio

import click


@click.group()
@click.version_option(package_name="auracode")
@click.option("--config", type=click.Path(), default=None, help="Path to auracode.yaml")
@click.pass_context
def main(ctx: click.Context, config: str | None) -> None:
    """AuraCode -- terminal-native, vendor-agnostic AI coding assistant."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Check AuraCode health and show component status."""
    from auracode.app import create_application

    engine, adapters, backends = create_application(ctx.obj.get("config_path"))
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

    engine, _, _ = create_application(ctx.obj.get("config_path"))
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

    engine, _, _ = create_application(ctx.obj.get("config_path"))
    click.echo(f"Starting AuraCode API shim on {host}:{port}")
    app = create_app(engine)
    import aiohttp.web as web

    web.run_app(app, host=host, port=port)


# -----------------------------------------------------------------------
# Mount adapter CLI groups
# -----------------------------------------------------------------------

def _mount_adapter_clis() -> None:
    """Import known adapter CLI groups and mount them on ``main``."""
    try:
        from auracode.adapters.claude_code.cli import claude

        main.add_command(claude, name="claude")
    except ImportError:
        pass


_mount_adapter_clis()


if __name__ == "__main__":
    main()
