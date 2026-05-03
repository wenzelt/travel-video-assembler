from __future__ import annotations

import subprocess
from datetime import date as _Date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from travel_video import metadata, planner, renderer, scanner
from travel_video.config import Config
from travel_video.deps import check_dependencies
from travel_video.logging_setup import setup_logging
from travel_video.models import Clip, DaySeparator, TimelineItem

app = typer.Typer(name="travel-video", help="Assemble travel video clips into a polished MKV.")
console = Console()

_CONFIG_OPT = Annotated[Path, typer.Option("--config", help="Path to config.yaml")]
_DEFAULT_CONFIG = Path("config.yaml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_duration(seconds: float) -> str:
    """Format *seconds* as ``MM:SS``."""
    total = int(round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def _extract_clips(paths: list[Path]) -> list[Clip]:
    clips: list[Clip] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Reading metadata…", total=None)
        for path in paths:
            progress.update(task_id, description=f"Reading {path.name}…")
            clips.append(metadata.extract(path))
    return clips


def _print_timeline(timeline: list[TimelineItem]) -> None:
    """Print a rich table summarizing the timeline."""
    table = Table(title="Planned Timeline", show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Type", width=10)
    table.add_column("Date", width=12)
    table.add_column("Duration", width=8)
    table.add_column("Resolution", width=12)
    table.add_column("GPS", width=22)
    table.add_column("Path")

    clip_number = 0
    total_duration = 0.0
    day_set: set[_Date] = set()

    for item in timeline:
        if isinstance(item, DaySeparator):
            table.add_row(
                "—",
                "[dim]day break[/dim]",
                str(item.date),
                "3s",
                "—",
                "—",
                "—",
                style="dim",
            )
        elif isinstance(item, Clip):
            clip_number += 1
            total_duration += item.duration_s
            day_set.add(item.creation_time.date())

            gps = f"{item.gps_lat:.4f}, {item.gps_lon:.4f}" if item.has_gps else "—"
            table.add_row(
                str(clip_number),
                "clip",
                str(item.creation_time.date()),
                _fmt_duration(item.duration_s),
                f"{item.width}x{item.height}",
                gps,
                item.path.name,
            )

    console.print(table)
    console.print(
        f"\nTotal clips: [bold]{clip_number}[/bold]  "
        f"Total days: [bold]{len(day_set)}[/bold]  "
        f"Total duration: [bold]{_fmt_duration(total_duration)}[/bold]"
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def render(
    input: Annotated[Path, typer.Option("--input", help="Folder of input clips")],
    output: Annotated[Path, typer.Option("--output", help="Output MKV path")],
    config: _CONFIG_OPT = _DEFAULT_CONFIG,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print FFmpeg commands without running")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Render all clips in INPUT into a single travel video at OUTPUT."""
    setup_logging(verbose)
    check_dependencies()

    # --- Validate --input ---------------------------------------------------
    if not input.exists() or not input.is_dir():
        raise typer.BadParameter(
            f"Input path '{input}' does not exist or is not a directory.",
            param_hint="'--input'",
        )

    # --- Validate --config ---------------------------------------------------
    if not config.exists():
        raise typer.BadParameter(
            f"Config file '{config}' does not exist.",
            param_hint="'--config'",
        )

    # --- Ensure output parent directory exists --------------------------------
    output.parent.mkdir(parents=True, exist_ok=True)

    # --- Load config ----------------------------------------------------------
    cfg = Config.load(config)

    # --- Scan -----------------------------------------------------------------
    paths = scanner.scan(input)

    # --- Early return when no clips found ------------------------------------
    if not paths:
        console.print("[yellow]Warning: no video clips found in the input directory.[/yellow]")
        return

    # --- Extract metadata with progress bar ----------------------------------
    clips = _extract_clips(paths)

    # --- Build timeline -------------------------------------------------------
    timeline = planner.build_timeline(clips)

    # --- Print summary --------------------------------------------------------
    _print_timeline(timeline)
    console.print()

    # --- Render ---------------------------------------------------------------
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Rendering video segments…", total=len(timeline))
        
        def _update_progress() -> None:
            progress.advance(task_id)

        renderer.render(timeline, cfg, output, dry_run=dry_run, progress_callback=_update_progress)

    # --- Success message ------------------------------------------------------
    console.print(f"\n[green]✔ Successfully rendered to:[/green] {output}")


@app.command()
def plan(
    input: Annotated[Path, typer.Option("--input", help="Folder of input clips")],
    config: _CONFIG_OPT = _DEFAULT_CONFIG,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Show the planned clip timeline without rendering."""
    setup_logging(verbose)

    # --- Validate --input ---------------------------------------------------
    if not input.exists() or not input.is_dir():
        raise typer.BadParameter(
            f"Input path '{input}' does not exist or is not a directory.",
            param_hint="'--input'",
        )

    # --- Validate --config ---------------------------------------------------
    if not config.exists():
        raise typer.BadParameter(
            f"Config file '{config}' does not exist.",
            param_hint="'--config'",
        )

    # --- Load config ---------------------------------------------------------
    Config.load(config)

    # --- Scan ----------------------------------------------------------------
    paths = scanner.scan(input)

    # --- Extract metadata with progress bar ----------------------------------
    clips = _extract_clips(paths)

    # --- Build timeline ------------------------------------------------------
    timeline = planner.build_timeline(clips)

    # --- Render table --------------------------------------------------------
    _print_timeline(timeline)


@app.command()
def inspect(
    file: Annotated[Path, typer.Argument(help="Video file to inspect")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Show metadata for a single video file."""
    setup_logging(verbose)

    # --- Validate file -------------------------------------------------------
    if not file.exists() or not file.is_file():
        raise typer.BadParameter(
            f"File '{file}' does not exist or is not a regular file.",
            param_hint="'file'",
        )

    # --- Extract metadata ----------------------------------------------------
    clip = metadata.extract(file)

    # --- Build key/value table for the panel ---------------------------------
    kv_table = Table(show_header=False, box=None, padding=(0, 1))
    kv_table.add_column("Key", style="bold cyan", no_wrap=True)
    kv_table.add_column("Value")

    gps = f"{clip.gps_lat:.6f}, {clip.gps_lon:.6f}" if clip.has_gps else "—"
    rows = [
        ("path", str(clip.path)),
        ("duration", _fmt_duration(clip.duration_s)),
        ("creation_time", str(clip.creation_time)),
        ("width", str(clip.width)),
        ("height", str(clip.height)),
        ("rotation", str(clip.rotation)),
        ("gps", gps),
        ("is_vertical", str(clip.is_vertical)),
    ]
    for key, value in rows:
        kv_table.add_row(key, value)

    console.print(Panel(kv_table, title=f"[bold]{file.name}[/bold]", expand=False))

    # --- Raw ExifTool output -------------------------------------------------
    try:
        result = subprocess.run(  # noqa: S603 — args are a literal list; file path is already validated
            ["exiftool", "-j", str(file)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        console.print(
            Panel(
                "[red]exiftool not found — install it via: brew install exiftool[/red]",
                title="Raw ExifTool output",
                expand=False,
            )
        )
        return
    if result.returncode == 0:
        console.print(Panel(result.stdout.strip(), title="Raw ExifTool output", expand=False))
    else:
        console.print(
            Panel(
                f"[red]exiftool exited with code {result.returncode}[/red]\n{result.stderr}",
                title="Raw ExifTool output",
                expand=False,
            )
        )


if __name__ == "__main__":
    app()
