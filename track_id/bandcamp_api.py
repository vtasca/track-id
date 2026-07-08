from typing import Any, Dict, Optional

from .data_sources import DEFAULT_HTTP_TIMEOUT, DataSource, find_best_match, make_retrying_session


class BandcampDataSource(DataSource):
    """Bandcamp data source implementation."""

    def __init__(self):
        super().__init__("Bandcamp")
        self._session = make_retrying_session()

    def search(self, search_text: str) -> Dict[str, Any]:
        """Search for tracks on Bandcamp and return the raw API response"""
        
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.6312.86 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

        payload = {
            'fan_id': None,
            'full_page': False,
            'search_filter': '',
            'search_text': search_text
        }

        response = self._session.post(
            'https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic',
            headers=headers,
            json=payload,
            timeout=DEFAULT_HTTP_TIMEOUT
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Bandcamp API error: {response.status_code} - {response.text}")

    def find_matching_track(self, search_results: Dict[str, Any], artist: str, title: str) -> Optional[Dict[str, Any]]:
        """Find the best-scoring track result for the given artist and title"""
        if 'auto' not in search_results:
            return None

        tracks = [r for r in search_results['auto']['results'] if r.get('type') == 't']
        return find_best_match(
            tracks,
            artist,
            title,
            get_artist=lambda r: r.get('band_name', ''),
            get_title=lambda r: r.get('name', ''),
        )

    def extract_metadata(self, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from Bandcamp track data"""
        metadata = {}
        
        if 'name' in track_data:
            metadata['TIT2'] = track_data['name']
        
        if 'band_name' in track_data:
            metadata['TPE1'] = track_data['band_name']
        
        if 'album_name' in track_data:
            metadata['TALB'] = track_data['album_name']
        
        # Extract artwork URL if available
        if 'art_id' in track_data:
            metadata['artwork_url'] = f"https://f4.bcbits.com/img/a{track_data['art_id']}_16.jpg"

        return metadata
