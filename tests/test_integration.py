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
        with patch('track_id.track_id.search_bandcamp') as mock_search:
            # Mock successful API response
            mock_search.return_value = {
                "results": [
                    {
                        "title": "Midnight In Peckham",
                        "artist": "Chaos In The CBD",
                        "album": "Midnight In Peckham"
                    }
                ]
            }
            
            result = runner.invoke(app, ["search", "Chaos In The CBD"])
            
            assert result.exit_code == 0
            assert "Midnight In Peckham" in result.output
            assert "Chaos In The CBD" in result.output
    
    def test_full_info_workflow(self, runner):
        """Test the complete info workflow with a real-like MP3 file"""
        with patch('track_id.track_id.get_mp3_info') as mock_info, \
             patch('track_id.track_id.get_mp3_metadata') as mock_metadata:
            
            # Mock MP3 file info
            mock_info.return_value = {
                'file_path': 'Chaos In The CBD - Midnight In Peckham - 04 Midnight In Peckham.mp3',
                'file_size': 2048000,
                'duration_seconds': 245.3,
                'bitrate': 320000,
                'sample_rate': 44100
            }
            
            # Mock ID3 tags
            mock_metadata.return_value = {
                'TIT2': 'Midnight In Peckham',
                'TPE1': 'Chaos In The CBD',
                'TALB': 'Midnight In Peckham',
                'TRCK': '4',
                'TDRC': '2023'
            }
            
            result = runner.invoke(app, ["info", "Chaos In The CBD - Midnight In Peckham - 04 Midnight In Peckham.mp3"])
            
            assert result.exit_code == 0
            assert "Chaos In The CBD" in result.output
            assert "Midnight In Peckham" in result.output
            assert "4:05" in result.output  # Duration
            assert "320 kbps" in result.output  # Bitrate
            assert "44100 Hz" in result.output  # Sample rate
            assert "1.95 MB" in result.output  # File size
    
    def test_error_handling_workflow(self, runner):
        """Test error handling in the complete workflow"""
        # Test with invalid search
        with patch('track_id.track_id.search_bandcamp') as mock_search:
            mock_search.side_effect = Exception("Internal Server Error")
            
            result = runner.invoke(app, ["search", "invalid search"])
            
            assert result.exit_code == 1
            assert "Error:" in result.output
        
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
        assert "enrich" in result.output
        
        # Test search help
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "search" in result.output
        
        # Test info help
        result = runner.invoke(app, ["info", "--help"])
        assert result.exit_code == 0
        assert "info" in result.output
        
        # Test enrich help
        result = runner.invoke(app, ["enrich", "--help"])
        assert result.exit_code == 0
        assert "enrich" in result.output 