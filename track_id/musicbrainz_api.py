from typing import Any, Dict, List, Optional, Tuple, Union

from .data_sources import (
    DEFAULT_HTTP_TIMEOUT,
    USER_AGENT,
    DataSource,
    RateLimiter,
    extract_artist_name_from_credits,
    find_best_match,
    make_retrying_session,
)

# MusicBrainz API configuration
MUSICBRAINZ_API_BASE = "https://musicbrainz.org/ws/2"


class MusicBrainzDataSource(DataSource):
    """MusicBrainz data source implementation."""

    def __init__(self):
        super().__init__("MusicBrainz")
        self._session = make_retrying_session()
        # MusicBrainz allows max 1 request per second; the limiter only waits
        # for the time remaining since this source's previous call.
        self._rate_limiter = RateLimiter(1.0)
    
    def search(self, search_text: str, entity_type: str = "recording") -> Dict[str, Any]:
        """Search for tracks on MusicBrainz and return the raw API response"""
        
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }

        params: Dict[str, Union[str, int]] = {
            'query': search_text,
            'fmt': 'json',
            'limit': 25
        }

        # Rate limiting: MusicBrainz requires max 1 request per second
        self._rate_limiter.wait()

        response = self._session.get(
            f'{MUSICBRAINZ_API_BASE}/{entity_type}',
            headers=headers,
            params=params,
            timeout=DEFAULT_HTTP_TIMEOUT
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"MusicBrainz API error: {response.status_code} - {response.text}")

    def lookup_recording(self, recording_id: str, includes: Optional[List[str]] = None) -> Dict[str, Any]:
        """Look up detailed information about a specific recording"""
        
        if includes is None:
            # release-groups is needed to spot compilations when picking a release
            includes = ['artists', 'releases', 'release-groups', 'tags']
        
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }

        params: Dict[str, str] = {
            'fmt': 'json',
            'inc': '+'.join(includes)
        }

        # Rate limiting: MusicBrainz requires max 1 request per second
        self._rate_limiter.wait()

        response = self._session.get(
            f'{MUSICBRAINZ_API_BASE}/recording/{recording_id}',
            headers=headers,
            params=params,
            timeout=DEFAULT_HTTP_TIMEOUT
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"MusicBrainz API error: {response.status_code} - {response.text}")

    def find_matching_track(self, search_results: Dict[str, Any], artist: str, title: str) -> Optional[Dict[str, Any]]:
        """Find the best-scoring recording for the given artist and title"""
        if 'recordings' not in search_results:
            return None

        return find_best_match(
            search_results['recordings'],
            artist,
            title,
            get_artist=lambda r: extract_artist_name_from_credits(r.get('artist-credit', [])),
            get_title=lambda r: r.get('title', ''),
        )

    def extract_metadata(self, recording_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from MusicBrainz recording data"""
        metadata = {}
        
        # Title
        if 'title' in recording_data:
            metadata['TIT2'] = recording_data['title']
        
        # Artist
        if 'artist-credit' in recording_data and recording_data['artist-credit']:
            metadata['TPE1'] = extract_artist_name_from_credits(recording_data['artist-credit'])
        
        # Album/Release
        if 'releases' in recording_data and recording_data['releases']:
            release = self._select_release(recording_data['releases'])
            if 'title' in release:
                metadata['TALB'] = release['title']

            # Year from release date
            if 'date' in release and release['date']:
                # Extract year from date (format: YYYY-MM-DD or YYYY)
                date_str = release['date']
                if '-' in date_str:
                    year = date_str.split('-')[0]
                else:
                    year = date_str
                if year.isdigit():
                    metadata['TDRC'] = year

            # Artwork from Cover Art Archive
            if 'id' in release:
                metadata['artwork_url'] = f"https://coverartarchive.org/release/{release['id']}/front"
        
        # Tags/Genres
        if 'tags' in recording_data and recording_data['tags']:
            # Get the most popular tags
            sorted_tags = sorted(recording_data['tags'], key=lambda x: x.get('count', 0), reverse=True)
            top_tags = [tag['name'] for tag in sorted_tags[:3]]  # Top 3 tags
            if top_tags:
                metadata['TXXX:GENRE'] = ', '.join(top_tags)

        return metadata

    @staticmethod
    def _select_release(releases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Pick the release to source album/year/artwork from.

        The API's ordering of a recording's releases is arbitrary, so taking
        releases[0] often lands on a compilation or reissue. Prefer official
        releases, then non-compilations, then the earliest date.
        """
        def sort_key(release: Dict[str, Any]) -> Tuple[int, int, str]:
            status_rank = 0 if release.get('status') == 'Official' else 1
            release_group = release.get('release-group') or {}
            secondary_types = release_group.get('secondary-types') or []
            compilation_rank = 1 if 'Compilation' in secondary_types else 0
            # Missing/partial dates sort last; "YYYY" vs "YYYY-MM-DD" compares fine
            date = release.get('date') or '9999'
            return (status_rank, compilation_rank, date)

        return min(releases, key=sort_key)

    def _build_search_query(self, artist: str, title: str) -> str:
        """Build MusicBrainz-specific search query."""
        return f'artist:"{artist}" AND recording:"{title}"'
    
    def _get_detailed_track_info(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed recording information from MusicBrainz."""
        recording_id = track_data['id']
        return self.lookup_recording(recording_id)

