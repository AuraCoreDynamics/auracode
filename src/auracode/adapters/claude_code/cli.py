"""Click commands for the Claude Code CLI adapter."""

from __future__ import annotations

import asyncio
import sys

import click

from auracode.adapters.claude_code.formatter import format_response


def _build_raw_input(
    prompt: str,
    *,
    intent: str,
    context: tuple[str, ...] | None = None,
    model: str | None = None,
) -> dict:
    """Build the raw_input dict consumed by ClaudeCodeAdapter.translate_request."""
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
        adapter = adapter_registry.get("claude-code")
        if adapter is None:
            click.echo("Error: Claude Code adapter not found in registry.", err=True)
            sys.exit(1)
        return engine, adapter
    except Exception as exc:
        click.echo(f"Error: Failed to bootstrap AuraCode engine: {exc}", err=True)
        sys.exit(1)


def _run_command(
    prompt: str, *, intent: str, context: tuple[str, ...], model: str | None, json_mode: bool
) -> None:
    """Execute a single prompt through the engine and echo the result."""
    engine, adapter = _get_engine()
    raw_input = _build_raw_input(prompt, intent=intent, context=context, model=model)

    async def _execute():
        request = await adapter.translate_request(raw_input)
        response = await engine.execute(request)
        return response

    response = asyncio.run(_execute())
    click.echo(format_response(response, json_mode=json_mode))


def _read_file_content(file_path: str) -> str | None:
    """Read file content, returning None on error."""
    from pathlib import Path

    p = Path(file_path)
    if not p.is_file():
        click.echo(f"Warning: File not found: {file_path}", err=True)
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        click.echo(f"Warning: Could not read {file_path}: {exc}", err=True)
        return None


@click.group()
def claude() -> None:
    """Claude Code — AI coding assistant powered by AuraCode."""


@claude.command()
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output response as JSON.")
def chat(context: tuple[str, ...], model: str | None, json_mode: bool) -> None:
    """Interactive REPL mode."""
    engine, adapter = _get_engine()
    click.echo("AuraCode Claude REPL — type your prompts below. Press Ctrl+C to exit.\n")
    try:
        while True:
            try:
                prompt = click.prompt(">>>", prompt_suffix=" ")
            except click.Abort:
                break
            raw_input = _build_raw_input(prompt, intent="chat", context=context, model=model)

            async def _execute():
                request = await adapter.translate_request(raw_input)
                response = await engine.execute(request)
                return response

            response = asyncio.run(_execute())
            click.echo(format_response(response, json_mode=json_mode))
    except KeyboardInterrupt:
        click.echo("\nExiting.")


@claude.command()
@click.argument("prompt")
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="File(s) to include as context.",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output response as JSON.")
def do(prompt: str, context: tuple[str, ...], model: str | None, json_mode: bool) -> None:
    """One-shot code generation from PROMPT."""
    _run_command(prompt, intent="do", context=context, model=model, json_mode=json_mode)


@claude.command()
@click.argument("file", type=click.Path(exists=False))
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="Additional context file(s).",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output response as JSON.")
def explain(file: str, context: tuple[str, ...], model: str | None, json_mode: bool) -> None:
    """Explain the contents of FILE."""
    file_content = _read_file_content(file)
    if file_content is not None:
        prompt = f"Explain the following file ({file}):\n\n{file_content}"
    else:
        prompt = f"Explain {file}"
    # Include the target file in context so the adapter can build FileContext
    all_context = (file,) + context
    _run_command(prompt, intent="explain", context=all_context, model=model, json_mode=json_mode)


@claude.command()
@click.argument("file", type=click.Path(exists=False))
@click.option(
    "--context",
    "-c",
    multiple=True,
    type=click.Path(exists=False),
    help="Additional context file(s).",
)
@click.option("--model", "-m", default=None, help="Model to use for inference.")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output response as JSON.")
def review(file: str, context: tuple[str, ...], model: str | None, json_mode: bool) -> None:
    """Review code in FILE."""
    file_content = _read_file_content(file)
    if file_content is not None:
        prompt = f"Review the following code ({file}):\n\n{file_content}"
    else:
        prompt = f"Review {file}"
    all_context = (file,) + context
    _run_command(prompt, intent="review", context=all_context, model=model, json_mode=json_mode)
