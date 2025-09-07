"""Unified API functions that work with all available data sources."""

from typing import Dict, Any
from .data_sources import data_source_registry, search_all_sources, enrich_with_all_sources
from .bandcamp_api import BandcampDataSource
from .musicbrainz_api import MusicBrainzDataSource


def initialize_data_sources():
    """Initialize and register all available data sources."""
    # Register Bandcamp data source
    bandcamp_source = BandcampDataSource()
    data_source_registry.register(bandcamp_source)
    
    # Register MusicBrainz data source
    musicbrainz_source = MusicBrainzDataSource()
    data_source_registry.register(musicbrainz_source)


def search(query: str) -> Dict[str, Any]:
    """
    Search for tracks across all available data sources.
    
    Args:
        query: The search query string
        
    Returns:
        Dictionary containing results from all data sources
    """
    return search_all_sources(query)


def enrich(file_path: str) -> Dict[str, Any]:
    """
    Enrich an MP3 file using all available data sources.
    
    Args:
        file_path: Path to the MP3 file to enrich
        
    Returns:
        Dictionary containing enrichment results from all data sources
    """
    return enrich_with_all_sources(file_path)


# Initialize data sources when module is imported
initialize_data_sources()
