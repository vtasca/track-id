import pytest
import os
import tempfile
from unittest.mock import Mock, patch, mock_open
from typer.testing import CliRunner
from track_id import app
from track_id.musicbrainz_api import MusicBrainzDataSource


class TestMusicBrainzAPI:
    """Test cases for the MusicBrainz API functionality"""
    
    @pytest.fixture
    def runner(self):
        """Create a CLI runner for testing"""
        return CliRunner()
    
    
    @patch('track_id.musicbrainz_api.requests.get')
    def test_search_musicbrainz_success(self, mock_get):
        """Test successful MusicBrainz search"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "recordings": [
                {
                    "id": "test-id-1",
                    "title": "Test Track",
                    "artist-credit": [{"name": "Test Artist"}]
                }
            ]
        }
        mock_get.return_value = mock_response
        
        source = MusicBrainzDataSource()
        result = source.search("test track")
        
        assert result["recordings"][0]["title"] == "Test Track"
        assert result["recordings"][0]["artist-credit"][0]["name"] == "Test Artist"
        mock_get.assert_called_once()
    
    @patch('track_id.musicbrainz_api.requests.get')
    def test_search_musicbrainz_error(self, mock_get):
        """Test MusicBrainz search with API error"""
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_get.return_value = mock_response
        
        source = MusicBrainzDataSource()
        with pytest.raises(Exception) as exc_info:
            source.search("test track")
        
        assert "MusicBrainz API error: 404" in str(exc_info.value)
    
    @patch('track_id.musicbrainz_api.requests.get')
    def test_lookup_recording_success(self, mock_get):
        """Test successful recording lookup"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "test-id-1",
            "title": "Test Track",
            "artist-credit": [{"name": "Test Artist"}],
            "releases": [{"title": "Test Album", "date": "2020-01-01"}],
            "tags": [{"name": "rock", "count": 10}]
        }
        mock_get.return_value = mock_response
        
        source = MusicBrainzDataSource()
        result = source.lookup_recording("test-id-1")
        
        assert result["title"] == "Test Track"
        assert result["releases"][0]["title"] == "Test Album"
        mock_get.assert_called_once()
    
    def test_find_matching_track_success(self):
        """Test finding matching track in search results"""
        search_results = {
            "recordings": [
                {
                    "id": "test-id-1",
                    "title": "Test Track",
                    "artist-credit": [{"name": "Test Artist"}]
                },
                {
                    "id": "test-id-2", 
                    "title": "Another Track",
                    "artist-credit": [{"name": "Another Artist"}]
                }
            ]
        }
        
        source = MusicBrainzDataSource()
        result = source.find_matching_track(search_results, "Test Artist", "Test Track")
        
        assert result is not None
        assert result["id"] == "test-id-1"
        assert result["title"] == "Test Track"
    
    def test_find_matching_track_no_match(self):
        """Test finding matching track with no match"""
        search_results = {
            "recordings": [
                {
                    "id": "test-id-1",
                    "title": "Different Track",
                    "artist-credit": [{"name": "Different Artist"}]
                }
            ]
        }
        
        source = MusicBrainzDataSource()
        result = source.find_matching_track(search_results, "Test Artist", "Test Track")
        
        assert result is None
    
    def test_extract_musicbrainz_metadata(self):
        """Test extracting metadata from MusicBrainz recording data"""
        recording_data = {
            "title": "Test Track",
            "artist-credit": [{"name": "Test Artist"}],
            "releases": [
                {
                    "title": "Test Album",
                    "date": "2020-01-01"
                }
            ],
            "tags": [
                {"name": "rock", "count": 10},
                {"name": "alternative", "count": 5}
            ]
        }
        
        source = MusicBrainzDataSource()
        metadata = source.extract_metadata(recording_data)
        
        assert metadata["TIT2"] == "Test Track"
        assert metadata["TPE1"] == "Test Artist"
        assert metadata["TALB"] == "Test Album"
        assert metadata["TDRC"] == "2020"
        assert metadata["TCOM"] == "Test Artist"
        assert "rock" in metadata["TXXX:GENRE"]
        assert "alternative" in metadata["TXXX:GENRE"]
    
    @patch('track_id.data_sources.MP3File')
    @patch('track_id.musicbrainz_api.MusicBrainzDataSource.search')
    @patch('track_id.musicbrainz_api.MusicBrainzDataSource.find_matching_track')
    @patch('track_id.musicbrainz_api.MusicBrainzDataSource.lookup_recording')
    @patch('track_id.musicbrainz_api.MusicBrainzDataSource.extract_metadata')
    def test_enrich_mp3_file_musicbrainz_success(
        self, mock_extract, mock_lookup,
        mock_find, mock_search, mock_mp3_file_class
    ):
        """Test successful MP3 enrichment with MusicBrainz"""
        # Mock MP3File instance
        mock_mp3_file = Mock()
        mock_mp3_file.metadata = {
            "TPE1": "Test Artist",
            "TIT2": "Test Track"
        }
        mock_mp3_file.parsed_filename = ("", "")  # No filename parsing needed
        mock_mp3_file.update_metadata.return_value = {
            "TALB": "Test Album",
            "TDRC": "2020"
        }
        mock_mp3_file_class.return_value = mock_mp3_file
        
        # Mock search results
        mock_search.return_value = {"recordings": [
            {
                "id": "test-id-1",
                "title": "Test Track",
                "artist-credit": [{"name": "Test Artist"}]
            }
        ]}
        
        # Mock matching track
        mock_find.return_value = {"id": "test-id-1", "title": "Test Track"}
        
        # Mock detailed recording
        mock_lookup.return_value = {
            "id": "test-id-1",
            "title": "Test Track",
            "artist-credit": [{"name": "Test Artist"}]
        }
        
        # Mock extracted metadata
        mock_extract.return_value = {
            "TIT2": "Test Track",
            "TPE1": "Test Artist",
            "TALB": "Test Album"
        }
        
        source = MusicBrainzDataSource()
        result = source.enrich_mp3_file("test.mp3")
        
        assert result["file_path"] == "test.mp3"
        assert result["musicbrainz_metadata"]["TALB"] == "Test Album"
        mock_search.assert_called_once()
        mock_find.assert_called_once()
        mock_lookup.assert_called_once()
        mock_extract.assert_called_once()
        mock_mp3_file.update_metadata.assert_called_once()
    
    @patch('track_id.data_sources.MP3File')
    def test_enrich_mp3_file_musicbrainz_no_metadata(self, mock_mp3_file_class):
        """Test enrichment with no existing metadata"""
        # Mock MP3File instance with no metadata
        mock_mp3_file = Mock()
        mock_mp3_file.metadata = {}
        mock_mp3_file.parsed_filename = ("", "")  # No filename parsing
        mock_mp3_file_class.return_value = mock_mp3_file
        
        source = MusicBrainzDataSource()
        with pytest.raises(ValueError) as exc_info:
            source.enrich_mp3_file("test.mp3")
        
        assert "missing artist and title metadata" in str(exc_info.value)
    
    @patch('track_id.data_sources.MP3File')
    def test_enrich_mp3_file_musicbrainz_no_match(self, mock_mp3_file_class):
        """Test enrichment with no matching track found"""
        # Mock MP3File instance
        mock_mp3_file = Mock()
        mock_mp3_file.metadata = {
            "TPE1": "Test Artist",
            "TIT2": "Test Track"
        }
        mock_mp3_file.parsed_filename = ("", "")  # No filename parsing needed
        mock_mp3_file_class.return_value = mock_mp3_file
        
        source = MusicBrainzDataSource()
        
        # Mock the search method to return empty results
        with patch.object(source, 'search', return_value={"recordings": []}):
            with patch.object(source, 'find_matching_track', return_value=None):
                with pytest.raises(ValueError) as exc_info:
                    source.enrich_mp3_file("test.mp3")
                
                assert "No matching track found on MusicBrainz" in str(exc_info.value) 