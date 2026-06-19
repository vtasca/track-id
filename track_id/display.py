"""Display utilities for Rich console output formatting."""

from typing import Dict, Any, List, Optional, Iterable, Tuple
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
from rich.text import Text
from .id3_tags import ID3_TAG_NAMES
from .data_sources import extract_artist_name_from_credits

console = Console()


# ---------------------------------------------------------------------------
# Design system — "monochrome + one accent".
#
# A near-monochrome grey ramp plus a single accent hue (warm amber), rationed
# to the one element that matters at any moment: the active download and the
# final success mark. No boxes or borders — structure comes from alignment.
# Importance is encoded by brightness, not by an array of competing colors.
#
# This started life on the download command and now governs every screen that
# prints to stdout: search, info, enrich, errors. The vocabulary below — the
# grey ramp, the lead-in `›`, the `✓`/`✗` marks, borderless aligned tables —
# is the whole design system; new output should be built only from it.
# ---------------------------------------------------------------------------

ACCENT = "#d7af5f"   # the single accent hue — warm amber
DL_TEXT = "grey93"   # primary content
DL_MUTED = "grey62"  # secondary labels, headers, units
DL_FAINT = "grey39"  # diagnostics, scaffolding, rules

ERROR = "#c75450"    # muted red — the one other rationed hue, reserved for failure

_ACCENT_BOLD = f"bold {ACCENT}"
_ERROR_BOLD = f"bold {ERROR}"
_LEAD = "›"     # › quiet lead-in marker for a top-level section
_DONE = "✓"     # ✓ success
_FAIL = "✗"     # ✗ failure


# ---------------------------------------------------------------------------
# Shared primitives — the building blocks every screen is assembled from.
# ---------------------------------------------------------------------------

def section(label: str, value: Any = None, *, mark: Optional[str] = _LEAD,
            blank_before: bool = True) -> None:
    """Print a section header — ``› label  value``.

    Pass ``mark=None`` for a nested sub-header (a plain muted label with no
    lead-in marker), used to group sources under a top-level section.
    """
    if blank_before:
        console.print()
    header = Text()
    if mark:
        header.append(f"{mark} ", style=DL_FAINT)
    header.append(str(label), style=DL_MUTED)
    if value is not None:
        header.append("  ")
        header.append(str(value), style=DL_TEXT)
    console.print(header)


def _mono_table(show_header: bool = True) -> Table:
    """A borderless, near-monochrome table in the shared design system."""
    return Table(
        box=box.SIMPLE_HEAD if show_header else box.SIMPLE,
        show_edge=False,
        pad_edge=False,
        show_header=show_header,
        border_style=DL_FAINT,
        header_style=DL_MUTED,
    )


def _print_pairs(pairs: Iterable[Tuple[str, Any]]) -> None:
    """Render a quiet key/value block — right-aligned labels, aligned values."""
    table = _mono_table(show_header=False)
    table.add_column(justify="right", style=DL_MUTED, no_wrap=True)
    table.add_column(style=DL_TEXT)
    for label, value in pairs:
        table.add_row(str(label), str(value))
    console.print(table)


def _overflow(total: int, shown: int) -> None:
    """Quiet ``+K more`` line when a table has been truncated."""
    if total > shown:
        console.print(Text(f"  +{total - shown} more", style=DL_FAINT))


def display_warning(message: str) -> None:
    """A non-fatal warning — stays in the grey ramp, never takes the accent."""
    line = Text()
    line.append("! ", style=DL_MUTED)
    line.append(str(message), style=DL_MUTED)
    console.print(line)


def extract_artist_name_from_track_data(track_data: Dict[str, Any], source_type: str) -> str:
    """Extract artist name from track data based on source type."""
    if source_type == "bandcamp":
        return track_data.get('band_name', 'Unknown')
    elif source_type == "musicbrainz":
        return extract_artist_name_from_credits(track_data.get('artist-credit', []))
    else:
        return track_data.get('artist', 'Unknown')


# ---------------------------------------------------------------------------
# Download command — live progress helpers.
# ---------------------------------------------------------------------------

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
    section("searching", query)
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

    table = _mono_table()
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
    """Display download success — one of two places the accent appears."""
    ok = Text()
    ok.append(f"{_DONE} ", style=_ACCENT_BOLD)
    ok.append("download complete  ", style=_ACCENT_BOLD)
    ok.append(str(dest_path), style=DL_TEXT)
    console.print()
    console.print(ok)
    if enriched:
        console.print(Text("  metadata enrichment applied", style=DL_FAINT))
    console.print()


# ---------------------------------------------------------------------------
# info command.
# ---------------------------------------------------------------------------

def display_file_info_table(file_info: Dict[str, Any]) -> None:
    """Display MP3 file information as a quiet key/value block."""
    duration_seconds = file_info['duration_seconds']
    minutes = int(duration_seconds // 60)
    seconds = int(duration_seconds % 60)
    duration_str = f"{minutes}:{seconds:02d}"

    size = file_info['file_size']
    bitrate = file_info['bitrate']
    sample_rate = file_info['sample_rate']

    section("file info", file_info['file_path'])
    _print_pairs([
        ("size", f"{size:,} bytes  ({size / 1024 / 1024:.2f} MB)"),
        ("duration", duration_str),
        ("bitrate", f"{bitrate // 1000} kbps" if bitrate else "unknown"),
        ("sample rate", f"{sample_rate} Hz" if sample_rate else "unknown"),
    ])
    console.print()


# ---------------------------------------------------------------------------
# Metadata tables — shared by info and enrich.
# ---------------------------------------------------------------------------

def display_metadata_table(tags: Dict[str, str], title: str = "metadata tags",
                           color: Optional[str] = None) -> None:
    """Display metadata tags as a borderless, near-monochrome table.

    ``color`` is accepted for backward compatibility but ignored — the design
    system is monochrome.
    """
    section(title, mark=None)
    if not tags:
        console.print(Text("  no metadata tags found", style=DL_FAINT))
        return

    table = _mono_table()
    table.add_column("tag", style=DL_TEXT, no_wrap=True)
    table.add_column("id3 key", style=DL_MUTED, no_wrap=True)
    table.add_column("value", style=DL_TEXT)

    for key, value in tags.items():
        readable_name = ID3_TAG_NAMES.get(key, key)
        table.add_row(readable_name, key, str(value))

    console.print(table)


# ---------------------------------------------------------------------------
# enrich command — success, per-source details, results.
# ---------------------------------------------------------------------------

def display_enrichment_success(file_path: str, service_name: str = "") -> None:
    """Display enrichment success — the other place the accent appears."""
    ok = Text()
    ok.append(f"{_DONE} ", style=_ACCENT_BOLD)
    label = f"enriched via {service_name.lower()}" if service_name else "enriched"
    ok.append(f"{label}  ", style=_ACCENT_BOLD)
    ok.append(str(file_path), style=DL_TEXT)
    console.print()
    console.print(ok)


def display_bandcamp_search_details(result: Dict[str, Any]) -> None:
    """Display Bandcamp-specific search details."""
    track = result['bandcamp_track']
    section("bandcamp", mark=None)
    _print_pairs([
        ("query", result['search_query']),
        ("found", f"{track.get('band_name', 'Unknown')} — {track.get('name', 'Unknown')}"),
        ("album", track.get('album_name', 'Unknown')),
        ("url", track.get('item_url_path', 'Unknown')),
    ])


def display_musicbrainz_search_details(result: Dict[str, Any]) -> None:
    """Display MusicBrainz-specific search details."""
    recording = result['musicbrainz_recording']
    artist_name = extract_artist_name_from_track_data(recording, "musicbrainz")
    section("musicbrainz", mark=None)
    _print_pairs([
        ("query", result['search_query']),
        ("found", f"{artist_name} — {recording.get('title', 'Unknown')}"),
        ("recording", recording.get('id', 'Unknown')),
    ])


def display_discogs_search_details(result: Dict[str, Any]) -> None:
    """Display Discogs-specific search details."""
    detail = result['discogs_track']
    matched = detail.get('_matched_track')
    source = detail.get('_source', 'release')

    artists = detail.get('artists', [])
    artist_str = ' & '.join(a.get('name', '') for a in artists if a.get('name'))

    section("discogs", mark=None)
    pairs: List[Tuple[str, Any]] = [
        ("query", result['search_query']),
        ("source", f"{source} — {artist_str} / {detail.get('title', 'Unknown')} "
                   f"({detail.get('year', '?')})"),
    ]
    if matched:
        pairs.append((
            "matched",
            f"{matched.get('title', 'Unknown')} "
            f"(pos {matched.get('position', '?')}, {matched.get('duration', '?')})",
        ))
    pairs.append(("styles", ', '.join(detail.get('styles', []) or ['—'])))
    _print_pairs(pairs)


def filter_actual_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Filter out skipped metadata entries to show only actual additions."""
    return {k: v for k, v in metadata.items()
            if not str(v).startswith('Artwork already exists') and
               not str(v).startswith('No new metadata')}


def _display_added_or_unchanged(added_metadata: Dict[str, Any]) -> None:
    """Show newly added metadata, or a quiet 'no changes' note."""
    actual_added_metadata = filter_actual_metadata(added_metadata)
    if actual_added_metadata:
        display_metadata_table(actual_added_metadata, "new metadata")
    else:
        section("no changes", mark=None)
        console.print(Text("  all fields already had values", style=DL_FAINT))


def display_enrichment_results(result: Dict[str, Any], search_details_func: Any) -> None:
    """Display complete enrichment results using provided search details function."""
    search_details_func(result)
    _display_added_or_unchanged(result['added_metadata'])
    if result['existing_metadata']:
        display_metadata_table(result['existing_metadata'], "existing metadata")


def display_unified_enrichment_results(result: Dict[str, Any]) -> None:
    """Display enrichment results from unified enrichment."""
    successful = result['successful_enrichment']

    # Which source produced the winning enrichment.
    source_name = next(
        (name for name, r in result['all_results'].items() if r['success']),
        "",
    )

    display_enrichment_success(successful['file_path'], source_name)

    # Search details based on the successful source.
    if 'bandcamp_track' in successful:
        display_bandcamp_search_details(successful)
    elif 'musicbrainz_recording' in successful:
        display_musicbrainz_search_details(successful)
    elif 'discogs_track' in successful:
        display_discogs_search_details(successful)

    _display_added_or_unchanged(successful['added_metadata'])

    if successful['existing_metadata']:
        display_metadata_table(successful['existing_metadata'], "existing metadata")

    # A compact ledger of every source that was tried.
    section("sources", mark=None)
    for name, source_result in result['all_results'].items():
        line = Text("  ")
        if source_result['success']:
            line.append(f"{_DONE} ", style=_ACCENT_BOLD)
            line.append(name, style=DL_TEXT)
        else:
            line.append(f"{_FAIL} ", style=ERROR)
            line.append(name, style=DL_MUTED)
            line.append(f"  {source_result['error']}", style=DL_FAINT)
        console.print(line)
    console.print()


# ---------------------------------------------------------------------------
# search command — unified results across sources.
# ---------------------------------------------------------------------------

def display_search_results(data: Any, title: str, color: str = "") -> None:
    """Display raw search results as JSON under a section header."""
    section(title)
    console.print(JSON.from_data(data))
    console.print()


def display_unified_search_results(results: Dict[str, Any], top_n: int = 3) -> None:
    """Display search results from all data sources in a clean summary format."""
    section("search", f"{len(results)} sources")

    for source_name, result in results.items():
        if result['success']:
            display_search_summary(source_name, result['data'], top_n)
        else:
            section(source_name.lower(), mark=None)
            console.print(Text(f"  {result['error']}", style=ERROR))
    console.print()


def display_search_summary(source_name: str, data: Dict[str, Any], top_n: int = 3) -> None:
    """Display a clean summary of search results for a specific data source."""
    if source_name == "Bandcamp":
        display_bandcamp_search_summary(data, top_n)
    elif source_name == "MusicBrainz":
        display_musicbrainz_search_summary(data, top_n)
    elif source_name == "Discogs":
        display_discogs_search_summary(data, top_n)
    else:
        section(source_name.lower(), mark=None)
        console.print(JSON.from_data(data))


def display_bandcamp_search_summary(data: Dict[str, Any], top_n: int = 3) -> None:
    """Display a clean summary of Bandcamp search results."""
    section("bandcamp", mark=None)

    if 'auto' not in data or 'results' not in data['auto']:
        console.print(Text("  no results", style=DL_FAINT))
        return

    results = data['auto']['results']
    track_results = [r for r in results if r.get('type') == 't']

    if not track_results:
        console.print(Text("  no track results", style=DL_FAINT))
        return

    table = _mono_table()
    table.add_column("", justify="right", style=DL_MUTED)
    table.add_column("artist", style=DL_TEXT, no_wrap=True)
    table.add_column("track", style=DL_TEXT)
    table.add_column("album", style=DL_MUTED)

    for i, track in enumerate(track_results[:top_n], 1):
        table.add_row(
            str(i),
            track.get('band_name', 'Unknown'),
            track.get('name', 'Unknown'),
            track.get('album_name', 'Unknown'),
        )

    console.print(table)
    _overflow(len(track_results), min(top_n, len(track_results)))


def display_musicbrainz_search_summary(data: Dict[str, Any], top_n: int = 3) -> None:
    """Display a clean summary of MusicBrainz search results."""
    section("musicbrainz", mark=None)

    recordings = data.get('recordings', [])
    if not recordings:
        console.print(Text("  no results", style=DL_FAINT))
        return

    table = _mono_table()
    table.add_column("", justify="right", style=DL_MUTED)
    table.add_column("artist", style=DL_TEXT, no_wrap=True)
    table.add_column("track", style=DL_TEXT)
    table.add_column("release", style=DL_MUTED)
    table.add_column("id", style=DL_FAINT)

    for i, recording in enumerate(recordings[:top_n], 1):
        artist_name = extract_artist_name_from_track_data(recording, "musicbrainz")
        title = recording.get('title', 'Unknown')
        release = ""
        if recording.get('releases'):
            release = recording['releases'][0].get('title', 'Unknown')
        recording_id = recording.get('id', 'Unknown')
        short_id = recording_id[:8] + "…" if len(recording_id) > 8 else recording_id
        table.add_row(str(i), artist_name, title, release, short_id)

    console.print(table)
    _overflow(len(recordings), min(top_n, len(recordings)))


def display_discogs_search_summary(data: Dict[str, Any], top_n: int = 3) -> None:
    """Display a clean summary of Discogs search results."""
    section("discogs", mark=None)

    results = data.get('results', [])
    if not results:
        console.print(Text("  no results", style=DL_FAINT))
        return

    table = _mono_table()
    table.add_column("", justify="right", style=DL_MUTED)
    table.add_column("release", style=DL_TEXT)
    table.add_column("format", style=DL_MUTED, no_wrap=True)
    table.add_column("year", justify="right", style=DL_MUTED)
    table.add_column("label", style=DL_FAINT)

    for i, release in enumerate(results[:top_n], 1):
        title = release.get('title', 'Unknown')
        fmt = ', '.join(release.get('format', []))
        year = str(release.get('year', ''))
        labels = release.get('label', [])
        label = labels[0] if labels else ''
        table.add_row(str(i), title, fmt, year, label)

    console.print(table)
    _overflow(len(results), min(top_n, len(results)))


# ---------------------------------------------------------------------------
# Errors.
# ---------------------------------------------------------------------------

def display_error(message: str, prefix: str = "error") -> None:
    """Display an error — the muted-red mark, the one non-amber accent."""
    line = Text()
    line.append(f"{_FAIL} ", style=_ERROR_BOLD)
    line.append(f"{prefix}  ", style=ERROR)
    line.append(str(message), style=DL_TEXT)
    console.print()
    console.print(line)
