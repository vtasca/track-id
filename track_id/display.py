"""Display utilities for Rich console output formatting."""

from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.json import JSON
from rich.table import Table
from rich.panel import Panel
from .id3_tags import ID3_TAG_NAMES
from .data_sources import extract_artist_name_from_credits

console = Console()


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
    console.print(f"[bold red]{prefix}: {message}[/bold red]")


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


def display_search_summary(source_name: str, data: Dict[str, Any], top_n: int = 3) -> None:
    """Display a clean summary of search results for a specific data source."""
    if source_name == "Bandcamp":
        display_bandcamp_search_summary(data, top_n)
    elif source_name == "MusicBrainz":
        display_musicbrainz_search_summary(data, top_n)
    else:
        # Fallback to JSON display for unknown sources
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
