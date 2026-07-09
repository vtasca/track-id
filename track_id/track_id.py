import asyncio
import importlib.metadata
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

import typer

if TYPE_CHECKING:
    from .config import SoulseekConfig
    from .soulseek_downloader import SlskResult, SoulseekDownloader

from .display import (
    DL_MUTED,
    collecting_text,
    connecting_text,
    console,
    display_collected,
    display_download_complete,
    display_error,
    display_file_info_table,
    display_log_path,
    display_metadata_table,
    display_racing,
    display_request,
    display_search_header,
    display_search_sources_header,
    display_slsk_candidates,
    display_source_search_result,
    display_unified_enrichment_results,
    display_warning,
    make_download_progress,
    searching_text,
    section,
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
    top: int = typer.Option(3, "--top", "-t", help="Number of top results to show per source")
) -> None:
    """Search for tracks across all available data sources (Bandcamp, MusicBrainz, Discogs)"""
    from .unified_api import get_registry

    try:
        pending = [s.name for s in get_registry().get_all_sources()]
        display_search_sources_header(len(pending))

        # Sources run concurrently; print each one's results the moment it
        # answers, while the status line names whichever are still pending.
        shown = set()
        with console.status(searching_text(pending), spinner="dots", spinner_style=DL_MUTED) as status:
            def on_source_done(name: str, result: dict) -> None:
                display_source_search_result(name, result, top_n=top)
                shown.add(name)
                remaining = [n for n in pending if n not in shown]
                if remaining:
                    status.update(searching_text(remaining))

            results = unified_search(search_text, on_source_done=on_source_done)

        # Anything not streamed (defensive: callback missed a source)
        for name, result in results.items():
            if name not in shown:
                display_source_search_result(name, result, top_n=top)
        console.print()
    except Exception as e:
        display_error(str(e))
        raise typer.Exit(1) from None

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
        raise typer.Exit(1) from None

@app.command()
def enrich(
    file_path: str = typer.Argument(..., help="MP3 file — or directory of MP3s — to enrich with metadata from all available sources"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite fields that already have values"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be written without modifying files"),
) -> None:
    """Enrich MP3 files with metadata from all available data sources (Bandcamp, MusicBrainz, Discogs)"""
    if Path(file_path).is_dir():
        _enrich_directory(Path(file_path), force=force, dry_run=dry_run)
        return

    try:
        with console.status("querying sources", spinner="dots", spinner_style=DL_MUTED):
            result = unified_enrich(file_path, force=force, dry_run=dry_run)
        display_unified_enrichment_results(result)
        if dry_run:
            display_warning("dry run: no changes were written")
    except Exception as e:
        display_error(f"Error enriching MP3 file: {e}")
        raise typer.Exit(1) from None


def _enrich_directory(directory: Path, force: bool, dry_run: bool) -> None:
    """Enrich every MP3 under a directory, with per-file lines and a summary."""
    from .analysis import iter_audio_files
    from .display import display_batch_enrich_line, display_batch_enrich_summary

    files = iter_audio_files(directory)
    if not files:
        display_warning(f"no .mp3 files found under {directory}")
        return

    section("enrich", f"{len(files)} files in {directory}")
    enriched = skipped = unmatched = 0
    with console.status("", spinner="dots", spinner_style=DL_MUTED) as status:
        for i, file in enumerate(files, start=1):
            status.update(f"enriching {i}/{len(files)}  {file.name}")
            try:
                result = unified_enrich(str(file), force=force, dry_run=dry_run)
            except Exception as e:
                display_batch_enrich_line(file.name, "unmatched", str(e))
                unmatched += 1
                continue

            added = result['successful_enrichment']['added_metadata']
            new_fields = {
                k: v for k, v in added.items()
                if not (k == 'artwork' and 'skipped' in str(v))
            }
            if new_fields:
                plural = "s" if len(new_fields) != 1 else ""
                display_batch_enrich_line(file.name, "enriched", f"+{len(new_fields)} field{plural}")
                enriched += 1
            else:
                display_batch_enrich_line(file.name, "skipped", "already tagged")
                skipped += 1

    display_batch_enrich_summary(enriched, skipped, unmatched, dry_run)
    if dry_run and enriched:
        display_warning("dry run: no changes were written")

@app.command()
def analyze(
    file_path: str = typer.Argument(..., help="Path to the audio file to inspect"),
    min_bitrate: int = typer.Option(192, "--min-bitrate", help="Bitrate threshold (kbps) used when flagging problems"),
) -> None:
    """Deep-inspect one file: real container format, stream properties, tag completeness"""
    from .analysis import inspect_file
    from .display import display_analysis_report

    if not Path(file_path).is_file():
        display_error(f"File '{file_path}' does not exist")
        raise typer.Exit(1)

    try:
        report = inspect_file(file_path)
        display_analysis_report(report, min_bitrate=min_bitrate)
    except Exception as e:
        display_error(f"Error analyzing file: {e}")
        raise typer.Exit(1) from None


@app.command()
def rename(
    path: Path = typer.Argument(..., help="MP3 file or directory of MP3s to rename"),
    template: str = typer.Option(
        "{artist} - {title}", "--template", "-t",
        help="Filename template; fields: {artist} {title} {album} {year} {genre} {track}",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview renames without moving any files"),
) -> None:
    """Rename MP3 files from their tags using a template (default '{artist} - {title}')"""
    from .analysis import iter_audio_files
    from .display import display_rename_line, display_rename_summary
    from .mp3_utils import build_filename_from_tags, validate_rename_template

    try:
        validate_rename_template(template)
    except ValueError as e:
        display_error(str(e))
        raise typer.Exit(1) from None

    if path.is_dir():
        files = iter_audio_files(path)
        if not files:
            display_warning(f"no .mp3 files found under {path}")
            return
    elif path.is_file():
        files = [path]
    else:
        display_error(f"'{path}' does not exist")
        raise typer.Exit(1)

    section("rename", f"{len(files)} file{'s' if len(files) != 1 else ''}")
    renamed = unchanged = skipped = 0
    for file in files:
        try:
            new_name = build_filename_from_tags(MP3File(str(file)).metadata, template)
        except ValueError as e:
            display_warning(f"{file.name}: {e}")
            skipped += 1
            continue

        target = file.with_name(new_name + file.suffix)
        if target == file:
            unchanged += 1
        elif target.exists():
            display_warning(f"{file.name}: target '{target.name}' already exists")
            skipped += 1
        else:
            if not dry_run:
                file.rename(target)
            display_rename_line(file.name, target.name, performed=not dry_run)
            renamed += 1

    display_rename_summary(renamed, unchanged, skipped, dry_run)
    if dry_run and renamed:
        display_warning("dry run: no files were renamed")


@app.command()
def doctor(
    directory: Path = typer.Argument(Path("."), help="Directory to scan (recursive)"),
    min_bitrate: int = typer.Option(192, "--min-bitrate", help="Bitrate threshold (kbps) below which files are flagged"),
) -> None:
    """Scan a directory for unhealthy MP3s: fake audio files, low bitrate, missing tags or artwork"""
    from .analysis import inspect_file, iter_audio_files
    from .display import display_doctor_report

    if not directory.is_dir():
        display_error(f"'{directory}' is not a directory")
        raise typer.Exit(1)

    files = iter_audio_files(directory)
    if not files:
        display_warning(f"no .mp3 files found under {directory}")
        return

    results = []
    with console.status(f"scanning 0/{len(files)}", spinner="dots", spinner_style=DL_MUTED) as status:
        for i, path in enumerate(files, start=1):
            status.update(f"scanning {i}/{len(files)}")
            report = inspect_file(str(path))
            results.append((report, report.problems(min_bitrate)))

    display_doctor_report(directory, results)


@app.command()
def download(
    search_text: Optional[str] = typer.Argument(None, help="Track to download, e.g. 'Artist - Title'"),
    from_file: Optional[Path] = typer.Option(None, "--from", help="Text file with one 'Artist - Title' query per line; blank lines and # comments are skipped"),
    output_dir: Path = typer.Option(Path("downloads"), "--output-dir", "-o", help="Directory to save the downloaded file"),
    min_bitrate: int = typer.Option(192, "--min-bitrate", help="Minimum acceptable bitrate in kbps"),
    search_timeout: float = typer.Option(10.0, "--timeout", "-T", help="Seconds to wait for Soulseek search results"),
    max_attempts: int = typer.Option(5, "--attempts", help="Maximum download attempts before giving up"),
    enrich_after: bool = typer.Option(True, "--enrich/--no-enrich", help="Run metadata enrichment after download"),
    username: Optional[str] = typer.Option(None, "--username", "-u", envvar="SOULSEEK_USERNAME", help="Soulseek username", show_default=False),
    password: Optional[str] = typer.Option(None, "--password", "-p", envvar="SOULSEEK_PASSWORD", help="Soulseek password", show_default=False),
) -> None:
    """Download one track — or a list of tracks via --from — from Soulseek, then enrich"""
    from .config import load_soulseek_config
    from .logging_setup import configure_logging
    from .soulseek_downloader import DownloadError

    if (search_text is None) == (from_file is None):
        display_error("provide either a search query or --from FILE (not both)")
        raise typer.Exit(1)

    queries = [search_text] if search_text else _read_batch_file(from_file)  # type: ignore[arg-type]

    log_file = configure_logging()
    display_log_path(log_file)

    try:
        config = load_soulseek_config(username, password)
    except ValueError as e:
        display_error(str(e))
        raise typer.Exit(1) from None

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        results = asyncio.run(
            _download_batch_async(
                queries=queries,
                config=config,
                output_dir=output_dir,
                min_bitrate=min_bitrate,
                search_timeout=search_timeout,
                max_attempts=max_attempts,
            )
        )
    except (DownloadError, ValueError) as e:
        display_error(str(e))
        raise typer.Exit(1) from None

    downloaded = [(query, dest) for query, dest, _ in results if dest is not None]
    failed = [(query, error) for query, dest, error in results if dest is None]

    if enrich_after:
        for _, dest in downloaded:
            section("enriching", str(dest))
            try:
                _strip_existing_tags(dest)
                with console.status("querying sources", spinner="dots", spinner_style=DL_MUTED):
                    result = unified_enrich(str(dest))
                display_unified_enrichment_results(result)
            except Exception as e:
                display_warning(f"enrichment failed: {e}")

    if len(queries) > 1:
        section("summary", mark=None)
        for query, error in failed:
            display_warning(f"{query}: {error}")
        console.print(f"  downloaded {len(downloaded)} of {len(queries)} tracks")
        console.print()

    if failed and not downloaded:
        raise typer.Exit(1)


def _read_batch_file(path: Path) -> list:
    """Read download queries from a file: one per line, # comments and blanks skipped."""
    if not path.is_file():
        display_error(f"'{path}' does not exist")
        raise typer.Exit(1)

    queries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            queries.append(stripped)

    if not queries:
        display_error(f"no queries found in '{path}'")
        raise typer.Exit(1)
    return queries


async def _download_batch_async(
    queries: list,
    config: "SoulseekConfig",
    output_dir: Path,
    min_bitrate: int,
    search_timeout: float,
    max_attempts: int,
) -> list:
    """Download several tracks over a single Soulseek connection.

    Returns one ``(query, dest_or_None, error_or_None)`` tuple per query; a
    per-track failure is recorded and the batch moves on, but a connection
    failure propagates and aborts the run.
    """
    from .soulseek_downloader import DownloadError, SoulseekDownloader

    results: List[Tuple[str, Optional[Path], Optional[str]]] = []
    async with SoulseekDownloader(config, output_dir) as dl:
        with console.status(connecting_text(), spinner="dots", spinner_style=DL_MUTED):
            await dl.connect()

        for i, query in enumerate(queries, start=1):
            if len(queries) > 1:
                section("track", f"{i}/{len(queries)}  {query}")
            try:
                dest = await _download_one(
                    dl, query, output_dir, min_bitrate, search_timeout, max_attempts
                )
                display_download_complete(dest)
                results.append((query, dest, None))
            except (DownloadError, ValueError) as e:
                display_error(str(e))
                results.append((query, None, str(e)))
    return results


def _strip_existing_tags(path: Path) -> None:
    """Remove all ID3 tags from a downloaded file so enrichment sources write fresh metadata."""
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        ID3(str(path)).delete()
    except ID3NoHeaderError:
        pass  # no tags to strip; anything else propagates to the caller's warning


async def _download_one(
    dl: "SoulseekDownloader",
    search_text: str,
    output_dir: Path,
    min_bitrate: int,
    search_timeout: float,
    max_attempts: int,
) -> Path:
    """Search and download one track over an already-connected downloader."""
    from .analysis import sanitize_filename

    # Derive destination filename from search text
    dest = output_dir / f"{sanitize_filename(search_text)}.mp3"

    display_search_header(search_text, search_timeout)

    last_progress = {"files": 0, "peers": 0}
    with console.status(
        collecting_text(0, 0), spinner="dots", spinner_style=DL_MUTED
    ) as status:
        def on_search_progress(file_count: int, peer_count: int) -> None:
            last_progress["files"] = file_count
            last_progress["peers"] = peer_count
            status.update(collecting_text(file_count, peer_count))

        candidates = await dl.search(
            search_text,
            timeout=search_timeout,
            min_bitrate=min_bitrate,
            on_progress=on_search_progress,
        )

    if not candidates:
        raise ValueError(f"No results found on Soulseek for '{search_text}'")

    display_collected(last_progress["files"], last_progress["peers"])
    display_slsk_candidates(candidates)

    racers = candidates[:max_attempts]
    display_racing(len(racers))

    def on_attempt(c: "SlskResult") -> None:
        display_request(c.username)

    with make_download_progress() as progress:
        task_id = progress.add_task(
            "waiting for a slot", user="", total=None, start=False
        )

        def on_start(c: "SlskResult") -> None:
            console.print()  # separate the racing block from the download bar
            progress.update(
                task_id,
                description="downloading from",
                user=c.username,
                total=c.file_size or None,
            )
            progress.start_task(task_id)

        def on_progress(bytes_done: int, total: Optional[int]) -> None:
            progress.update(task_id, completed=bytes_done, total=total or None)

        return await dl.race_download(
            racers,
            dest,
            on_attempt=on_attempt,
            on_start=on_start,
            on_progress=on_progress,
        )


if __name__ == "__main__":
    app()