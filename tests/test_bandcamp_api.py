import pytest
import os
import tempfile
from unittest.mock import Mock, patch
from typer.testing import CliRunner
from track_id import app
from track_id.bandcamp_api import BandcampDataSource


class TestBandcampAPI:
    """Test cases for the Bandcamp API functionality"""
    
    @pytest.fixture
    def runner(self):
        """Create a CLI runner for testing"""
        return CliRunner()
    
    @patch('track_id.bandcamp_api.requests.post')
    def test_search_bandcamp_success(self, mock_post):
        """Test successful Bandcamp search"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "auto": {
                "results": [
                    {
                        "type": "t",
                        "name": "Test Track",
                        "band_name": "Test Artist",
                        "album_name": "Test Album",
                        "art_id": "1234567890"
                    }
                ]
            }
        }
        mock_post.return_value = mock_response
        
        source = BandcampDataSource()
        result = source.search("test track")
        
        assert result["auto"]["results"][0]["name"] == "Test Track"
        assert result["auto"]["results"][0]["band_name"] == "Test Artist"
        mock_post.assert_called_once()
    
    @patch('track_id.bandcamp_api.requests.post')
    def test_search_bandcamp_error(self, mock_post):
        """Test Bandcamp search with API error"""
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        source = BandcampDataSource()
        with pytest.raises(Exception) as exc_info:
            source.search("test track")
        
        assert "Bandcamp API error: 500" in str(exc_info.value)
    
    def test_find_matching_track_success(self):
        """Test finding matching track in search results"""
        search_results = {
            "auto": {
                "results": [
                    {
                        "type": "t",
                        "name": "Test Track",
                        "band_name": "Test Artist",
                        "album_name": "Test Album"
                    },
                    {
                        "type": "t",
                        "name": "Another Track",
                        "band_name": "Another Artist",
                        "album_name": "Another Album"
                    }
                ]
            }
        }
        
        source = BandcampDataSource()
        result = source.find_matching_track(search_results, "Test Artist", "Test Track")
        
        assert result is not None
        assert result["name"] == "Test Track"
        assert result["band_name"] == "Test Artist"
    
    def test_find_matching_track_no_match(self):
        """Test finding matching track with no match"""
        search_results = {
            "auto": {
                "results": [
                    {
                        "type": "t",
                        "name": "Different Track",
                        "band_name": "Different Artist",
                        "album_name": "Different Album"
                    }
                ]
            }
        }
        
        source = BandcampDataSource()
        result = source.find_matching_track(search_results, "Test Artist", "Test Track")
        
        assert result is None
    
    def test_extract_bandcamp_metadata(self):
        """Test extracting metadata from Bandcamp track data"""
        track_data = {
            "name": "Test Track",
            "band_name": "Test Artist",
            "album_name": "Test Album",
            "art_id": "1234567890"
        }
        
        source = BandcampDataSource()
        metadata = source.extract_metadata(track_data)
        
        assert metadata["TIT2"] == "Test Track"
        assert metadata["TPE1"] == "Test Artist"
        assert metadata["TALB"] == "Test Album"
        assert metadata["artwork_url"] == "https://f4.bcbits.com/img/a1234567890_16.jpg"
    
    def test_extract_bandcamp_metadata_without_artwork(self):
        """Test extracting metadata from Bandcamp track data without artwork"""
        track_data = {
            "name": "Test Track",
            "band_name": "Test Artist",
            "album_name": "Test Album"
        }
        
        source = BandcampDataSource()
        metadata = source.extract_metadata(track_data)
        
        assert metadata["TIT2"] == "Test Track"
        assert metadata["TPE1"] == "Test Artist"
        assert metadata["TALB"] == "Test Album"
        assert "artwork_url" not in metadata
    
    @patch('track_id.data_sources.MP3File')
    def test_enrich_mp3_file_bandcamp_success(self, mock_mp3_file_class):
        """Test successful MP3 enrichment with Bandcamp"""
        # Mock MP3File instance
        mock_mp3_file = Mock()
        mock_mp3_file.metadata = {
            "TPE1": "Test Artist",
            "TIT2": "Test Track"
        }
        mock_mp3_file.parsed_filename = ("", "")  # No filename parsing needed
        mock_mp3_file.update_metadata.return_value = {
            "TALB": "Test Album",
            "artwork": "Added album artwork (image/jpeg)"
        }
        mock_mp3_file_class.return_value = mock_mp3_file
        
        source = BandcampDataSource()
        
        # Mock the search method
        with patch.object(source, 'search', return_value={
            "auto": {
                "results": [
                    {
                        "type": "t",
                        "name": "Test Track",
                        "band_name": "Test Artist",
                        "album_name": "Test Album",
                        "art_id": "1234567890"
                    }
                ]
            }
        }):
            with patch.object(source, 'find_matching_track', return_value={
                "name": "Test Track",
                "band_name": "Test Artist",
                "album_name": "Test Album",
                "art_id": "1234567890"
            }):
                result = source.enrich_mp3_file("test.mp3")
                
                assert result["file_path"] == "test.mp3"
                assert result["bandcamp_metadata"]["TALB"] == "Test Album"
                assert result["added_metadata"]["TALB"] == "Test Album"
    
    @patch('track_id.data_sources.MP3File')
    def test_enrich_mp3_file_bandcamp_no_metadata(self, mock_mp3_file_class):
        """Test enrichment with no existing metadata"""
        # Mock MP3File instance with no metadata
        mock_mp3_file = Mock()
        mock_mp3_file.metadata = {}
        mock_mp3_file.parsed_filename = ("", "")  # No filename parsing
        mock_mp3_file_class.return_value = mock_mp3_file
        
        source = BandcampDataSource()
        with pytest.raises(ValueError) as exc_info:
            source.enrich_mp3_file("test.mp3")
        
        assert "missing artist and title metadata" in str(exc_info.value)
    
    @patch('track_id.data_sources.MP3File')
    def test_enrich_mp3_file_bandcamp_no_match(self, mock_mp3_file_class):
        """Test enrichment with no matching track found"""
        # Mock MP3File instance
        mock_mp3_file = Mock()
        mock_mp3_file.metadata = {
            "TPE1": "Test Artist",
            "TIT2": "Test Track"
        }
        mock_mp3_file.parsed_filename = ("", "")  # No filename parsing needed
        mock_mp3_file_class.return_value = mock_mp3_file
        
        source = BandcampDataSource()
        
        # Mock the search method to return empty results
        with patch.object(source, 'search', return_value={"auto": {"results": []}}):
            with patch.object(source, 'find_matching_track', return_value=None):
                with pytest.raises(ValueError) as exc_info:
                    source.enrich_mp3_file("test.mp3")
                
                assert "No matching track found on Bandcamp" in str(exc_info.value)
