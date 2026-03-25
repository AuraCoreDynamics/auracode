"""Click commands for the Aider CLI adapter."""

from __future__ import annotations

import asyncio
import sys

import click

from auracode.adapters.aider.formatter import format_response


def _build_raw_input(
    prompt: str,
    *,
    intent: str,
    context: tuple[str, ...] | None = None,
    readonly: tuple[str, ...] | None = None,
    model: str | None = None,
) -> dict:
    """Build the raw_input dict consumed by AiderAdapter.translate_request."""
    raw: dict = {"prompt": prompt, "intent": intent}
    if context:
        raw["context_files"] = list(context)
    options: dict = {}
    if readonly:
        options["readonly_files"] = list(readonly)
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
        adapter = adapter_registry.get("aider")
        if adapter is None:
            click.echo("Error: Aider adapter not found in registry.", err=True)
            sys.exit(1)
        return engine, adapter
    except Exception as exc:
        click.echo(f"Error: Failed to bootstrap AuraCode engine: {exc}", err=True)
        sys.exit(1)


def _run_command(
    prompt: str,
    *,
    intent: str,
    context: tuple[str, ...],
    readonly: tuple[str, ...] = (),
    model: str | None = None,
) -> None:
    """Execute a single prompt through the engine and echo the result."""
    engine, adapter = _get_engine()
    raw_input = _build_raw_input(
        prompt,
        intent=intent,
        context=context,
        readonly=readonly,
        model=model,
    )

    async def _execute():
        request = await adapter.translate_request(raw_input)
        response = await engine.execute(request)
        return response

    response = asyncio.run(_execute())
    click.echo(format_response(response))


@click.group()
def aider() -> None:
    """Aider — file-diffing code assistant powered by AuraCode."""


@aider.command()
@click.argument("prompt")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as editable context.",
)
@click.option(
    "--readonly",
    "-r",
    multiple=True,
    type=click.Path(exists=False),
    help="Read-only file(s) for reference.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
def code(
    prompt: str, context: tuple[str, ...], readonly: tuple[str, ...], model: str | None
) -> None:
    """Edit code based on PROMPT."""
    _run_command(prompt, intent="code", context=context, readonly=readonly, model=model)


@aider.command()
@click.argument("prompt")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
def ask(prompt: str, context: tuple[str, ...], model: str | None) -> None:
    """Ask a question about PROMPT."""
    _run_command(prompt, intent="ask", context=context, model=model)


@aider.command()
@click.argument("prompt")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
def architect(prompt: str, context: tuple[str, ...], model: str | None) -> None:
    """Plan an architecture change based on PROMPT."""
    _run_command(prompt, intent="architect", context=context, model=model)
