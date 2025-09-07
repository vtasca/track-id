import pytest
import os
import tempfile
from unittest.mock import Mock, patch, mock_open
from typer.testing import CliRunner
from track_id import app


class TestTrackIdCLI:
    """Test cases for the track-id CLI application"""
    
    @pytest.fixture
    def runner(self):
        """Create a CLI runner for testing"""
        return CliRunner()
    
    def test_search_command_exists(self, runner):
        """Test that the search command exists"""
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output.lower()
    
    def test_info_command_exists(self, runner):
        """Test that the info command exists"""
        result = runner.invoke(app, ["info", "--help"])
        assert result.exit_code == 0
        assert "info" in result.output.lower()
    
    def test_enrich_command_exists(self, runner):
        """Test that the enrich command exists"""
        result = runner.invoke(app, ["enrich", "--help"])
        assert result.exit_code == 0
        assert "enrich" in result.output.lower()
    
    @patch('track_id.track_id.search_bandcamp')
    def test_search_command_success(self, mock_search, runner):
        """Test search command with successful API response"""
        # Mock successful API response
        mock_search.return_value = {
            "results": [
                {"title": "Test Track", "artist": "Test Artist"}
            ]
        }
        
        result = runner.invoke(app, ["search", "test track"])
        
        assert result.exit_code == 0
        mock_search.assert_called_once_with("test track")
    
    @patch('track_id.track_id.search_bandcamp')
    def test_search_command_error(self, mock_search, runner):
        """Test search command with API error"""
        # Mock failed API response
        mock_search.side_effect = Exception("API Error")
        
        result = runner.invoke(app, ["search", "test track"])
        
        assert result.exit_code == 1
        assert "Error:" in result.output
    
    def test_info_command_file_not_exists(self, runner):
        """Test info command with non-existent file"""
        result = runner.invoke(app, ["info", "nonexistent.mp3"])
        
        assert result.exit_code == 1
        assert "does not exist" in result.output
    
    def test_info_command_not_mp3(self, runner):
        """Test info command with non-MP3 file"""
        # Create a temporary text file
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b"test content")
            temp_file = f.name
        
        try:
            result = runner.invoke(app, ["info", temp_file])
            assert result.exit_code == 1
            assert "not an MP3" in result.output
        finally:
            os.unlink(temp_file)
    
    @patch('track_id.track_id.MP3File')
    def test_info_command_success(self, mock_mp3_file_class, runner):
        """Test info command with valid MP3 file"""
        # Mock MP3File instance
        mock_mp3_file = Mock()
        mock_mp3_file.info = {
            'file_path': 'test.mp3',
            'file_size': 1024000,
            'duration_seconds': 180.5,
            'bitrate': 320000,
            'sample_rate': 44100
        }
        mock_mp3_file.metadata = {
            'TIT2': 'Test Title',
            'TPE1': 'Test Artist',
            'TALB': 'Test Album'
        }
        mock_mp3_file_class.return_value = mock_mp3_file
        
        result = runner.invoke(app, ["info", "test.mp3"])
        
        assert result.exit_code == 0
        assert "3:00" in result.output  # Duration
        assert "320 kbps" in result.output  # Bitrate
        assert "44100 Hz" in result.output  # Sample rate
        assert "Test Title" in result.output
        assert "Test Artist" in result.output
    
    @patch('track_id.track_id.MP3File')
    def test_info_command_no_id3_tags(self, mock_mp3_file_class, runner):
        """Test info command with MP3 file that has no ID3 tags"""
        # Mock MP3File instance
        mock_mp3_file = Mock()
        mock_mp3_file.info = {
            'file_path': 'test.mp3',
            'file_size': 512000,
            'duration_seconds': 120.0,
            'bitrate': 256000,
            'sample_rate': 44100
        }
        mock_mp3_file.metadata = {}
        mock_mp3_file_class.return_value = mock_mp3_file
        
        result = runner.invoke(app, ["info", "test.mp3"])
        
        assert result.exit_code == 0
        assert "No metadata tags found" in result.output
    
    @patch('track_id.track_id.enrich_mp3_file')
    def test_enrich_command_success(self, mock_enrich, runner):
        """Test enrich command with successful enrichment"""
        # Mock successful enrichment result
        mock_enrich.return_value = {
            'file_path': 'test.mp3',
            'search_query': 'Test Artist Test Title',
            'bandcamp_track': {
                'band_name': 'Test Artist',
                'name': 'Test Title',
                'album_name': 'Test Album',
                'art_id': '1234567890'
            },
            'existing_metadata': {
                'TIT2': 'Test Title',
                'TPE1': 'Test Artist'
            },
            'bandcamp_metadata': {
                'TIT2': 'Test Title',
                'TPE1': 'Test Artist',
                'TALB': 'Test Album',
                'artwork_url': 'https://f4.bcbits.com/img/a1234567890_16.jpg'
            },
            'added_metadata': {
                'TALB': 'Test Album',
                'artwork': 'Added album artwork (image/jpeg)'
            }
        }
        
        result = runner.invoke(app, ["enrich", "test.mp3"])
        
        assert result.exit_code == 0
        assert "Successfully enriched" in result.output
        assert "Test Artist - Test Title" in result.output
        assert "New Metadata Added" in result.output
        assert "Test Album" in result.output
        assert "Added album artwork" in result.output
    
    @patch('track_id.track_id.enrich_mp3_file')
    def test_enrich_command_error(self, mock_enrich, runner):
        """Test enrich command with error"""
        # Mock error
        mock_enrich.side_effect = ValueError("Cannot enrich file: missing artist (TPE1) or title (TIT2) metadata")
        
        result = runner.invoke(app, ["enrich", "test.mp3"])
        
        assert result.exit_code == 1
        assert "Error enriching MP3 file" in result.output
        assert "missing artist" in result.output
        
    @patch('track_id.track_id.enrich_mp3_file')
    def test_enrich_command_with_artwork(self, mock_enrich, runner):
        """Test enrich command with artwork functionality"""
        # Mock successful enrichment result with artwork
        mock_enrich.return_value = {
            'file_path': 'test.mp3',
            'search_query': 'Test Artist Test Title',
            'bandcamp_track': {
                'band_name': 'Test Artist',
                'name': 'Test Title',
                'album_name': 'Test Album',
                'art_id': '1234567890'
            },
            'existing_metadata': {
                'TIT2': 'Test Title',
                'TPE1': 'Test Artist',
                'TALB': 'Test Album'  # Already has album
            },
            'bandcamp_metadata': {
                'TIT2': 'Test Title',
                'TPE1': 'Test Artist',
                'TALB': 'Test Album',
                'artwork_url': 'https://f4.bcbits.com/img/a1234567890_16.jpg'
            },
            'added_metadata': {
                'artwork': 'Added album artwork (image/jpeg)'
            }
        }
        
        result = runner.invoke(app, ["enrich", "test.mp3"])
        
        assert result.exit_code == 0
        assert "Successfully enriched" in result.output
        assert "Added album artwork" in result.output
        assert "image/jpeg" in result.output
        