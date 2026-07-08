"""Data source abstraction for unified search and enrichment."""

import difflib
import importlib.metadata
import re
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .mp3_utils import MP3File

# Applied to every metadata API call so a stalled host can't hang a command;
# enrichment runs sources in a thread pool and a hung thread blocks the merge.
# (connect, read): MusicBrainz's search cluster intermittently takes 10s+ to
# answer, so the read timeout caps how long one slow source can gate results.
DEFAULT_HTTP_TIMEOUT = (5.0, 10.0)


def _package_version() -> str:
    try:
        return importlib.metadata.version("track-id")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


# Identifying User-Agent as required by the MusicBrainz and Discogs API terms.
USER_AGENT = f"track-id/{_package_version()} (https://github.com/vtasca/track-id)"


def make_retrying_session() -> requests.Session:
    """Build a Session that retries transient failures (429/5xx) with backoff.

    POST is included in the allowed methods because the only POST we issue is
    Bandcamp's search, which is idempotent.
    """
    session = requests.Session()
    retry = Retry(
        total=3,
        # Never re-issue a request after a read timeout: against a hanging
        # host that would multiply the worst-case wait by the retry count.
        read=0,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


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


# Decorations that vary between catalogs without changing track identity.
_PARENTHETICAL_RE = re.compile(r"[(\[][^)\]]*[)\]]")
_FEAT_RE = re.compile(r"\b(?:feat|ft|featuring)\.?\s.*$", re.IGNORECASE)

# Minimum combined score for a candidate to count as a match. Below this,
# returning nothing beats writing another track's metadata onto the file.
MATCH_SCORE_THRESHOLD = 0.7

T = TypeVar("T")


def normalize_for_match(s: str) -> str:
    """Lowercase and strip decorations (parentheticals, feat. credits,
    punctuation) that differ between catalogs for the same track."""
    s = s.lower()
    s = _PARENTHETICAL_RE.sub(" ", s)
    s = _FEAT_RE.sub(" ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def _field_similarity(wanted: str, candidate: str) -> float:
    """Similarity (0..1) of one field, dominated by the normalized strings.

    Containment of normalized strings is treated as near-certain — "xtal"
    inside "xtal remastered" is the same track even though the raw ratio is
    mediocre. A small raw-string term acts as a tiebreaker so an undecorated
    exact match outranks a decorated variant ("Xtal" beats "Xtal (Cover)").
    """
    wanted_norm = normalize_for_match(wanted)
    cand_norm = normalize_for_match(candidate)

    sim = difflib.SequenceMatcher(None, wanted_norm, cand_norm).ratio()
    if wanted_norm and cand_norm and (wanted_norm in cand_norm or cand_norm in wanted_norm):
        sim = max(sim, 0.9)

    raw_sim = difflib.SequenceMatcher(None, wanted.lower(), candidate.lower()).ratio()
    return min(1.0, 0.9 * sim + 0.1 * raw_sim)


def match_score(candidate_artist: str, candidate_title: str, artist: str, title: str) -> float:
    """Score (0..1) how well a candidate matches the searched artist/title."""
    title_sim = _field_similarity(title, candidate_title)
    artist_sim = _field_similarity(artist, candidate_artist)
    return 0.6 * title_sim + 0.4 * artist_sim


def find_best_match(
    candidates: List[T],
    artist: str,
    title: str,
    get_artist: Callable[[T], str],
    get_title: Callable[[T], str],
) -> Optional[T]:
    """Return the highest-scoring candidate, or None if none clears the
    match threshold. Replaces first-substring-hit matching, which picked the
    first plausible result instead of the best one."""
    best: Optional[T] = None
    best_score = 0.0
    for candidate in candidates:
        score = match_score(get_artist(candidate), get_title(candidate), artist, title)
        if score > best_score:
            best, best_score = candidate, score
    return best if best_score >= MATCH_SCORE_THRESHOLD else None


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


def search_all_sources(
    search_text: str,
    registry: DataSourceRegistry,
    on_source_done: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Search all registered data sources concurrently and return combined results.

    Sources are independent hosts and I/O bound, so total latency is the
    slowest source rather than the sum — MusicBrainz alone intermittently
    takes several seconds while the others answer in under one.

    ``on_source_done(name, result)`` fires from the calling thread as each
    source finishes, so the CLI can stream results as they arrive. The
    returned dict is always in registry order.
    """
    sources = registry.get_all_sources()
    if not sources:
        return {}

    completed: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        future_to_source = {
            executor.submit(source.search, search_text): source
            for source in sources
        }
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                result = {'success': True, 'data': future.result(), 'source': source}
            except Exception as e:
                result = {'success': False, 'error': str(e), 'source': source}
            completed[source.name] = result
            if on_source_done:
                on_source_done(source.name, result)

    return {source.name: completed[source.name] for source in sources}


def enrich_with_all_sources(
    file_path: str,
    registry: DataSourceRegistry,
    force: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
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

    sources = registry.get_all_sources()

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
    added_metadata = (
        mp3_file.update_metadata(merged_metadata, force=force, dry_run=dry_run)
        if merged_metadata
        else {}
    )

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
