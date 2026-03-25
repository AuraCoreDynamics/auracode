"""Click commands for the Codestral CLI adapter."""

from __future__ import annotations

import asyncio
import sys

import click

from auracode.adapters.codestral.formatter import format_response


def _build_raw_input(
    prompt: str,
    *,
    intent: str,
    context: tuple[str, ...] | None = None,
    model: str | None = None,
    prefix: str | None = None,
    suffix: str | None = None,
) -> dict:
    """Build the raw_input dict consumed by CodestralAdapter.translate_request."""
    raw: dict = {"prompt": prompt, "intent": intent}
    if context:
        raw["context_files"] = list(context)
    options: dict = {}
    if model:
        options["model"] = model
    if prefix is not None:
        options["prefix"] = prefix
    if suffix is not None:
        options["suffix"] = suffix
    if options:
        raw["options"] = options
    return raw


def _get_engine():
    """Bootstrap the AuraCode engine. Returns (engine, adapter) or exits with error."""
    try:
        from auracode.app import create_application

        engine, adapter_registry, _, _ = create_application()
        adapter = adapter_registry.get("codestral")
        if adapter is None:
            click.echo("Error: Codestral adapter not found in registry.", err=True)
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
    model: str | None = None,
    prefix: str | None = None,
    suffix: str | None = None,
) -> None:
    """Execute a single prompt through the engine and echo the result."""
    engine, adapter = _get_engine()
    raw_input = _build_raw_input(
        prompt,
        intent=intent,
        context=context,
        model=model,
        prefix=prefix,
        suffix=suffix,
    )

    async def _execute():
        request = await adapter.translate_request(raw_input)
        response = await engine.execute(request)
        return response

    response = asyncio.run(_execute())
    click.echo(format_response(response))


@click.group()
def codestral() -> None:
    """Codestral — inline code completion powered by AuraCode."""


@codestral.command()
@click.argument("prompt")
@click.option("--prefix", default=None, help="Code prefix for fill-in-the-middle.")
@click.option("--suffix", default=None, help="Code suffix for fill-in-the-middle.")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
def complete(
    prompt: str,
    prefix: str | None,
    suffix: str | None,
    context: tuple[str, ...],
    model: str | None,
) -> None:
    """Complete code from PROMPT."""
    _run_command(
        prompt, intent="complete", context=context, model=model, prefix=prefix, suffix=suffix
    )


@codestral.command()
@click.argument("prompt")
@click.option("--prefix", default=None, help="Code prefix for fill-in-the-middle.")
@click.option("--suffix", default=None, help="Code suffix for fill-in-the-middle.")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
def fill(
    prompt: str,
    prefix: str | None,
    suffix: str | None,
    context: tuple[str, ...],
    model: str | None,
) -> None:
    """Fill in code from PROMPT with prefix/suffix context."""
    _run_command(prompt, intent="fill", context=context, model=model, prefix=prefix, suffix=suffix)


@codestral.command()
@click.argument("prompt")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
def chat(prompt: str, context: tuple[str, ...], model: str | None) -> None:
    """Chat about code from PROMPT."""
    _run_command(prompt, intent="chat", context=context, model=model)
