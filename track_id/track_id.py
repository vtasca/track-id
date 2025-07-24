import typer
from rich.console import Console
from rich.json import JSON
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from .id3_tags import ID3_TAG_NAMES
from .bandcamp_api import (
    search_bandcamp, 
    enrich_mp3_file
)
from .musicbrainz_api import (
    search_musicbrainz,
    enrich_mp3_file_musicbrainz
)
from .mp3_utils import (
    get_mp3_info, 
    get_mp3_metadata
)

console = Console()

app = typer.Typer()

@app.command()
def search(search_text: str = typer.Argument(..., help="The text to search for")):
    """Search for a track on Bandcamp"""

    try:
        data = search_bandcamp(search_text)
        console.print(Panel.fit(
            JSON.from_data(data),
            title="[bold blue]Bandcamp Search Results[/bold blue]",
            border_style="blue"
        ))
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)

@app.command()
def search_mb(search_text: str = typer.Argument(..., help="The text to search for")):
    """Search for a track on MusicBrainz"""

    try:
        data = search_musicbrainz(search_text)
        console.print(Panel.fit(
            JSON.from_data(data),
            title="[bold green]MusicBrainz Search Results[/bold green]",
            border_style="green"
        ))
    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)

@app.command()
def info(file_path: str = typer.Argument(..., help="Path to the MP3 file")):
    """Display information about an MP3 file"""
    
    try:
        # Get file information
        file_info = get_mp3_info(file_path)
        
        # Get metadata
        tags = get_mp3_metadata(file_path)
        
        # Format duration
        duration_seconds = file_info['duration_seconds']
        minutes = int(duration_seconds // 60)
        seconds = int(duration_seconds % 60)
        duration_str = f"{minutes}:{seconds:02d}"
        
        # Create a table for file information
        info_table = Table(title="[bold green]MP3 File Information[/bold green]", border_style="green")
        info_table.add_column("Property", style="cyan", no_wrap=True)
        info_table.add_column("Value", style="white")
        
        info_table.add_row("File", file_info['file_path'])
        info_table.add_row("Size", f"{file_info['file_size']:,} bytes ({file_info['file_size'] / 1024 / 1024:.2f} MB)")
        info_table.add_row("Duration", duration_str)
        info_table.add_row("Bitrate", f"{file_info['bitrate'] // 1000} kbps" if file_info['bitrate'] else "Unknown")
        info_table.add_row("Sample Rate", f"{file_info['sample_rate']} Hz" if file_info['sample_rate'] else "Unknown")
        
        console.print(info_table)
        
        if tags:
            # Create a table for metadata
            metadata_table = Table(title="[bold yellow]Metadata Tags[/bold yellow]", border_style="yellow")
            metadata_table.add_column("Tag", style="cyan", no_wrap=True)
            metadata_table.add_column("ID3 Key", style="dim")
            metadata_table.add_column("Value", style="white")
            
            for key, value in tags.items():
                readable_name = ID3_TAG_NAMES.get(key, key)
                metadata_table.add_row(readable_name, key, str(value))
            
            console.print(metadata_table)
        else:
            console.print(Panel("No metadata tags found", title="[yellow]Metadata[/yellow]", border_style="yellow"))
            
    except Exception as e:
        console.print(f"[bold red]Error reading MP3 file: {e}[/bold red]")
        raise typer.Exit(1)

@app.command()
def enrich(file_path: str = typer.Argument(..., help="Path to the MP3 file to enrich with Bandcamp metadata")):
    """Enrich an MP3 file with metadata from Bandcamp"""
    
    try:
        # Enrich the file
        result = enrich_mp3_file(file_path)
        
        # Display results
        console.print(Panel(
            f"[bold green]Successfully enriched: {result['file_path']}[/bold green]",
            title="[bold green]Enrichment Complete[/bold green]",
            border_style="green"
        ))
        
        # Show search details
        search_panel = Panel(
            f"[cyan]Search Query:[/cyan] {result['search_query']}\n"
            f"[cyan]Found Track:[/cyan] {result['bandcamp_track'].get('band_name', 'Unknown')} - {result['bandcamp_track'].get('name', 'Unknown')} (URL: {result['bandcamp_track'].get('item_url_path', 'Unknown')})\n"
            f"[cyan]Album:[/cyan] {result['bandcamp_track'].get('album_name', 'Unknown')}",
            title="[bold blue]Search Results[/bold blue]",
            border_style="blue"
        )
        console.print(search_panel)
        
        # Show what metadata was added
        # Filter out "skipped" entries to only show actually added metadata
        actual_added_metadata = {k: v for k, v in result['added_metadata'].items() 
                               if not str(v).startswith('Artwork already exists') and 
                               not str(v).startswith('No new metadata')}
        
        if actual_added_metadata:
            added_table = Table(title="[bold green]New Metadata Added[/bold green]", border_style="green")
            added_table.add_column("Tag", style="cyan", no_wrap=True)
            added_table.add_column("ID3 Key", style="dim")
            added_table.add_column("Value", style="white")
            
            for key, value in actual_added_metadata.items():
                readable_name = ID3_TAG_NAMES.get(key, key)
                added_table.add_row(readable_name, key, str(value))
            
            console.print(added_table)
        else:
            console.print(Panel(
                "No new metadata was added - all fields already had values",
                title="[yellow]No Changes[/yellow]",
                border_style="yellow"
            ))
        
        # Show existing metadata for comparison
        if result['existing_metadata']:
            existing_table = Table(title="[bold yellow]Existing Metadata[/bold yellow]", border_style="yellow")
            existing_table.add_column("Tag", style="cyan", no_wrap=True)
            existing_table.add_column("ID3 Key", style="dim")
            existing_table.add_column("Value", style="white")
            
            for key, value in result['existing_metadata'].items():
                readable_name = ID3_TAG_NAMES.get(key, key)
                existing_table.add_row(readable_name, key, str(value))
            
            console.print(existing_table)
            
    except Exception as e:
        console.print(f"[bold red]Error enriching MP3 file: {e}[/bold red]")
        
        raise typer.Exit(1)

@app.command()
def enrich_mb(file_path: str = typer.Argument(..., help="Path to the MP3 file to enrich with MusicBrainz metadata")):
    """Enrich an MP3 file with metadata from MusicBrainz"""
    
    try:
        # Enrich the file
        result = enrich_mp3_file_musicbrainz(file_path)
        
        # Display results
        console.print(Panel(
            f"[bold green]Successfully enriched: {result['file_path']}[/bold green]",
            title="[bold green]MusicBrainz Enrichment Complete[/bold green]",
            border_style="green"
        ))
        
        # Show search details
        recording = result['musicbrainz_recording']
        artist_name = ""
        if 'artist-credit' in recording and recording['artist-credit']:
            artist_names = []
            for artist_credit in recording['artist-credit']:
                if isinstance(artist_credit, dict) and 'name' in artist_credit:
                    artist_names.append(artist_credit['name'])
                elif isinstance(artist_credit, str):
                    artist_names.append(artist_credit)
            artist_name = ' '.join(artist_names)
        
        search_panel = Panel(
            f"[cyan]Search Query:[/cyan] {result['search_query']}\n"
            f"[cyan]Found Track:[/cyan] {artist_name} - {recording.get('title', 'Unknown')}\n"
            f"[cyan]Recording ID:[/cyan] {recording.get('id', 'Unknown')}",
            title="[bold green]MusicBrainz Search Results[/bold green]",
            border_style="green"
        )
        console.print(search_panel)
        
        # Show what metadata was added
        # Filter out "skipped" entries to only show actually added metadata
        actual_added_metadata = {k: v for k, v in result['added_metadata'].items() 
                               if not str(v).startswith('Artwork already exists') and 
                               not str(v).startswith('No new metadata')}
        
        if actual_added_metadata:
            added_table = Table(title="[bold green]New Metadata Added[/bold green]", border_style="green")
            added_table.add_column("Tag", style="cyan", no_wrap=True)
            added_table.add_column("ID3 Key", style="dim")
            added_table.add_column("Value", style="white")
            
            for key, value in actual_added_metadata.items():
                readable_name = ID3_TAG_NAMES.get(key, key)
                added_table.add_row(readable_name, key, str(value))
            
            console.print(added_table)
        else:
            console.print(Panel(
                "No new metadata was added - all fields already had values",
                title="[yellow]No Changes[/yellow]",
                border_style="yellow"
            ))
        
        # Show existing metadata for comparison
        if result['existing_metadata']:
            existing_table = Table(title="[bold yellow]Existing Metadata[/bold yellow]", border_style="yellow")
            existing_table.add_column("Tag", style="cyan", no_wrap=True)
            existing_table.add_column("ID3 Key", style="dim")
            existing_table.add_column("Value", style="white")
            
            for key, value in result['existing_metadata'].items():
                readable_name = ID3_TAG_NAMES.get(key, key)
                existing_table.add_row(readable_name, key, str(value))
            
            console.print(existing_table)
            
    except Exception as e:
        console.print(f"[bold red]Error enriching MP3 file with MusicBrainz: {e}[/bold red]")
        
        raise typer.Exit(1)

if __name__ == "__main__":
    app()