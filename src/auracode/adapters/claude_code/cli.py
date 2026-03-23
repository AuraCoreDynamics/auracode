"""Click commands for the Claude Code CLI adapter."""

from __future__ import annotations

import json
import sys

import click

from auracode.adapters.claude_code.formatter import format_response
from auracode.models.request import EngineResponse


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


def _placeholder_response(prompt: str) -> EngineResponse:
    """Return a placeholder EngineResponse until the engine is wired in."""
    return EngineResponse(
        request_id="placeholder",
        content=f"[engine not connected] received prompt: {prompt}",
    )


@click.group()
def claude() -> None:
    """Claude Code — AI coding assistant powered by AuraCode."""


@claude.command()
@click.option("--context", "-c", multiple=True, type=click.Path(exists=False), help="File(s) to include as context.")
@click.option("--model", "-m", default=None, help="Model to use for inference.")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output response as JSON.")
def chat(context: tuple[str, ...], model: str | None, json_mode: bool) -> None:
    """Interactive REPL mode (engine wired in TG6)."""
    click.echo("AuraCode Claude REPL — engine integration pending (TG6).")
    click.echo("Type your prompts below. Press Ctrl+C to exit.\n")
    try:
        while True:
            try:
                prompt = click.prompt(">>>", prompt_suffix=" ")
            except click.Abort:
                break
            response = _placeholder_response(prompt)
            click.echo(format_response(response, json_mode=json_mode))
    except KeyboardInterrupt:
        click.echo("\nExiting.")


@claude.command()
@click.argument("prompt")
@click.option("--context", "-c", multiple=True, type=click.Path(exists=False), help="File(s) to include as context.")
@click.option("--model", "-m", default=None, help="Model to use for inference.")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output response as JSON.")
def do(prompt: str, context: tuple[str, ...], model: str | None, json_mode: bool) -> None:
    """One-shot code generation from PROMPT."""
    response = _placeholder_response(prompt)
    click.echo(format_response(response, json_mode=json_mode))


@claude.command()
@click.argument("file", type=click.Path(exists=False))
@click.option("--context", "-c", multiple=True, type=click.Path(exists=False), help="Additional context file(s).")
@click.option("--model", "-m", default=None, help="Model to use for inference.")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output response as JSON.")
def explain(file: str, context: tuple[str, ...], model: str | None, json_mode: bool) -> None:
    """Explain the contents of FILE."""
    response = _placeholder_response(f"Explain {file}")
    click.echo(format_response(response, json_mode=json_mode))


@claude.command()
@click.argument("file", type=click.Path(exists=False))
@click.option("--context", "-c", multiple=True, type=click.Path(exists=False), help="Additional context file(s).")
@click.option("--model", "-m", default=None, help="Model to use for inference.")
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output response as JSON.")
def review(file: str, context: tuple[str, ...], model: str | None, json_mode: bool) -> None:
    """Review code in FILE."""
    response = _placeholder_response(f"Review {file}")
    click.echo(format_response(response, json_mode=json_mode))
