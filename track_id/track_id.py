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
from .bandcamp_api import search_bandcamp, enrich_mp3_file
from .musicbrainz_api import search_musicbrainz, enrich_mp3_file_musicbrainz
from .mp3_utils import MP3File

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
        # Create MP3File instance and get information
        mp3_file = MP3File(file_path)
        
        # Display file information and metadata
        display_file_info_table(mp3_file.info)
        display_metadata_table(mp3_file.metadata)
            
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