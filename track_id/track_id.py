import typer
import importlib.metadata
from .display import (
    console, 
    display_search_results, 
    display_file_info_table, 
    display_metadata_table,
    display_error
)
from .enrichment_handlers import (
    handle_bandcamp_enrichment,
    handle_musicbrainz_enrichment
)
from .bandcamp_api import search_bandcamp
from .musicbrainz_api import search_musicbrainz
from .mp3_utils import get_mp3_info, get_mp3_metadata

def version_callback(value: bool):
    """Print version and exit."""
    if value:
        try:
            version = importlib.metadata.version("track_id")
            console.print(f"track-id version {version}")
        except importlib.metadata.PackageNotFoundError:
            console.print("track-id version unknown (package not installed)")
        raise typer.Exit()

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich"
)

@app.callback()
def main(
    version: bool = typer.Option(
        False, 
        "-V", 
        "--version", 
        help="Show version and exit",
        callback=version_callback,
        is_eager=True
    )
):
    """Track ID - MP3 metadata enrichment tool"""
    pass

@app.command()
def search(search_text: str = typer.Argument(..., help="The text to search for")):
    """Search for a track on Bandcamp"""

    try:
        data = search_bandcamp(search_text)
        display_search_results(data, "Bandcamp Search Results", "blue")
    except Exception as e:
        display_error(str(e))
        raise typer.Exit(1)

@app.command()
def search_mb(search_text: str = typer.Argument(..., help="The text to search for")):
    """Search for a track on MusicBrainz"""

    try:
        data = search_musicbrainz(search_text)
        display_search_results(data, "MusicBrainz Search Results", "green")
    except Exception as e:
        display_error(str(e))
        raise typer.Exit(1)

@app.command()
def info(file_path: str = typer.Argument(..., help="Path to the MP3 file")):
    """Display information about an MP3 file"""
    
    try:
        # Get file information and metadata
        file_info = get_mp3_info(file_path)
        tags = get_mp3_metadata(file_path)
        
        # Display file information and metadata
        display_file_info_table(file_info)
        display_metadata_table(tags)
            
    except Exception as e:
        display_error(f"Error reading MP3 file: {e}")
        raise typer.Exit(1)

@app.command()
def enrich(file_path: str = typer.Argument(..., help="Path to the MP3 file to enrich with Bandcamp metadata")):
    """Enrich an MP3 file with metadata from Bandcamp"""
    handle_bandcamp_enrichment(file_path)

@app.command()
def enrich_mb(file_path: str = typer.Argument(..., help="Path to the MP3 file to enrich with MusicBrainz metadata")):
    """Enrich an MP3 file with metadata from MusicBrainz"""
    handle_musicbrainz_enrichment(file_path)

if __name__ == "__main__":
    app()