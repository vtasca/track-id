import requests
from typing import Dict, List, Optional, Any, Tuple
from .mp3_utils import (
    get_mp3_metadata, 
    update_mp3_metadata, 
    parse_artist_title_from_filename
)

def search_bandcamp(search_text: str) -> Dict[str, Any]:
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

    response = requests.post(
        'https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic',
        headers=headers, 
        json=payload
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Bandcamp API error: {response.status_code} - {response.text}")

def find_matching_track(search_results: Dict[str, Any], artist: str, title: str) -> Optional[Dict[str, Any]]:
    """Find the first track result that matches the given artist and title"""
    if 'auto' not in search_results:
        return None
    
    # First, try to find exact track matches
    for result in search_results['auto']['results']:
        if result.get('type') == 't':
            result_artist = result.get('band_name', '').lower()
            result_title = result.get('name', '').lower()
            
            if (artist.lower() in result_artist or result_artist in artist.lower()) and \
               (title.lower() in result_title or result_title in title.lower()):
                return result
    
    return None

def extract_bandcamp_metadata(track_data: Dict[str, Any]) -> Dict[str, Any]:
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

def enrich_mp3_file(file_path: str) -> Dict[str, Any]:
    """Main function to enrich an MP3 file with Bandcamp metadata"""
    # Get existing metadata
    existing_metadata = get_mp3_metadata(file_path)
    
    # Extract artist and title from existing metadata for search
    artist = existing_metadata.get('TPE1', '')
    title = existing_metadata.get('TIT2', '')
    
    # If metadata is missing, try to parse from filename
    if not artist or not title:
        filename_artist, filename_title = parse_artist_title_from_filename(file_path)
        if filename_artist and filename_title:
            artist = filename_artist
            title = filename_title
        else:
            raise ValueError("Cannot enrich file: missing artist and title metadata in both ID3 tags and filename")
    
    # Search Bandcamp
    search_text = f"{artist} - {title}"
    search_results = search_bandcamp(search_text)
    
    # Find matching track
    matching_track = find_matching_track(search_results, artist, title)
    
    if not matching_track:
        raise ValueError(f"No matching track found on Bandcamp for '{artist} - {title}'")
    
    # Extract metadata from Bandcamp
    bandcamp_metadata = extract_bandcamp_metadata(matching_track)
    
    # Update MP3 file with new metadata
    added_metadata = update_mp3_metadata(file_path, bandcamp_metadata, existing_metadata)
    
    return {
        'file_path': file_path,
        'search_query': search_text,
        'bandcamp_track': matching_track,
        'existing_metadata': existing_metadata,
        'bandcamp_metadata': bandcamp_metadata,
        'added_metadata': added_metadata
    }