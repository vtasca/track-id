import requests
import time
from typing import Dict, List, Optional, Any, Tuple
from .mp3_utils import MP3File
from .data_sources import DataSource, extract_artist_name_from_credits

# MusicBrainz API configuration
MUSICBRAINZ_API_BASE = "https://musicbrainz.org/ws/2"
USER_AGENT = "track-id/1.0.0 (https://github.com/vtasca/track-id)"


class MusicBrainzDataSource(DataSource):
    """MusicBrainz data source implementation."""
    
    def __init__(self):
        super().__init__("MusicBrainz")
    
    def search(self, search_text: str, entity_type: str = "recording") -> Dict[str, Any]:
        """Search for tracks on MusicBrainz and return the raw API response"""
        
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }

        params = {
            'query': search_text,
            'fmt': 'json',
            'limit': 25
        }

        # Rate limiting: MusicBrainz requires max 1 request per second
        time.sleep(1)
        
        response = requests.get(
            f'{MUSICBRAINZ_API_BASE}/{entity_type}',
            headers=headers,
            params=params
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"MusicBrainz API error: {response.status_code} - {response.text}")

    def lookup_recording(self, recording_id: str, includes: Optional[List[str]] = None) -> Dict[str, Any]:
        """Look up detailed information about a specific recording"""
        
        if includes is None:
            includes = ['artists', 'releases', 'tags']
        
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }

        params = {
            'fmt': 'json',
            'inc': '+'.join(includes)
        }

        # Rate limiting: MusicBrainz requires max 1 request per second
        time.sleep(1)
        
        response = requests.get(
            f'{MUSICBRAINZ_API_BASE}/recording/{recording_id}',
            headers=headers,
            params=params
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"MusicBrainz API error: {response.status_code} - {response.text}")

    def find_matching_track(self, search_results: Dict[str, Any], artist: str, title: str) -> Optional[Dict[str, Any]]:
        """Find the first track result that matches the given artist and title"""
        if 'recordings' not in search_results:
            return None
        
        # First, try to find exact track matches
        for recording in search_results['recordings']:
            recording_title = recording.get('title', '').lower()
            recording_artist = extract_artist_name_from_credits(
                recording.get('artist-credit', [])
            ).lower()
            
            # Check if artist and title match (allowing partial matches)
            if (artist.lower() in recording_artist or recording_artist in artist.lower()) and \
               (title.lower() in recording_title or recording_title in title.lower()):
                return recording
        
        return None

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
            # Get the first release (usually the main one)
            release = recording_data['releases'][0]
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
        
        # Composer (if available)
        if 'artist-credit' in recording_data and recording_data['artist-credit']:
            # For simplicity, use the first artist as composer
            first_artist = recording_data['artist-credit'][0]
            if isinstance(first_artist, dict) and 'name' in first_artist:
                metadata['TCOM'] = first_artist['name']
            elif isinstance(first_artist, str):
                metadata['TCOM'] = first_artist
        
        # Tags/Genres
        if 'tags' in recording_data and recording_data['tags']:
            # Get the most popular tags
            sorted_tags = sorted(recording_data['tags'], key=lambda x: x.get('count', 0), reverse=True)
            top_tags = [tag['name'] for tag in sorted_tags[:3]]  # Top 3 tags
            if top_tags:
                metadata['TXXX:GENRE'] = ', '.join(top_tags)

        return metadata

    def _build_search_query(self, artist: str, title: str) -> str:
        """Build MusicBrainz-specific search query."""
        return f'artist:"{artist}" AND recording:"{title}"'
    
    def _get_detailed_track_info(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed recording information from MusicBrainz."""
        recording_id = track_data['id']
        return self.lookup_recording(recording_id)

