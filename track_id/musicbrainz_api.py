import requests
import time
from typing import Dict, List, Optional, Any, Tuple
from .mp3_utils import (
    get_mp3_metadata, 
    update_mp3_metadata, 
    parse_artist_title_from_filename
)

# MusicBrainz API configuration
MUSICBRAINZ_API_BASE = "https://musicbrainz.org/ws/2"
USER_AGENT = "track-id/1.0.0 (https://github.com/your-repo/track-id)"

def search_musicbrainz(search_text: str, entity_type: str = "recording") -> Dict[str, Any]:
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

def lookup_recording(recording_id: str, includes: List[str] = None) -> Dict[str, Any]:
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

def find_matching_track(search_results: Dict[str, Any], artist: str, title: str) -> Optional[Dict[str, Any]]:
    """Find the first track result that matches the given artist and title"""
    if 'recordings' not in search_results:
        return None
    
    # First, try to find exact track matches
    for recording in search_results['recordings']:
        recording_title = recording.get('title', '').lower()
        recording_artist = ''
        
        # Get artist name from the recording
        if 'artist-credit' in recording and recording['artist-credit']:
            # Join all artist names (handles collaborations)
            artist_names = []
            for artist_credit in recording['artist-credit']:
                if isinstance(artist_credit, dict) and 'name' in artist_credit:
                    artist_names.append(artist_credit['name'])
                elif isinstance(artist_credit, str):
                    artist_names.append(artist_credit)
            recording_artist = ' '.join(artist_names).lower()
        
        # Check if artist and title match (allowing partial matches)
        if (artist.lower() in recording_artist or recording_artist in artist.lower()) and \
           (title.lower() in recording_title or recording_title in title.lower()):
            return recording
    
    return None

def extract_musicbrainz_metadata(recording_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract metadata from MusicBrainz recording data"""
    metadata = {}
    
    # Title
    if 'title' in recording_data:
        metadata['TIT2'] = recording_data['title']
    
    # Artist
    if 'artist-credit' in recording_data and recording_data['artist-credit']:
        artist_names = []
        for artist_credit in recording_data['artist-credit']:
            if isinstance(artist_credit, dict) and 'name' in artist_credit:
                artist_names.append(artist_credit['name'])
            elif isinstance(artist_credit, str):
                artist_names.append(artist_credit)
        metadata['TPE1'] = ' '.join(artist_names)
    
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

def enrich_mp3_file_musicbrainz(file_path: str) -> Dict[str, Any]:
    """Main function to enrich an MP3 file with MusicBrainz metadata"""
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
    
    # Search MusicBrainz
    search_text = f'artist:"{artist}" AND recording:"{title}"'
    search_results = search_musicbrainz(search_text)
    
    # Find matching track
    matching_track = find_matching_track(search_results, artist, title)
    
    if not matching_track:
        raise ValueError(f"No matching track found on MusicBrainz for '{artist} - {title}'")
    
    # Get detailed recording information
    recording_id = matching_track['id']
    detailed_recording = lookup_recording(recording_id)
    
    # Extract metadata from MusicBrainz
    musicbrainz_metadata = extract_musicbrainz_metadata(detailed_recording)
    
    # Update MP3 file with new metadata
    added_metadata = update_mp3_metadata(file_path, musicbrainz_metadata, existing_metadata)
    
    return {
        'file_path': file_path,
        'search_query': search_text,
        'musicbrainz_recording': detailed_recording,
        'existing_metadata': existing_metadata,
        'musicbrainz_metadata': musicbrainz_metadata,
        'added_metadata': added_metadata
    } 