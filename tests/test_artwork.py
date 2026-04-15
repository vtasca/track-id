import pytest
from unittest.mock import Mock, patch
from track_id.mp3_utils import (
    download_artwork,
    get_mime_type,
    update_mp3_metadata,
    MAX_ARTWORK_SIZE,
)
from track_id.bandcamp_api import BandcampDataSource


def _make_streaming_response(chunks, content_length=None):
    """Build a mock streaming response that yields the given chunks."""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.headers = Mock()
    mock_response.headers.get.return_value = content_length
    mock_response.iter_content.return_value = iter(chunks)
    return mock_response


class TestArtworkFunctionality:
    """Test cases for artwork functionality"""

    @patch('track_id.mp3_utils.requests.get')
    def test_download_artwork_success(self, mock_get):
        """Test successful artwork download within size limit"""
        mock_get.return_value = _make_streaming_response([b'fake_', b'image_data'])

        result = download_artwork('https://example.com/artwork.jpg')

        assert result == b'fake_image_data'
        mock_get.assert_called_once()

    @patch('track_id.mp3_utils.requests.get')
    def test_download_artwork_uses_streaming(self, mock_get):
        """Test that download uses stream=True to avoid loading full response upfront"""
        mock_get.return_value = _make_streaming_response([b'data'])

        download_artwork('https://example.com/artwork.jpg')

        _, kwargs = mock_get.call_args
        assert kwargs.get('stream') is True

    @patch('track_id.mp3_utils.requests.get')
    def test_download_artwork_rejected_by_content_length_header(self, mock_get):
        """Test that an oversized Content-Length header causes early rejection"""
        oversized = str(MAX_ARTWORK_SIZE + 1)
        mock_get.return_value = _make_streaming_response([], content_length=oversized)

        result = download_artwork('https://example.com/artwork.jpg')

        assert result is None

    @patch('track_id.mp3_utils.requests.get')
    def test_download_artwork_rejected_mid_stream(self, mock_get):
        """Test that a response exceeding the limit mid-stream is rejected"""
        # No Content-Length header, but body is too large
        oversized_chunk = b'x' * (MAX_ARTWORK_SIZE + 1)
        mock_get.return_value = _make_streaming_response([oversized_chunk])

        result = download_artwork('https://example.com/artwork.jpg')

        assert result is None

    @patch('track_id.mp3_utils.requests.get')
    def test_download_artwork_accepted_at_exact_limit(self, mock_get):
        """Test that a response exactly at the limit is accepted"""
        exact_chunk = b'x' * MAX_ARTWORK_SIZE
        mock_get.return_value = _make_streaming_response([exact_chunk])

        result = download_artwork('https://example.com/artwork.jpg')

        assert result == exact_chunk

    @patch('track_id.mp3_utils.requests.get')
    def test_download_artwork_failure(self, mock_get):
        """Test artwork download failure"""
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
        
        source = BandcampDataSource()
        result = source.extract_metadata(track_data)
        
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
        
        source = BandcampDataSource()
        result = source.extract_metadata(track_data)
        
        assert result['TIT2'] == 'Test Track'
        assert result['TPE1'] == 'Test Artist'
        assert result['TALB'] == 'Test Album'
        assert 'artwork_url' not in result 