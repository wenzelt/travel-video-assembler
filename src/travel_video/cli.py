from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from travel_video.logging_setup import setup_logging

app = typer.Typer(name="travel-video", help="Assemble travel video clips into a polished MKV.")
console = Console()

_CONFIG_OPT = Annotated[Path, typer.Option("--config", help="Path to config.yaml")]
_DEFAULT_CONFIG = Path("config.yaml")


@app.command()
def render(
    input: Annotated[Path, typer.Option("--input", help="Folder of input clips")],
    output: Annotated[Path, typer.Option("--output", help="Output MKV path")],
    config: _CONFIG_OPT = _DEFAULT_CONFIG,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print FFmpeg commands without running")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Render all clips in INPUT into a single travel video at OUTPUT."""
    setup_logging(verbose)
    raise NotImplementedError("render not yet implemented")


@app.command()
def plan(
    input: Annotated[Path, typer.Option("--input", help="Folder of input clips")],
    config: _CONFIG_OPT = _DEFAULT_CONFIG,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Show the planned clip timeline without rendering."""
    setup_logging(verbose)
    raise NotImplementedError("plan not yet implemented")


@app.command()
def inspect(
    file: Annotated[Path, typer.Argument(help="Video file to inspect")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Show metadata for a single video file."""
    setup_logging(verbose)
    raise NotImplementedError("inspect not yet implemented")


if __name__ == "__main__":
    app()
