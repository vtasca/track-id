import asyncio
import importlib.metadata
from pathlib import Path
from typing import NoReturn, Optional

import typer

from .display import (
    console,
    display_download_complete,
    display_error,
    display_file_info_table,
    display_metadata_table,
    display_search_results,
    display_slsk_candidates,
    display_unified_enrichment_results,
    display_unified_search_results,
)
from .mp3_utils import MP3File
from .unified_api import enrich as unified_enrich
from .unified_api import search as unified_search

def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        try:
            version = importlib.metadata.version("track-id")
            console.print(f"track-id version {version}")
        except importlib.metadata.PackageNotFoundError:
            console.print("track-id version unknown (package not installed)")
        raise typer.Exit()

app = typer.Typer(
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]}
)

@app.callback()
def root_callback(
    version: bool = typer.Option(
        False, 
        "-V", 
        "--version", 
        help="Show version and exit",
        callback=version_callback,
        is_eager=True
    )
) -> None:
    """Track ID - MP3 metadata enrichment tool"""
    pass

@app.command()
def search(
    search_text: str = typer.Argument(..., help="The text to search for"),
    top: int = typer.Option(3, "--top", "-t", help="Number of top results to show per source (default: 5)")
) -> None:
    """Search for tracks across all available data sources (Bandcamp, MusicBrainz)"""

    try:
        results = unified_search(search_text)
        display_unified_search_results(results, top_n=top)
    except Exception as e:
        display_error(str(e))
        raise typer.Exit(1)

@app.command()
def info(file_path: str = typer.Argument(..., help="Path to the MP3 file")) -> None:
    """Display information about an MP3 file"""
    
    try:
        # Create MP3File instance and get information
        mp3_file = MP3File(file_path)
        
        # Display file information and metadata
        display_file_info_table(mp3_file.info)
        display_metadata_table(mp3_file.metadata)
            
    except Exception as e:
        display_error(f"Error reading MP3 file: {e}")
        raise typer.Exit(1)

@app.command()
def enrich(file_path: str = typer.Argument(..., help="Path to the MP3 file to enrich with metadata from all available sources")) -> None:
    """Enrich an MP3 file with metadata from all available data sources (Bandcamp, MusicBrainz)"""
    try:
        result = unified_enrich(file_path)
        display_unified_enrichment_results(result)
    except Exception as e:
        display_error(f"Error enriching MP3 file: {e}")
        raise typer.Exit(1)

@app.command()
def download(
    search_text: str = typer.Argument(..., help="Track to download, e.g. 'Artist - Title'"),
    output_dir: Path = typer.Option(Path("downloads"), "--output-dir", "-o", help="Directory to save the downloaded file"),
    min_bitrate: int = typer.Option(192, "--min-bitrate", help="Minimum acceptable bitrate in kbps"),
    search_timeout: float = typer.Option(10.0, "--timeout", "-T", help="Seconds to wait for Soulseek search results"),
    max_attempts: int = typer.Option(5, "--attempts", help="Maximum download attempts before giving up"),
    enrich_after: bool = typer.Option(True, "--enrich/--no-enrich", help="Run metadata enrichment after download"),
    username: Optional[str] = typer.Option(None, "--username", "-u", envvar="SOULSEEK_USERNAME", help="Soulseek username", show_default=False),
    password: Optional[str] = typer.Option(None, "--password", "-p", envvar="SOULSEEK_PASSWORD", help="Soulseek password", show_default=False),
) -> None:
    """Download a track from Soulseek and optionally enrich it with metadata"""
    from .config import load_soulseek_config
    from .soulseek_downloader import DownloadError, SoulseekDownloader

    try:
        config = load_soulseek_config(username, password)
    except ValueError as e:
        display_error(str(e))
        raise typer.Exit(1)

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        dest = asyncio.run(
            _download_async(
                search_text=search_text,
                config=config,
                output_dir=output_dir,
                min_bitrate=min_bitrate,
                search_timeout=search_timeout,
                max_attempts=max_attempts,
            )
        )
    except (DownloadError, ValueError) as e:
        display_error(str(e))
        raise typer.Exit(1)

    display_download_complete(dest)

    if enrich_after:
        console.print("[cyan]Running metadata enrichment...[/cyan]")
        try:
            _strip_existing_tags(dest)
            result = unified_enrich(str(dest))
            display_unified_enrichment_results(result)
        except Exception as e:
            console.print(f"[yellow]Warning: enrichment failed: {e}[/yellow]")


def _strip_existing_tags(path: Path) -> None:
    """Remove all ID3 tags from a downloaded file so enrichment sources write fresh metadata."""
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        ID3(str(path)).delete()
    except (ID3NoHeaderError, Exception):
        pass


async def _download_async(
    search_text: str,
    config: "SoulseekConfig",  # type: ignore[name-defined]
    output_dir: Path,
    min_bitrate: int,
    search_timeout: float,
    max_attempts: int,
) -> Path:
    from .soulseek_downloader import DownloadError, SoulseekDownloader, _sanitize_filename

    # Derive destination filename from search text
    dest = output_dir / f"{_sanitize_filename(search_text)}.mp3"

    async with SoulseekDownloader(config, output_dir) as dl:
        console.print(
            f"[cyan]Searching Soulseek for:[/cyan] [bold]{search_text}[/bold]  "
            f"[dim]({search_timeout:.0f}s timeout)[/dim]"
        )
        with console.status("Collecting results..."):
            candidates = await dl.search(search_text, timeout=search_timeout, min_bitrate=min_bitrate)

        if not candidates:
            raise ValueError(f"No results found on Soulseek for '{search_text}'")

        display_slsk_candidates(candidates)

        from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn

        for attempt, candidate in enumerate(candidates[:max_attempts], 1):
            console.print(
                f"[cyan]Attempt {attempt}/{min(max_attempts, len(candidates))}:[/cyan] "
                f"downloading from [yellow]{candidate.username}[/yellow]  "
                f"[dim]{candidate.display_name}[/dim]"
            )

            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task_id = progress.add_task(
                    "Downloading...",
                    total=candidate.file_size or None,
                )

                def on_progress(bytes_done: int, total: Optional[int]) -> None:
                    progress.update(task_id, completed=bytes_done, total=total or candidate.file_size or None)

                try:
                    return await dl.download_file(candidate, dest, on_progress=on_progress)
                except DownloadError as e:
                    console.print(f"[yellow]  Failed: {e}[/yellow]")
                    continue

    raise DownloadError(f"All {max_attempts} download attempts failed for '{search_text}'")


if __name__ == "__main__":
    app()