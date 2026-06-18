"""Display utilities for Rich console output formatting."""

from typing import Dict, Any, List, Optional
from rich import box
from rich.console import Console
from rich.json import JSON
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from .id3_tags import ID3_TAG_NAMES
from .data_sources import extract_artist_name_from_credits

console = Console()


# ---------------------------------------------------------------------------
# Download command design system — "monochrome + one accent".
#
# A near-monochrome grey ramp plus a single accent hue (warm amber), rationed
# to the one element that matters at any moment: the active download and the
# final success mark. No boxes or borders — structure comes from alignment.
# Importance is encoded by brightness, not by an array of competing colors.
# (See style_demos/ for the exploration this was chosen from.)
# ---------------------------------------------------------------------------

ACCENT = "#d7af5f"   # the single accent hue — warm amber
DL_TEXT = "grey93"   # primary content
DL_MUTED = "grey62"  # secondary labels, headers, units
DL_FAINT = "grey39"  # diagnostics, scaffolding, rules

_ACCENT_BOLD = f"bold {ACCENT}"
_LEAD = "›"     # › quiet lead-in marker
_DONE = "✓"     # ✓ completion


def display_log_path(path: Any) -> None:
    """The most de-emphasized line: where diagnostics are being written."""
    console.print()
    console.print(Text(f"logging diagnostics to {path}", style=DL_FAINT))
    console.print()


def connecting_text() -> Text:
    """Label for the 'connecting to Soulseek' status spinner."""
    return Text("connecting to Soulseek", style=DL_MUTED)


def collecting_text(files: int, peers: int) -> Text:
    """Live status text while search results stream in."""
    line = Text()
    line.append("collecting results  ", style=DL_MUTED)
    line.append(f"{files} files", style=DL_TEXT)
    line.append(" from ", style=DL_MUTED)
    line.append(f"{peers} peers", style=DL_TEXT)
    return line


def display_search_header(query: str, timeout_s: float) -> None:
    """Announce the search query and its timeout."""
    header = Text()
    header.append(f"{_LEAD} ", style=DL_FAINT)
    header.append("searching  ", style=DL_MUTED)
    header.append(str(query), style=DL_TEXT)
    console.print(header)
    console.print(Text(f"  timeout {timeout_s:.0f}s", style=DL_FAINT))
    console.print()


def display_collected(files: int, peers: int) -> None:
    """Final summary line once result collection has finished."""
    line = Text()
    line.append("  collected  ", style=DL_MUTED)
    line.append(f"{files} files", style=DL_TEXT)
    line.append(" from ", style=DL_MUTED)
    line.append(f"{peers} peers", style=DL_TEXT)
    console.print(line)
    console.print()


def display_racing(count: int) -> None:
    """Announce that candidates are being raced for an upload slot."""
    line = Text()
    line.append(f"{_LEAD} ", style=DL_FAINT)
    line.append(f"racing top {count} candidates for an upload slot", style=DL_MUTED)
    console.print(line)


def display_request(username: str) -> None:
    """A single 'requesting from <peer>' sub-line."""
    req = Text()
    req.append("    requesting from ", style=DL_MUTED)
    req.append(str(username), style=DL_TEXT)
    console.print(req)


def make_download_progress() -> Progress:
    """A Progress styled in the download design system.

    The amber accent appears only here (the active download) and on the final
    success line. Add the task with fields ``user`` (the peer, shown in accent)
    and a ``description`` prefix; e.g.::

        task = progress.add_task("waiting for a slot", user="", total=None, start=False)
        progress.update(task, description="downloading from", user=peer, total=size)
    """
    return Progress(
        SpinnerColumn(style=DL_MUTED),
        TextColumn("{task.description}", style=DL_MUTED),
        TextColumn("{task.fields[user]}", style=_ACCENT_BOLD),
        BarColumn(
            bar_width=32,
            complete_style=ACCENT,
            finished_style=ACCENT,
            style=DL_FAINT,
            pulse_style=ACCENT,
        ),
        TextColumn("{task.percentage:>3.0f}%", style=DL_MUTED),
        TransferSpeedColumn(),
        DownloadColumn(),
        console=console,
    )


def extract_artist_name_from_track_data(track_data: Dict[str, Any], source_type: str) -> str:
    """Extract artist name from track data based on source type."""
    if source_type == "bandcamp":
        return track_data.get('band_name', 'Unknown')
    elif source_type == "musicbrainz":
        return extract_artist_name_from_credits(track_data.get('artist-credit', []))
    else:
        return track_data.get('artist', 'Unknown')


def display_search_results(data: Any, title: str, color: str) -> None:
    """Display search results in a formatted panel."""
    console.print(Panel.fit(
        JSON.from_data(data),
        title=f"[bold {color}]{title}[/bold {color}]",
        border_style=color
    ))


def display_file_info_table(file_info: Dict[str, Any]) -> None:
    """Create and display MP3 file information table."""
    # Format duration
    duration_seconds = file_info['duration_seconds']
    minutes = int(duration_seconds // 60)
    seconds = int(duration_seconds % 60)
    duration_str = f"{minutes}:{seconds:02d}"
    
    # Create table
    info_table = Table(title="[bold green]MP3 File Information[/bold green]", border_style="green")
    info_table.add_column("Property", style="cyan", no_wrap=True)
    info_table.add_column("Value", style="white")
    
    info_table.add_row("File", file_info['file_path'])
    info_table.add_row("Size", f"{file_info['file_size']:,} bytes ({file_info['file_size'] / 1024 / 1024:.2f} MB)")
    info_table.add_row("Duration", duration_str)
    info_table.add_row("Bitrate", f"{file_info['bitrate'] // 1000} kbps" if file_info['bitrate'] else "Unknown")
    info_table.add_row("Sample Rate", f"{file_info['sample_rate']} Hz" if file_info['sample_rate'] else "Unknown")
    
    console.print(info_table)


def display_metadata_table(tags: Dict[str, str], title: str = "Metadata Tags", color: str = "yellow") -> None:
    """Create and display metadata table."""
    if not tags:
        console.print(Panel("No metadata tags found", title=f"[{color}]Metadata[/{color}]", border_style=color))
        return
    
    metadata_table = Table(title=f"[bold {color}]{title}[/bold {color}]", border_style=color)
    metadata_table.add_column("Tag", style="cyan", no_wrap=True)
    metadata_table.add_column("ID3 Key", style="dim")
    metadata_table.add_column("Value", style="white")
    
    for key, value in tags.items():
        readable_name = ID3_TAG_NAMES.get(key, key)
        metadata_table.add_row(readable_name, key, str(value))
    
    console.print(metadata_table)


def display_enrichment_success(file_path: str, service_name: str = "") -> None:
    """Display enrichment success panel."""
    title = f"{service_name} Enrichment Complete" if service_name else "Enrichment Complete"
    console.print(Panel(
        f"[bold green]Successfully enriched: {file_path}[/bold green]",
        title=f"[bold green]{title}[/bold green]",
        border_style="green"
    ))


def display_bandcamp_search_details(result: Dict[str, Any]) -> None:
    """Display Bandcamp-specific search details."""
    track = result['bandcamp_track']
    search_panel = Panel(
        f"[cyan]Search Query:[/cyan] {result['search_query']}\n"
        f"[cyan]Found Track:[/cyan] {track.get('band_name', 'Unknown')} - {track.get('name', 'Unknown')} (URL: {track.get('item_url_path', 'Unknown')})\n"
        f"[cyan]Album:[/cyan] {track.get('album_name', 'Unknown')}",
        title="[bold blue]Search Results[/bold blue]",
        border_style="blue"
    )
    console.print(search_panel)


def display_musicbrainz_search_details(result: Dict[str, Any]) -> None:
    """Display MusicBrainz-specific search details."""
    recording = result['musicbrainz_recording']
    artist_name = extract_artist_name_from_track_data(recording, "musicbrainz")
    
    search_panel = Panel(
        f"[cyan]Search Query:[/cyan] {result['search_query']}\n"
        f"[cyan]Found Track:[/cyan] {artist_name} - {recording.get('title', 'Unknown')}\n"
        f"[cyan]Recording ID:[/cyan] {recording.get('id', 'Unknown')}",
        title="[bold green]MusicBrainz Search Results[/bold green]",
        border_style="green"
    )
    console.print(search_panel)


def display_discogs_search_details(result: Dict[str, Any]) -> None:
    """Display Discogs-specific search details."""
    detail = result['discogs_track']
    stub = detail.get('_release_stub', {})
    matched = detail.get('_matched_track')
    source = detail.get('_source', 'release')

    artists = detail.get('artists', [])
    artist_str = ' & '.join(a.get('name', '') for a in artists if a.get('name'))

    track_line = ""
    if matched:
        track_line = f"\n[cyan]Matched Track:[/cyan] {matched.get('title', 'Unknown')} (pos {matched.get('position', '?')}, {matched.get('duration', '?')})"

    search_panel = Panel(
        f"[cyan]Search Query:[/cyan] {result['search_query']}\n"
        f"[cyan]Source:[/cyan] {source} — {artist_str} / {detail.get('title', 'Unknown')} ({detail.get('year', '?')})"
        f"{track_line}\n"
        f"[cyan]Styles:[/cyan] {', '.join(detail.get('styles', []) or ['—'])}",
        title="[bold magenta]Discogs Search Results[/bold magenta]",
        border_style="magenta"
    )
    console.print(search_panel)


def filter_actual_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Filter out skipped metadata entries to show only actual additions."""
    return {k: v for k, v in metadata.items() 
            if not str(v).startswith('Artwork already exists') and 
               not str(v).startswith('No new metadata')}


def display_enrichment_results(result: Dict[str, Any], search_details_func: Any) -> None:
    """Display complete enrichment results using provided search details function."""
    # Show search details
    search_details_func(result)
    
    # Show added metadata
    actual_added_metadata = filter_actual_metadata(result['added_metadata'])
    
    if actual_added_metadata:
        display_metadata_table(actual_added_metadata, "New Metadata Added", "green")
    else:
        console.print(Panel(
            "No new metadata was added - all fields already had values",
            title="[yellow]No Changes[/yellow]",
            border_style="yellow"
        ))
    
    # Show existing metadata for comparison
    if result['existing_metadata']:
        display_metadata_table(result['existing_metadata'], "Existing Metadata", "yellow")


def display_error(message: str, prefix: str = "Error") -> None:
    """Display error message in red."""
    from rich.markup import escape
    console.print(f"[bold red]{prefix}:[/bold red] {escape(message)}")


def display_unified_search_results(results: Dict[str, Any], top_n: int = 3) -> None:
    """Display search results from all data sources in a clean summary format."""
    console.print(Panel(
        f"[bold cyan]Search completed across {len(results)} data sources[/bold cyan]",
        title="[bold blue]Unified Search Results[/bold blue]",
        border_style="blue"
    ))
    
    for source_name, result in results.items():
        if result['success']:
            display_search_summary(source_name, result['data'], top_n)
        else:
            console.print(Panel(
                f"[red]Error: {result['error']}[/red]",
                title=f"[bold red]{source_name} Error[/bold red]",
                border_style="red"
            ))


def display_discogs_search_summary(data: Dict[str, Any], top_n: int = 3) -> None:
    """Display a clean summary of Discogs search results."""
    results = data.get('results', [])
    if not results:
        console.print(Panel(
            "No results found",
            title="[bold magenta]Discogs Results[/bold magenta]",
            border_style="magenta"
        ))
        return

    table = Table(title="[bold magenta]Discogs Search Results[/bold magenta]", border_style="magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("Release", style="white")
    table.add_column("Format", style="cyan", no_wrap=True)
    table.add_column("Year", style="yellow", width=6)
    table.add_column("Label", style="dim")

    for i, release in enumerate(results[:top_n], 1):
        title = release.get('title', 'Unknown')
        fmt = ', '.join(release.get('format', []))
        year = str(release.get('year', ''))
        labels = release.get('label', [])
        label = labels[0] if labels else ''
        table.add_row(str(i), title, fmt, year, label)

    console.print(table)

    if len(results) > top_n:
        console.print(f"[dim]Showing top {top_n} of {len(results)} release results[/dim]")


def display_search_summary(source_name: str, data: Dict[str, Any], top_n: int = 3) -> None:
    """Display a clean summary of search results for a specific data source."""
    if source_name == "Bandcamp":
        display_bandcamp_search_summary(data, top_n)
    elif source_name == "MusicBrainz":
        display_musicbrainz_search_summary(data, top_n)
    elif source_name == "Discogs":
        display_discogs_search_summary(data, top_n)
    else:
        console.print(Panel(
            JSON.from_data(data),
            title=f"[bold green]{source_name} Results[/bold green]",
            border_style="green"
        ))


def display_bandcamp_search_summary(data: Dict[str, Any], top_n: int = 3) -> None:
    """Display a clean summary of Bandcamp search results."""
    if 'auto' not in data or 'results' not in data['auto']:
        console.print(Panel(
            "No results found",
            title="[bold blue]Bandcamp Results[/bold blue]",
            border_style="blue"
        ))
        return
    
    results = data['auto']['results']
    track_results = [r for r in results if r.get('type') == 't'][:top_n]
    
    if not track_results:
        console.print(Panel(
            "No track results found",
            title="[bold blue]Bandcamp Results[/bold blue]",
            border_style="blue"
        ))
        return
    
    # Create summary table
    table = Table(title="[bold blue]Bandcamp Search Results[/bold blue]", border_style="blue")
    table.add_column("#", style="dim", width=3)
    table.add_column("Artist", style="cyan", no_wrap=True)
    table.add_column("Track", style="white")
    table.add_column("Album", style="yellow")
    table.add_column("Type", style="dim")
    
    for i, track in enumerate(track_results, 1):
        artist = track.get('band_name', 'Unknown')
        title = track.get('name', 'Unknown')
        album = track.get('album_name', 'Unknown')
        track_type = track.get('type', 'Unknown')
        
        table.add_row(
            str(i),
            artist,
            title,
            album,
            track_type
        )
    
    console.print(table)
    
    # Show total count
    total_tracks = len([r for r in results if r.get('type') == 't'])
    if total_tracks > top_n:
        console.print(f"[dim]Showing top {top_n} of {total_tracks} track results[/dim]")


def display_musicbrainz_search_summary(data: Dict[str, Any], top_n: int = 3) -> None:
    """Display a clean summary of MusicBrainz search results."""
    if 'recordings' not in data:
        console.print(Panel(
            "No results found",
            title="[bold green]MusicBrainz Results[/bold green]",
            border_style="green"
        ))
        return
    
    recordings = data['recordings'][:top_n]
    
    if not recordings:
        console.print(Panel(
            "No recording results found",
            title="[bold green]MusicBrainz Results[/bold green]",
            border_style="green"
        ))
        return
    
    # Create summary table
    table = Table(title="[bold green]MusicBrainz Search Results[/bold green]", border_style="green")
    table.add_column("#", style="dim", width=3)
    table.add_column("Artist", style="cyan", no_wrap=True)
    table.add_column("Track", style="white")
    table.add_column("Release", style="yellow")
    table.add_column("ID", style="dim")
    
    for i, recording in enumerate(recordings, 1):
        # Extract artist name
        artist_name = extract_artist_name_from_track_data(recording, "musicbrainz")
        
        title = recording.get('title', 'Unknown')
        release = ""
        if 'releases' in recording and recording['releases']:
            release = recording['releases'][0].get('title', 'Unknown')
        
        recording_id = recording.get('id', 'Unknown')
        
        table.add_row(
            str(i),
            artist_name,
            title,
            release,
            recording_id[:8] + "..." if len(recording_id) > 8 else recording_id
        )
    
    console.print(table)
    
    # Show total count
    total_recordings = len(data['recordings'])
    if total_recordings > top_n:
        console.print(f"[dim]Showing top {top_n} of {total_recordings} recording results[/dim]")


def display_slsk_candidates(candidates: List[Any], top_n: int = 5) -> None:
    """Display ranked Soulseek download candidates.

    Borderless, near-monochrome: aligned columns under a single dim header
    rule. No accent here — it is reserved for the active download and success.
    """
    if not candidates:
        console.print(Text("no results found on Soulseek", style=DL_MUTED))
        return

    total = len(candidates)
    label = f"top {top_n} of {total}" if total > top_n else f"{total} candidates"
    console.print(Text(label, style=DL_MUTED))

    table = Table(
        box=box.SIMPLE_HEAD,
        show_edge=False,
        pad_edge=False,
        border_style=DL_FAINT,
        header_style=DL_MUTED,
    )
    table.add_column("", justify="right", style=DL_MUTED)
    table.add_column("user", style=DL_TEXT, no_wrap=True)
    table.add_column("filename", style=DL_TEXT)
    table.add_column("bitrate", justify="right", style=DL_MUTED)
    table.add_column("size", justify="right", style=DL_MUTED)
    table.add_column("score", justify="right", style=DL_MUTED)

    for i, r in enumerate(candidates[:top_n], 1):
        bitrate = f"{r.bitrate} kbps" if r.bitrate else "?"
        size = f"{r.file_size / 1024 / 1024:.1f} MB" if r.file_size else "?"
        table.add_row(str(i), r.username, r.display_name, bitrate, size, f"{r.score:.2f}")

    console.print(table)
    console.print()


def display_download_complete(dest_path: Any, enriched: bool = False) -> None:
    """Display download success — the one other place the accent appears."""
    ok = Text()
    ok.append(f"{_DONE} ", style=_ACCENT_BOLD)
    ok.append("download complete  ", style=_ACCENT_BOLD)
    ok.append(str(dest_path), style=DL_TEXT)
    console.print()
    console.print(ok)
    if enriched:
        console.print(Text("  metadata enrichment applied", style=DL_FAINT))
    console.print()


def display_unified_enrichment_results(result: Dict[str, Any]) -> None:
    """Display enrichment results from unified enrichment."""
    # Show successful enrichment
    successful = result['successful_enrichment']
    source_name = "Unknown"
    
    # Determine which source succeeded
    for source_name, source_result in result['all_results'].items():
        if source_result['success']:
            source_name = source_name
            break
    
    # Display success message
    display_enrichment_success(successful['file_path'], source_name)
    
    # Display search details based on the successful source
    if 'bandcamp_track' in successful:
        display_bandcamp_search_details(successful)
    elif 'musicbrainz_recording' in successful:
        display_musicbrainz_search_details(successful)
    elif 'discogs_track' in successful:
        display_discogs_search_details(successful)
    
    # Show added metadata
    actual_added_metadata = filter_actual_metadata(successful['added_metadata'])
    
    if actual_added_metadata:
        display_metadata_table(actual_added_metadata, "New Metadata Added", "green")
    else:
        console.print(Panel(
            "No new metadata was added - all fields already had values",
            title="[yellow]No Changes[/yellow]",
            border_style="yellow"
        ))
    
    # Show existing metadata for comparison
    if successful['existing_metadata']:
        display_metadata_table(successful['existing_metadata'], "Existing Metadata", "yellow")
    
    # Show summary of all data source attempts
    console.print("\n[bold cyan]Data Source Summary:[/bold cyan]")
    for source_name, source_result in result['all_results'].items():
        status = "✓ Success" if source_result['success'] else f"✗ Failed: {source_result['error']}"
        color = "green" if source_result['success'] else "red"
        console.print(f"  [{color}]{source_name}: {status}[/{color}]")
