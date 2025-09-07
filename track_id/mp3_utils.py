import requests
from typing import Dict, List, Optional, Any, Tuple
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from mutagen.id3._frames import TIT2, TPE1, TALB, TDRC, TCOM, TXXX, APIC
import os
import re


class MP3File:
    """A class to represent and manage MP3 file information and metadata."""
    
    def __init__(self, file_path: str):
        """
        Initialize MP3File with the given file path.
        
        Args:
            file_path: Path to the MP3 file
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file is not an MP3 file
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File '{file_path}' does not exist")
        
        if not file_path.lower().endswith('.mp3'):
            raise ValueError(f"File '{file_path}' is not an MP3 file")
        
        self.file_path = file_path
        self._info: Optional[Dict[str, Any]] = None
        self._metadata: Optional[Dict[str, str]] = None
        self._parsed_filename: Optional[Tuple[str, str]] = None
    
    @property
    def info(self) -> Dict[str, Any]:
        """Get basic information about the MP3 file (cached)."""
        if self._info is None:
            self._info = self._get_info()
        return self._info
    
    @property
    def metadata(self) -> Dict[str, str]:
        """Get existing metadata from the MP3 file (cached)."""
        if self._metadata is None:
            self._metadata = self._get_metadata()
        return self._metadata
    
    @property
    def parsed_filename(self) -> Tuple[str, str]:
        """Parse artist and title from filename (cached)."""
        if self._parsed_filename is None:
            self._parsed_filename = self._parse_artist_title_from_filename()
        return self._parsed_filename
    
    def _get_info(self) -> Dict[str, Any]:
        """Get basic information about the MP3 file."""
        audio = MP3(self.file_path)
        file_size = os.path.getsize(self.file_path)
        duration_seconds = audio.info.length if audio.info else 0
        
        return {
            'file_path': self.file_path,
            'file_size': file_size,
            'duration_seconds': duration_seconds,
            'bitrate': getattr(audio.info, 'bitrate', None) if audio.info else None,
            'sample_rate': getattr(audio.info, 'sample_rate', None) if audio.info else None
        }
    
    def _get_metadata(self) -> Dict[str, str]:
        """Get existing metadata from the MP3 file."""
        tags = {}
        try:
            id3 = ID3(self.file_path)
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
    
    def _parse_artist_title_from_filename(self) -> Tuple[str, str]:
        """Parse artist and title from filename using common patterns."""
        filename = os.path.basename(self.file_path)
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
    
    def update_metadata(self, new_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update MP3 file with new metadata, only for fields that don't already have values.
        
        Args:
            new_metadata: Dictionary of new metadata to add
            
        Returns:
            Dictionary of metadata that was actually added
            
        Raises:
            Exception: If there's an error updating the metadata
        """
        added_metadata = {}
        
        try:
            # Load existing ID3 tags or create new ones
            try:
                id3 = ID3(self.file_path)
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
                if key not in self.metadata or not self.metadata[key]:
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
            id3.save(self.file_path)
            
            # Invalidate metadata cache since we've updated it
            self._metadata = None
            
            return added_metadata
            
        except Exception as e:
            raise Exception(f"Error updating MP3 metadata: {e}")
    
    def refresh_metadata(self):
        """Refresh the metadata cache by reloading from file."""
        self._metadata = None
    
    def refresh_info(self):
        """Refresh the info cache by reloading from file."""
        self._info = None

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
    """Get existing metadata from an MP3 file (backward compatibility function)"""
    mp3_file = MP3File(file_path)
    return mp3_file.metadata

def get_mp3_info(file_path: str) -> Dict[str, Any]:
    """Get basic information about an MP3 file (backward compatibility function)"""
    mp3_file = MP3File(file_path)
    return mp3_file.info

def update_mp3_metadata(file_path: str, new_metadata: Dict[str, Any], existing_metadata: Dict[str, str]) -> Dict[str, Any]:
    """Update MP3 file with new metadata, only for fields that don't already have values (backward compatibility function)"""
    mp3_file = MP3File(file_path)
    return mp3_file.update_metadata(new_metadata)

def parse_artist_title_from_filename(file_path: str) -> Tuple[str, str]:
    """Parse artist and title from filename using common patterns (backward compatibility function)"""
    mp3_file = MP3File(file_path)
    return mp3_file.parsed_filename 