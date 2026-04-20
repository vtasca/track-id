import pytest
from unittest.mock import Mock, patch, MagicMock
from track_id.discogs_api import DiscogsDataSource

SAMPLE_SEARCH_RESULTS = {
    "results": [
        {
            "id": 86771,
            "master_id": 45058,
            "title": "DJ Krush & Toshinori Kondo - Ki-Oku",
            "year": 2000,
            "format": ["CD", "Album"],
            "label": ["Instinct Records"],
            "uri": "/release/86771-DJ-Krush-Toshinori-Kondo-Ki-Oku",
            "resource_url": "https://api.discogs.com/releases/86771",
            "master_url": "https://api.discogs.com/masters/45058",
        }
    ]
}

SAMPLE_MASTER = {
    "id": 45058,
    "title": "Ki-Oku",
    "year": 1996,
    "artists": [
        {"name": "DJ Krush", "join": "&"},
        {"name": "Toshinori Kondo"},
    ],
    "genres": ["Electronic"],
    "styles": ["Trip Hop", "Future Jazz", "Downtempo"],
    "images": [{"type": "primary", "uri": "https://img.discogs.com/cover.jpg"}],
    "tracklist": [
        {"type_": "track", "position": "1", "title": "Toh-Sui", "duration": "4:57"},
        {"type_": "track", "position": "2", "title": "Tobira-1", "duration": "0:35"},
        {"type_": "track", "position": "3", "title": "Mu-Getsu", "duration": "6:19"},
        {"type_": "track", "position": "4", "title": "Ha-Doh", "duration": "5:24"},
        {"type_": "track", "position": "5", "title": "Sun Is Shining", "duration": "6:52"},
    ],
}


@pytest.fixture
def source():
    return DiscogsDataSource()


class TestDiscogsSearch:
    @patch("track_id.discogs_api.time.sleep")
    def test_search_uses_freetext_query(self, mock_sleep, source):
        with patch.object(source._session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = SAMPLE_SEARCH_RESULTS
            mock_get.return_value = mock_response

            result = source.search("DJ Krush - Ha Doh")

        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
        assert params["q"] == "DJ Krush Ha Doh"
        assert params["type"] == "release"

    @patch("track_id.discogs_api.time.sleep")
    def test_search_handles_multilingual_title(self, mock_sleep, source):
        """Titles with embedded ' - ' (multilingual) must not break the query."""
        with patch.object(source._session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = SAMPLE_SEARCH_RESULTS
            mock_get.return_value = mock_response

            source.search("DJ Krush - 黒い雨 Kuroi Ame - Black Rain")

        params = mock_get.call_args[1]["params"]
        assert params["q"] == "DJ Krush 黒い雨 Kuroi Ame Black Rain"

    @patch("track_id.discogs_api.time.sleep")
    def test_search_api_error_raises(self, mock_sleep, source):
        with patch.object(source._session, "get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.text = "Rate limit exceeded"
            mock_get.return_value = mock_response

            with pytest.raises(Exception, match="Discogs API error: 429"):
                source.search("DJ Krush - Ha Doh")


class TestFindMatchingTrack:
    def test_prefers_result_with_master_id(self, source):
        results = {
            "results": [
                {"id": 1, "title": "No Master"},
                {"id": 2, "master_id": 99, "title": "Has Master"},
                {"id": 3, "master_id": 100, "title": "Also Has Master"},
            ]
        }
        match = source.find_matching_track(results, "Artist", "Title")
        assert match["id"] == 2

    def test_falls_back_to_first_when_no_master(self, source):
        results = {
            "results": [
                {"id": 10, "title": "First Result"},
                {"id": 11, "title": "Second Result"},
            ]
        }
        match = source.find_matching_track(results, "Artist", "Title")
        assert match["id"] == 10

    def test_annotates_search_context(self, source):
        results = {"results": [{"id": 1, "master_id": 5, "title": "X"}]}
        match = source.find_matching_track(results, "DJ Krush", "Ha Doh")
        assert match["_search_artist"] == "DJ Krush"
        assert match["_search_title"] == "Ha Doh"

    def test_returns_none_on_empty_results(self, source):
        assert source.find_matching_track({"results": []}, "A", "T") is None


class TestFindTrackInTracklist:
    def test_exact_match(self, source):
        tracklist = [{"type_": "track", "title": "Ha-Doh", "position": "4"}]
        result = source._find_track_in_tracklist(tracklist, "Ha-Doh")
        assert result["title"] == "Ha-Doh"

    def test_case_insensitive(self, source):
        tracklist = [{"type_": "track", "title": "Ha-Doh", "position": "4"}]
        result = source._find_track_in_tracklist(tracklist, "ha-doh")
        assert result is not None

    def test_hyphen_space_normalization(self, source):
        tracklist = [{"type_": "track", "title": "Ha-Doh", "position": "4"}]
        result = source._find_track_in_tracklist(tracklist, "ha doh")
        assert result is not None

    def test_multilingual_title_with_embedded_hyphens(self, source):
        # Tracklist: "黒い雨 - Kuroi Ame - Black Rain", search title: "黒い雨 Kuroi Ame - Black Rain"
        tracklist = [{"type_": "track", "title": "黒い雨 - Kuroi Ame - Black Rain", "position": "1"}]
        result = source._find_track_in_tracklist(tracklist, "黒い雨 Kuroi Ame - Black Rain")
        assert result is not None

    def test_skips_non_track_entries(self, source):
        tracklist = [
            {"type_": "heading", "title": "Side A"},
            {"type_": "track", "title": "Real Track", "position": "A1"},
        ]
        result = source._find_track_in_tracklist(tracklist, "Side A")
        assert result is None

    def test_returns_none_when_not_found(self, source):
        tracklist = [{"type_": "track", "title": "Other Song", "position": "1"}]
        assert source._find_track_in_tracklist(tracklist, "Ha Doh") is None


class TestGetDetailedTrackInfo:
    @patch("track_id.discogs_api.time.sleep")
    def test_fetches_master_when_master_id_present(self, mock_sleep, source):
        stub = {**SAMPLE_SEARCH_RESULTS["results"][0], "_search_title": "Ha Doh", "_search_artist": "DJ Krush"}
        with patch.object(source, "_fetch_master", return_value=SAMPLE_MASTER) as mock_master:
            detail = source._get_detailed_track_info(stub)

        mock_master.assert_called_once_with(45058)
        assert detail["_source"] == "master"

    @patch("track_id.discogs_api.time.sleep")
    def test_falls_back_to_release_when_no_master_id(self, mock_sleep, source):
        stub = {"id": 86771, "_search_title": "Ha Doh", "_search_artist": "DJ Krush"}
        sample_release = {**SAMPLE_MASTER, "labels": [{"name": "Instinct Records"}]}
        with patch.object(source, "_fetch_release", return_value=sample_release) as mock_release:
            detail = source._get_detailed_track_info(stub)

        mock_release.assert_called_once_with(86771)
        assert detail["_source"] == "release"

    @patch("track_id.discogs_api.time.sleep")
    def test_injects_track_number_and_total(self, mock_sleep, source):
        stub = {**SAMPLE_SEARCH_RESULTS["results"][0], "_search_title": "Ha Doh", "_search_artist": "DJ Krush"}
        with patch.object(source, "_fetch_master", return_value=SAMPLE_MASTER):
            detail = source._get_detailed_track_info(stub)

        matched = detail["_matched_track"]
        assert matched is not None
        assert matched["title"] == "Ha-Doh"
        assert matched["_track_number"] == 4
        assert matched["_track_total"] == 5

    @patch("track_id.discogs_api.time.sleep")
    def test_matched_track_is_none_when_not_found(self, mock_sleep, source):
        stub = {**SAMPLE_SEARCH_RESULTS["results"][0], "_search_title": "Nonexistent", "_search_artist": "DJ Krush"}
        with patch.object(source, "_fetch_master", return_value=SAMPLE_MASTER):
            detail = source._get_detailed_track_info(stub)

        assert detail["_matched_track"] is None


class TestExtractMetadata:
    def _make_detail(self, matched_title="Ha-Doh", track_num=4, track_total=5):
        matched = {
            "type_": "track",
            "position": "4",
            "title": matched_title,
            "duration": "5:24",
            "_track_number": track_num,
            "_track_total": track_total,
        }
        return {
            **SAMPLE_MASTER,
            "_source": "master",
            "_release_stub": SAMPLE_SEARCH_RESULTS["results"][0],
            "_matched_track": matched,
        }

    def test_album_and_year(self, source):
        meta = source.extract_metadata(self._make_detail())
        assert meta["TALB"] == "Ki-Oku"
        assert meta["TDRC"] == "1996"

    def test_artist_fields(self, source):
        meta = source.extract_metadata(self._make_detail())
        assert meta["TPE1"] == "DJ Krush & Toshinori Kondo"
        assert meta["TPE2"] == "DJ Krush & Toshinori Kondo"

    def test_genre_and_styles(self, source):
        meta = source.extract_metadata(self._make_detail())
        assert meta["TCON"] == "Electronic"
        assert "Trip Hop" in meta["TXXX:STYLE"]
        assert "Future Jazz" in meta["TXXX:STYLE"]

    def test_label_from_stub(self, source):
        meta = source.extract_metadata(self._make_detail())
        assert meta["TPUB"] == "Instinct Records"

    def test_track_title_and_number(self, source):
        meta = source.extract_metadata(self._make_detail())
        assert meta["TIT2"] == "Ha-Doh"
        assert meta["TRCK"] == "4/5"

    def test_artwork_url(self, source):
        meta = source.extract_metadata(self._make_detail())
        assert meta["artwork_url"] == "https://img.discogs.com/cover.jpg"

    def test_discogs_url(self, source):
        meta = source.extract_metadata(self._make_detail())
        assert "discogs.com" in meta["TXXX:DISCOGS_URL"]

    def test_no_matched_track_skips_track_fields(self, source):
        detail = {
            **SAMPLE_MASTER,
            "_source": "master",
            "_release_stub": SAMPLE_SEARCH_RESULTS["results"][0],
            "_matched_track": None,
        }
        meta = source.extract_metadata(detail)
        assert "TIT2" not in meta
        assert "TRCK" not in meta
