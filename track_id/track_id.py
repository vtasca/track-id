import typer
import importlib.metadata
from typing import NoReturn
from .display import (
    console, 
    display_search_results, 
    display_file_info_table, 
    display_metadata_table,
    display_error,
    display_unified_search_results,
    display_unified_enrichment_results
)
from .unified_api import search as unified_search, enrich as unified_enrich
from .mp3_utils import MP3File

def version_callback(value: bool) -> None:
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

if __name__ == "__main__":
    app()