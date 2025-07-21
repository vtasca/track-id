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
    
    @patch('track_id.track_id.requests.post')
    def test_search_command_success(self, mock_post, runner):
        """Test search command with successful API response"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"title": "Test Track", "artist": "Test Artist"}
            ]
        }
        mock_post.return_value = mock_response
        
        result = runner.invoke(app, ["search", "test track"])
        
        assert result.exit_code == 0
        mock_post.assert_called_once()
        # Verify the search text was passed correctly
        call_args = mock_post.call_args
        assert call_args[1]['json']['search_text'] == "test track"
    
    @patch('track_id.track_id.requests.post')
    def test_search_command_error(self, mock_post, runner):
        """Test search command with API error"""
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_post.return_value = mock_response
        
        result = runner.invoke(app, ["search", "test track"])
        
        assert result.exit_code == 0  # CLI doesn't exit on API errors
        assert "Error: 404" in result.output
    
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
            assert "not an MP3 file" in result.output
        finally:
            os.unlink(temp_file)
    
    @patch('track_id.track_id.MP3')
    @patch('track_id.track_id.ID3')
    def test_info_command_success(self, mock_id3, mock_mp3, runner):
        """Test info command with valid MP3 file"""
        # Mock MP3 file info
        mock_audio = Mock()
        mock_audio.info.length = 180.5  # 3 minutes 0.5 seconds
        mock_audio.info.bitrate = 320000
        mock_audio.info.sample_rate = 44100
        mock_mp3.return_value = mock_audio
        
        # Mock ID3 tags
        mock_id3_instance = Mock()
        mock_id3_instance.items.return_value = [
            ('TIT2', Mock(text=['Test Title'])),
            ('TPE1', Mock(text=['Test Artist'])),
            ('TALB', Mock(text=['Test Album']))
        ]
        mock_id3.return_value = mock_id3_instance
        
        # Mock file size
        with patch('track_id.track_id.os.path.getsize', return_value=1024000):
            with patch('track_id.track_id.os.path.exists', return_value=True):
                result = runner.invoke(app, ["info", "test.mp3"])
        
        assert result.exit_code == 0
        assert "test.mp3" in result.output
        assert "3:00" in result.output  # Duration
        assert "320 kbps" in result.output  # Bitrate
        assert "44100 Hz" in result.output  # Sample rate
        assert "Test Title" in result.output
        assert "Test Artist" in result.output
    
    @patch('track_id.track_id.MP3')
    def test_info_command_no_id3_tags(self, mock_mp3, runner):
        """Test info command with MP3 file that has no ID3 tags"""
        # Mock MP3 file info
        mock_audio = Mock()
        mock_audio.info.length = 120.0
        mock_audio.info.bitrate = 256000
        mock_audio.info.sample_rate = 44100
        mock_mp3.return_value = mock_audio
        
        # Mock ID3 to raise exception (no tags)
        with patch('track_id.track_id.ID3', side_effect=Exception("No ID3 tags")):
            with patch('track_id.track_id.os.path.getsize', return_value=512000):
                with patch('track_id.track_id.os.path.exists', return_value=True):
                    result = runner.invoke(app, ["info", "test.mp3"])
        
        assert result.exit_code == 0
        assert "No metadata tags found" in result.output
        