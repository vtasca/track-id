"""Unified API functions that work with all available data sources."""

from typing import Any, Dict, Optional

from .bandcamp_api import BandcampDataSource
from .data_sources import DataSourceRegistry, enrich_with_all_sources, search_all_sources
from .discogs_api import DiscogsDataSource
from .musicbrainz_api import MusicBrainzDataSource

_registry: Optional[DataSourceRegistry] = None


def get_registry() -> DataSourceRegistry:
    """Build (once) and return the registry of all available data sources.

    Lazy so that importing this module has no side effects and callers/tests
    can construct their own registry with a different set of sources.
    """
    global _registry
    if _registry is None:
        registry = DataSourceRegistry()
        registry.register(BandcampDataSource())
        registry.register(MusicBrainzDataSource())
        registry.register(DiscogsDataSource())
        _registry = registry
    return _registry


def search(query: str) -> Dict[str, Any]:
    """
    Search for tracks across all available data sources.

    Args:
        query: The search query string

    Returns:
        Dictionary containing results from all data sources
    """
    return search_all_sources(query, get_registry())


def enrich(file_path: str, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """
    Enrich an MP3 file using all available data sources.

    Args:
        file_path: Path to the MP3 file to enrich
        force: Overwrite fields that already have values
        dry_run: Report what would be written without modifying the file

    Returns:
        Dictionary containing enrichment results from all data sources
    """
    return enrich_with_all_sources(file_path, get_registry(), force=force, dry_run=dry_run)
