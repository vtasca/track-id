"""Data source abstraction for unified search and enrichment."""

import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any, Tuple
from .mp3_utils import MP3File


class RateLimiter:
    """Spaces out calls to a single host by at least ``min_interval`` seconds.

    Unlike a bare ``time.sleep`` before every request, this only waits for the
    time *remaining* since the previous call — so the first request of a run
    never pays a delay, and a request that arrives after a natural gap (e.g. the
    network latency of a prior call) waits less or not at all.
    """

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            remaining = self._min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            self._last_call = time.monotonic()


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


def resolve_artist_title(mp3_file: MP3File) -> Tuple[str, str]:
    """Resolve artist and title from ID3 tags, falling back to the filename."""
    artist = mp3_file.metadata.get('TPE1', '')
    title = mp3_file.metadata.get('TIT2', '')

    if not artist or not title:
        filename_artist, filename_title = mp3_file.parsed_filename
        if filename_artist and filename_title:
            artist = filename_artist
            title = filename_title
        else:
            raise ValueError(
                "Cannot enrich file: missing artist and title metadata in both "
                "ID3 tags and filename"
            )

    return artist, title


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
    
    def fetch_metadata(self, artist: str, title: str) -> Dict[str, Any]:
        """Search this source and return the matched track and its metadata.

        Network-only: performs no file I/O, so it is safe to run concurrently
        for several sources against one MP3 file. The caller is responsible for
        merging the returned metadata and writing it to disk.
        """
        search_text = self._build_search_query(artist, title)
        search_results = self.search(search_text)

        matching_track = self.find_matching_track(search_results, artist, title)
        if not matching_track:
            raise ValueError(f"No matching track found on {self.name} for '{artist} - {title}'")

        detailed_track = self._get_detailed_track_info(matching_track)
        source_metadata = self.extract_metadata(detailed_track)

        return {
            'search_query': search_text,
            'detailed_track': detailed_track,
            'source_metadata': source_metadata,
        }

    def enrich_mp3_file(self, file_path: str) -> Dict[str, Any]:
        """
        Enrich an MP3 file with metadata from this data source.
        This is the common implementation that all data sources can use.
        """
        # Create MP3File instance
        mp3_file = MP3File(file_path)

        artist, title = resolve_artist_title(mp3_file)

        # Search the source and extract metadata (network only)
        fetched = self.fetch_metadata(artist, title)
        detailed_track = fetched['detailed_track']
        source_metadata = fetched['source_metadata']

        # Snapshot the metadata that already existed on the file *before* updating.
        # update_metadata() invalidates the cache, so reading mp3_file.metadata
        # afterwards would return the post-update state (including the fields we
        # just added) and make "existing metadata" duplicate "new metadata".
        existing_metadata = dict(mp3_file.metadata)

        # Update MP3 file with new metadata
        added_metadata = mp3_file.update_metadata(source_metadata)

        return {
            'file_path': file_path,
            'search_query': fetched['search_query'],
            f'{self.name.lower()}_track': detailed_track,
            'existing_metadata': existing_metadata,
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
    """Search all registered data sources and return combined results.

    Run sequentially on purpose: each source makes a single request with no
    rate-limit sleep to overlap, and the raw HTTP path serializes under the GIL
    anyway, so a thread pool here adds complexity without reducing latency.
    (Enrichment is different — its rate-limit sleeps do overlap, so
    enrich_with_all_sources parallelizes.)
    """
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
    """Enrich an MP3 file using all available data sources.

    All sources are queried concurrently (they hit independent hosts and are
    I/O bound), then their results are merged in registry order — first source
    to provide a field wins — and written to the file in a single pass. This
    avoids both the serial latency of querying sources one by one and the
    repeated file writes / artwork downloads of writing per source.
    """
    mp3_file = MP3File(file_path)
    artist, title = resolve_artist_title(mp3_file)
    search_text = f"{artist} - {title}"

    sources = data_source_registry.get_all_sources()

    # Snapshot existing metadata before the single write below.
    existing_metadata = dict(mp3_file.metadata)

    # Query every source concurrently. fetch_metadata does no file I/O.
    fetched_by_source: Dict[str, Dict[str, Any]] = {}
    errors_by_source: Dict[str, str] = {}
    if sources:
        with ThreadPoolExecutor(max_workers=len(sources)) as executor:
            future_to_source = {
                executor.submit(source.fetch_metadata, artist, title): source
                for source in sources
            }
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    fetched_by_source[source.name] = future.result()
                except Exception as e:
                    errors_by_source[source.name] = str(e)

    # Merge in registry order: the first source to supply a field wins.
    merged_metadata: Dict[str, Any] = {}
    for source in sources:
        fetched = fetched_by_source.get(source.name)
        if fetched:
            for key, value in fetched['source_metadata'].items():
                merged_metadata.setdefault(key, value)

    # Single write (and at most one artwork download) for all sources combined.
    added_metadata = mp3_file.update_metadata(merged_metadata) if merged_metadata else {}

    # Assemble per-source results in registry order so the display ledger and
    # the "winning" source stay deterministic regardless of completion order.
    enrichment_results: Dict[str, Any] = {}
    successful_enrichment = None
    for source in sources:
        fetched = fetched_by_source.get(source.name)
        if fetched is not None:
            result = {
                'file_path': file_path,
                'search_query': fetched['search_query'],
                f'{source.name.lower()}_track': fetched['detailed_track'],
                'existing_metadata': existing_metadata,
                f'{source.name.lower()}_metadata': fetched['source_metadata'],
                'added_metadata': added_metadata,
            }
            enrichment_results[source.name] = {
                'success': True,
                'data': result,
                'source': source,
            }
            if successful_enrichment is None:
                successful_enrichment = result
        else:
            enrichment_results[source.name] = {
                'success': False,
                'error': errors_by_source.get(source.name, 'unknown error'),
                'source': source,
            }

    if successful_enrichment is None:
        raise ValueError(f"No data source could enrich the file '{file_path}'")

    return {
        'file_path': file_path,
        'search_query': search_text,
        'successful_enrichment': successful_enrichment,
        'all_results': enrichment_results
    }
