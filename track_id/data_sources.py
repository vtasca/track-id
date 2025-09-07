"""Data source abstraction for unified search and enrichment."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from .mp3_utils import MP3File


def extract_artist_name_from_credits(artist_credits: List[Any]) -> str:
    """Extract artist name from various artist credit formats."""
    if not artist_credits:
        return ""
    
    artist_names = []
    for artist_credit in artist_credits:
        if isinstance(artist_credit, dict) and 'name' in artist_credit:
            artist_names.append(artist_credit['name'])
        elif isinstance(artist_credit, str):
            artist_names.append(artist_credit)
    
    return ' '.join(artist_names)


class DataSource(ABC):
    """Abstract base class for all data sources."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def search(self, search_text: str) -> Dict[str, Any]:
        """Search for tracks using the data source's API."""
        pass
    
    @abstractmethod
    def find_matching_track(self, search_results: Dict[str, Any], artist: str, title: str) -> Optional[Dict[str, Any]]:
        """Find a matching track from search results."""
        pass
    
    @abstractmethod
    def extract_metadata(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from track data."""
        pass
    
    def enrich_mp3_file(self, file_path: str) -> Dict[str, Any]:
        """
        Enrich an MP3 file with metadata from this data source.
        This is the common implementation that all data sources can use.
        """
        # Create MP3File instance
        mp3_file = MP3File(file_path)
        
        # Extract artist and title from existing metadata for search
        artist = mp3_file.metadata.get('TPE1', '')
        title = mp3_file.metadata.get('TIT2', '')
        
        # If metadata is missing, try to parse from filename
        if not artist or not title:
            filename_artist, filename_title = mp3_file.parsed_filename
            if filename_artist and filename_title:
                artist = filename_artist
                title = filename_title
            else:
                raise ValueError("Cannot enrich file: missing artist and title metadata in both ID3 tags and filename")
        
        # Search using the data source's search method
        search_text = self._build_search_query(artist, title)
        search_results = self.search(search_text)
        
        # Find matching track
        matching_track = self.find_matching_track(search_results, artist, title)
        
        if not matching_track:
            raise ValueError(f"No matching track found on {self.name} for '{artist} - {title}'")
        
        # Get detailed track information (if needed)
        detailed_track = self._get_detailed_track_info(matching_track)
        
        # Extract metadata from the data source
        source_metadata = self.extract_metadata(detailed_track)
        
        # Update MP3 file with new metadata
        added_metadata = mp3_file.update_metadata(source_metadata)
        
        return {
            'file_path': file_path,
            'search_query': search_text,
            f'{self.name.lower()}_track': detailed_track,
            'existing_metadata': mp3_file.metadata,
            f'{self.name.lower()}_metadata': source_metadata,
            'added_metadata': added_metadata
        }
    
    def _build_search_query(self, artist: str, title: str) -> str:
        """Build search query from artist and title. Override in subclasses if needed."""
        return f"{artist} - {title}"
    
    def _get_detailed_track_info(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed track information. Override in subclasses if needed."""
        return track_data
    
    def get_display_name(self) -> str:
        """Get the display name for this data source."""
        return self.name


class DataSourceRegistry:
    """Registry for managing available data sources."""
    
    def __init__(self):
        self._sources: List[DataSource] = []
    
    def register(self, source: DataSource) -> None:
        """Register a new data source."""
        self._sources.append(source)
    
    def get_all_sources(self) -> List[DataSource]:
        """Get all registered data sources."""
        return self._sources.copy()
    
    def get_source_by_name(self, name: str) -> Optional[DataSource]:
        """Get a data source by name."""
        for source in self._sources:
            if source.name == name:
                return source
        return None


# Global registry instance
data_source_registry = DataSourceRegistry()


def search_all_sources(search_text: str) -> Dict[str, Any]:
    """Search all registered data sources and return combined results."""
    results = {}
    
    for source in data_source_registry.get_all_sources():
        try:
            source_results = source.search(search_text)
            results[source.name] = {
                'success': True,
                'data': source_results,
                'source': source
            }
        except Exception as e:
            results[source.name] = {
                'success': False,
                'error': str(e),
                'source': source
            }
    
    return results


def enrich_with_all_sources(file_path: str) -> Dict[str, Any]:
    """Enrich an MP3 file using all available data sources."""
    # Create MP3File instance
    mp3_file = MP3File(file_path)
    
    # Extract artist and title from existing metadata for search
    artist = mp3_file.metadata.get('TPE1', '')
    title = mp3_file.metadata.get('TIT2', '')
    
    # If metadata is missing, try to parse from filename
    if not artist or not title:
        filename_artist, filename_title = mp3_file.parsed_filename
        if filename_artist and filename_title:
            artist = filename_artist
            title = filename_title
        else:
            raise ValueError("Cannot enrich file: missing artist and title metadata in both ID3 tags and filename")
    
    # Try each data source until one succeeds
    search_text = f"{artist} - {title}"
    enrichment_results = {}
    successful_enrichment = None
    
    for source in data_source_registry.get_all_sources():
        try:
            result = source.enrich_mp3_file(file_path)
            enrichment_results[source.name] = {
                'success': True,
                'data': result,
                'source': source
            }
            if successful_enrichment is None:
                successful_enrichment = result
        except Exception as e:
            enrichment_results[source.name] = {
                'success': False,
                'error': str(e),
                'source': source
            }
    
    if successful_enrichment is None:
        raise ValueError(f"No data source could enrich the file '{file_path}'")
    
    return {
        'file_path': file_path,
        'search_query': search_text,
        'successful_enrichment': successful_enrichment,
        'all_results': enrichment_results
    }
