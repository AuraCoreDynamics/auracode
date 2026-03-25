"""Click commands for the Copilot CLI adapter."""

from __future__ import annotations

import asyncio
import sys

import click

from auracode.adapters.copilot.formatter import format_response


def _build_raw_input(
    prompt: str,
    *,
    intent: str,
    context: tuple[str, ...] | None = None,
    model: str | None = None,
) -> dict:
    """Build the raw_input dict consumed by CopilotAdapter.translate_request."""
    raw: dict = {"prompt": prompt, "intent": intent}
    if context:
        raw["context_files"] = list(context)
    options: dict = {}
    if model:
        options["model"] = model
    if options:
        raw["options"] = options
    return raw


def _get_engine():
    """Bootstrap the AuraCode engine. Returns (engine, adapter) or exits with error."""
    try:
        from auracode.app import create_application

        engine, adapter_registry, _, _ = create_application()
        adapter = adapter_registry.get("copilot")
        if adapter is None:
            click.echo("Error: Copilot adapter not found in registry.", err=True)
            sys.exit(1)
        return engine, adapter
    except Exception as exc:
        click.echo(f"Error: Failed to bootstrap AuraCode engine: {exc}", err=True)
        sys.exit(1)


def _run_command(prompt: str, *, intent: str, context: tuple[str, ...], model: str | None) -> None:
    """Execute a single prompt through the engine and echo the result."""
    engine, adapter = _get_engine()
    raw_input = _build_raw_input(prompt, intent=intent, context=context, model=model)

    async def _execute():
        request = await adapter.translate_request(raw_input)
        response = await engine.execute(request)
        return response

    response = asyncio.run(_execute())
    click.echo(format_response(response))


@click.group()
def copilot() -> None:
    """Copilot — inline code suggestion powered by AuraCode."""


@copilot.command()
@click.argument("prompt")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
def suggest(prompt: str, context: tuple[str, ...], model: str | None) -> None:
    """Generate an inline code suggestion from PROMPT."""
    _run_command(prompt, intent="suggest", context=context, model=model)


@copilot.command()
@click.argument("prompt")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
def explain(prompt: str, context: tuple[str, ...], model: str | None) -> None:
    """Explain code described by PROMPT."""
    _run_command(prompt, intent="explain", context=context, model=model)


@copilot.command()
@click.argument("prompt")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
def commit(prompt: str, context: tuple[str, ...], model: str | None) -> None:
    """Generate a commit message from PROMPT."""
    _run_command(prompt, intent="commit", context=context, model=model)
