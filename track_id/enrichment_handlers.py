"""Common enrichment handlers to eliminate code duplication."""

import typer
from typing import Callable, Any, Dict
from .display import display_enrichment_success, display_enrichment_results, display_error
from .display import display_bandcamp_search_details, display_musicbrainz_search_details
from .bandcamp_api import BandcampDataSource
from .musicbrainz_api import MusicBrainzDataSource


def handle_enrichment_command(
    file_path: str, 
    enrich_func: Callable[[str], Dict[str, Any]], 
    search_details_func: Callable[[Dict[str, Any]], None], 
    service_name: str = ""
) -> None:
    """
    Common handler for enrichment commands.
    
    Args:
        file_path: Path to the MP3 file to enrich
        enrich_func: Function to call for enrichment (e.g., enrich_mp3_file)
        search_details_func: Function to display service-specific search details
        service_name: Name of the service for display purposes
    """
    try:
        # Enrich the file
        result = enrich_func(file_path)
        
        # Display success message
        display_enrichment_success(result['file_path'], service_name)
        
        # Display all enrichment results
        display_enrichment_results(result, search_details_func)
        
    except Exception as e:
        error_message = f"Error enriching MP3 file"
        if service_name:
            error_message += f" with {service_name}"
        display_error(f"{error_message}: {e}")
        raise typer.Exit(1)


def handle_bandcamp_enrichment(file_path: str) -> None:
    """Handle Bandcamp enrichment command."""
    bandcamp_source = BandcampDataSource()
    handle_enrichment_command(
        file_path=file_path,
        enrich_func=bandcamp_source.enrich_mp3_file,
        search_details_func=display_bandcamp_search_details,
        service_name=""  # Original doesn't have service name in title
    )


def handle_musicbrainz_enrichment(file_path: str) -> None:
    """Handle MusicBrainz enrichment command."""
    musicbrainz_source = MusicBrainzDataSource()
    handle_enrichment_command(
        file_path=file_path,
        enrich_func=musicbrainz_source.enrich_mp3_file,
        search_details_func=display_musicbrainz_search_details,
        service_name="MusicBrainz"
    )
