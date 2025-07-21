import requests
from typing import Dict, List, Optional, Any, Tuple
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCOM, TXXX, APIC
import os
import tempfile
import re

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

def download_artwork(url: str) -> Optional[bytes]:
    """Download artwork from a URL and return the image data as bytes"""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.6312.86 Safari/537.36"
            ),
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        return response.content
    except Exception as e:
        print(f"Warning: Could not download artwork from {url}: {e}")
        return None

def get_mime_type(url: str, content: bytes) -> str:
    """Detect MIME type from URL or content"""
    # Try to get MIME type from URL extension
    if url.lower().endswith('.png'):
        return 'image/png'
    elif url.lower().endswith('.jpg') or url.lower().endswith('.jpeg'):
        return 'image/jpeg'
    elif url.lower().endswith('.gif'):
        return 'image/gif'
    elif url.lower().endswith('.webp'):
        return 'image/webp'
    
    # Try to detect from content magic bytes
    if content.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    elif content.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    elif content.startswith(b'GIF87a') or content.startswith(b'GIF89a'):
        return 'image/gif'
    elif content.startswith(b'RIFF') and content[8:12] == b'WEBP':
        return 'image/webp'
    
    # Default to JPEG
    return 'image/jpeg'

def get_mp3_metadata(file_path: str) -> Dict[str, str]:
    """Get existing metadata from an MP3 file"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' does not exist")
    
    if not file_path.lower().endswith('.mp3'):
        raise ValueError(f"File '{file_path}' is not an MP3 file")
    
    tags = {}
    try:
        id3 = ID3(file_path)
        for key, value in id3.items():
            if hasattr(value, 'text'):
                tags[key] = value.text[0] if value.text else ""
            elif key.startswith('APIC:'):
                # Handle artwork tags
                if hasattr(value, 'mime'):
                    tags[key] = f"Artwork ({value.mime[0] if value.mime else 'unknown'})"
                else:
                    tags[key] = "Artwork"
    except:
        pass
    
    return tags

def get_mp3_info(file_path: str) -> Dict[str, Any]:
    """Get basic information about an MP3 file"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' does not exist")
    
    if not file_path.lower().endswith('.mp3'):
        raise ValueError(f"File '{file_path}' is not an MP3 file")
    
    audio = MP3(file_path)
    file_size = os.path.getsize(file_path)
    duration_seconds = audio.info.length if audio.info else 0
    
    return {
        'file_path': file_path,
        'file_size': file_size,
        'duration_seconds': duration_seconds,
        'bitrate': audio.info.bitrate if audio.info else None,
        'sample_rate': audio.info.sample_rate if audio.info else None
    }

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

def update_mp3_metadata(file_path: str, new_metadata: Dict[str, Any], existing_metadata: Dict[str, str]) -> Dict[str, Any]:
    """Update MP3 file with new metadata, only for fields that don't already have values"""
    added_metadata = {}
    
    try:
        # Load existing ID3 tags or create new ones
        try:
            id3 = ID3(file_path)
        except:
            id3 = ID3()
        
        # Map of ID3 tag keys to their corresponding classes
        tag_classes = {
            'TIT2': TIT2,  # Title
            'TPE1': TPE1,  # Artist
            'TALB': TALB,  # Album
            'TDRC': TDRC,  # Year
            'TCOM': TCOM,  # Composer
            'TXXX': TXXX   # Custom
        }
        
        for key, value in new_metadata.items():
            # Skip artwork_url as it's handled separately
            if key == 'artwork_url':
                continue
                
            # Only add if the field is empty in existing metadata
            if key not in existing_metadata or not existing_metadata[key]:
                if key in tag_classes:
                    id3[key] = tag_classes[key](encoding=3, text=value)
                    added_metadata[key] = value
        
        # Handle artwork separately
        if 'artwork_url' in new_metadata and new_metadata['artwork_url']:
            # Check if artwork already exists
            existing_artwork = any(key.startswith('APIC') for key in id3.keys())
            
            if not existing_artwork:
                # Only add artwork if none exists
                artwork_data = download_artwork(new_metadata['artwork_url'])
                if artwork_data:
                    # Detect MIME type
                    mime_type = get_mime_type(new_metadata['artwork_url'], artwork_data)
                    
                    # Add new artwork
                    id3['APIC:'] = APIC(
                        encoding=3,
                        mime=mime_type,
                        type=3,  # 3 = cover (front)
                        desc='Cover (front)',
                        data=artwork_data
                    )
                    added_metadata['artwork'] = f'Added album artwork ({mime_type})'
            else:
                # Artwork already exists, skip adding
                added_metadata['artwork'] = 'Artwork already exists, skipped'
        
        # Save the updated tags
        id3.save(file_path)
        
        return added_metadata
        
    except Exception as e:
        raise Exception(f"Error updating MP3 metadata: {e}")

def parse_artist_title_from_filename(file_path: str) -> Tuple[str, str]:
    """Parse artist and title from filename using common patterns"""
    filename = os.path.basename(file_path)
    # Remove .mp3 extension
    name_without_ext = os.path.splitext(filename)[0]

    name_without_ext = re.sub(r'\[.*?\]', '', name_without_ext).strip()
    
    # Common patterns: artist - title, artist-title, artist:title
    patterns = [
        r'^(.+?)\s*-\s*(.+)$',  # artist - title
        r'^(.+?)\s*:\s*(.+)$',  # artist:title
    ]
    
    for pattern in patterns:
        match = re.match(pattern, name_without_ext, re.IGNORECASE)
        if match:
            artist = match.group(1).strip()
            title = match.group(2).strip()
            if artist and title:
                return artist, title
    
    # If no pattern matches, return empty strings
    return '', ''

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