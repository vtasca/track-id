import pytest
import os
import tempfile
from unittest.mock import patch, Mock
from typer.testing import CliRunner
from track_id import app


class TestIntegration:
    """Integration tests for the track-id application"""
    
    @pytest.fixture
    def runner(self):
        """Create a CLI runner for testing"""
        return CliRunner()
    
    def test_full_search_workflow(self, runner):
        """Test the complete search workflow"""
        with patch('track_id.track_id.requests.post') as mock_post:
            # Mock successful API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "results": [
                    {
                        "title": "Midnight In Peckham",
                        "artist": "Chaos In The CBD",
                        "album": "Midnight In Peckham"
                    }
                ]
            }
            mock_post.return_value = mock_response
            
            result = runner.invoke(app, ["search", "Chaos In The CBD"])
            
            assert result.exit_code == 0
            assert "Midnight In Peckham" in result.output
            assert "Chaos In The CBD" in result.output
    
    def test_full_info_workflow(self, runner):
        """Test the complete info workflow with a real-like MP3 file"""
        with patch('track_id.track_id.MP3') as mock_mp3, \
             patch('track_id.track_id.ID3') as mock_id3, \
             patch('track_id.track_id.os.path.getsize', return_value=2048000), \
             patch('track_id.track_id.os.path.exists', return_value=True):
            
            # Mock MP3 file info
            mock_audio = Mock()
            mock_audio.info.length = 245.3  # 4 minutes 5 seconds
            mock_audio.info.bitrate = 320000
            mock_audio.info.sample_rate = 44100
            mock_mp3.return_value = mock_audio
            
            # Mock ID3 tags
            mock_id3_instance = Mock()
            mock_id3_instance.items.return_value = [
                ('TIT2', Mock(text=['Midnight In Peckham'])),
                ('TPE1', Mock(text=['Chaos In The CBD'])),
                ('TALB', Mock(text=['Midnight In Peckham'])),
                ('TRCK', Mock(text=['4'])),
                ('TDRC', Mock(text=['2023']))
            ]
            mock_id3.return_value = mock_id3_instance
            
            result = runner.invoke(app, ["info", "Chaos In The CBD - Midnight In Peckham - 04 Midnight In Peckham.mp3"])
            
            assert result.exit_code == 0
            assert "Chaos In The CBD - Midnight In Peckham - 04 Midnight In Peckham.mp3" in result.output
            assert "4:05" in result.output  # Duration
            assert "320 kbps" in result.output  # Bitrate
            assert "44100 Hz" in result.output  # Sample rate
            assert "1.95 MB" in result.output  # File size
            assert "Midnight In Peckham" in result.output
            assert "Chaos In The CBD" in result.output
    
    def test_error_handling_workflow(self, runner):
        """Test error handling in the complete workflow"""
        # Test with invalid search
        with patch('track_id.track_id.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response
            
            result = runner.invoke(app, ["search", "invalid search"])
            
            assert result.exit_code == 0  # CLI doesn't exit on API errors
            assert "Error: 500" in result.output
        
        # Test with invalid file
        result = runner.invoke(app, ["info", "nonexistent.mp3"])
        assert result.exit_code == 1
        assert "does not exist" in result.output
    
    def test_cli_help_workflow(self, runner):
        """Test that help commands work correctly"""
        # Test main help
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "search" in result.output
        assert "info" in result.output
        
        # Test search help
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output
        
        # Test info help
        result = runner.invoke(app, ["info", "--help"])
        assert result.exit_code == 0
        assert "info" in result.output 