import pytest
from unittest.mock import Mock, patch
from track_id.bandcamp_api import (
    download_artwork, 
    get_mime_type, 
    extract_bandcamp_metadata,
    update_mp3_metadata
)


class TestArtworkFunctionality:
    """Test cases for artwork functionality"""
    
    @patch('track_id.bandcamp_api.requests.get')
    def test_download_artwork_success(self, mock_get):
        """Test successful artwork download"""
        # Mock successful response
        mock_response = Mock()
        mock_response.content = b'fake_image_data'
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = download_artwork('https://example.com/artwork.jpg')
        
        assert result == b'fake_image_data'
        mock_get.assert_called_once()
    
    @patch('track_id.bandcamp_api.requests.get')
    def test_download_artwork_failure(self, mock_get):
        """Test artwork download failure"""
        # Mock failed response
        mock_get.side_effect = Exception("Network error")
        
        result = download_artwork('https://example.com/artwork.jpg')
        
        assert result is None
    
    def test_get_mime_type_from_url(self):
        """Test MIME type detection from URL"""
        assert get_mime_type('https://example.com/artwork.jpg', b'') == 'image/jpeg'
        assert get_mime_type('https://example.com/artwork.png', b'') == 'image/png'
        assert get_mime_type('https://example.com/artwork.gif', b'') == 'image/gif'
        assert get_mime_type('https://example.com/artwork.webp', b'') == 'image/webp'
    
    def test_get_mime_type_from_content(self):
        """Test MIME type detection from content"""
        # JPEG magic bytes
        jpeg_data = b'\xff\xd8\xff\xe0\x00\x10JFIF'
        assert get_mime_type('https://example.com/artwork', jpeg_data) == 'image/jpeg'
        
        # PNG magic bytes
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
        assert get_mime_type('https://example.com/artwork', png_data) == 'image/png'
        
        # GIF magic bytes
        gif_data = b'GIF87a\x00\x00\x00\x00'
        assert get_mime_type('https://example.com/artwork', gif_data) == 'image/gif'
        
        # WebP magic bytes
        webp_data = b'RIFF\x00\x00\x00\x00WEBP'
        assert get_mime_type('https://example.com/artwork', webp_data) == 'image/webp'
    
    def test_extract_bandcamp_metadata_with_artwork(self):
        """Test metadata extraction with artwork URL"""
        track_data = {
            'name': 'Test Track',
            'band_name': 'Test Artist',
            'album_name': 'Test Album',
            'art_id': '1234567890'
        }
        
        result = extract_bandcamp_metadata(track_data)
        
        assert result['TIT2'] == 'Test Track'
        assert result['TPE1'] == 'Test Artist'
        assert result['TALB'] == 'Test Album'
        assert result['artwork_url'] == 'https://f4.bcbits.com/img/a1234567890_16.jpg'
    
    def test_extract_bandcamp_metadata_without_artwork(self):
        """Test metadata extraction without artwork URL"""
        track_data = {
            'name': 'Test Track',
            'band_name': 'Test Artist',
            'album_name': 'Test Album'
        }
        
        result = extract_bandcamp_metadata(track_data)
        
        assert result['TIT2'] == 'Test Track'
        assert result['TPE1'] == 'Test Artist'
        assert result['TALB'] == 'Test Album'
        assert 'artwork_url' not in result 