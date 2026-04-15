"""Tests for data_sources.py core aggregation logic."""

import pytest
from unittest.mock import Mock, patch

from track_id.data_sources import (
    DataSourceRegistry,
    search_all_sources,
    enrich_with_all_sources,
    extract_artist_name_from_credits,
)


def _make_source(name, search_return=None, search_raises=None, enrich_return=None, enrich_raises=None):
    source = Mock()
    source.name = name
    if search_raises:
        source.search.side_effect = search_raises
    else:
        source.search.return_value = search_return if search_return is not None else {}
    if enrich_raises:
        source.enrich_mp3_file.side_effect = enrich_raises
    else:
        source.enrich_mp3_file.return_value = enrich_return if enrich_return is not None else {"file_path": "test.mp3"}
    return source


def _make_mp3(artist="Test Artist", title="Test Track", parsed=("", "")):
    mp3 = Mock()
    mp3.metadata = {}
    if artist:
        mp3.metadata["TPE1"] = artist
    if title:
        mp3.metadata["TIT2"] = title
    mp3.parsed_filename = parsed
    return mp3


class TestDataSourceRegistry:
    def test_starts_empty(self):
        registry = DataSourceRegistry()
        assert registry.get_all_sources() == []

    def test_register_and_retrieve(self):
        registry = DataSourceRegistry()
        source = Mock()
        source.name = "TestSource"
        registry.register(source)
        assert registry.get_all_sources() == [source]

    def test_register_multiple_sources(self):
        registry = DataSourceRegistry()
        source_a = Mock()
        source_a.name = "A"
        source_b = Mock()
        source_b.name = "B"
        registry.register(source_a)
        registry.register(source_b)
        assert registry.get_all_sources() == [source_a, source_b]

    def test_get_source_by_name_found(self):
        registry = DataSourceRegistry()
        source = Mock()
        source.name = "Bandcamp"
        registry.register(source)
        assert registry.get_source_by_name("Bandcamp") is source

    def test_get_source_by_name_not_found(self):
        registry = DataSourceRegistry()
        assert registry.get_source_by_name("NonExistent") is None

    def test_get_source_by_name_empty_registry(self):
        registry = DataSourceRegistry()
        assert registry.get_source_by_name("Bandcamp") is None

    def test_get_all_sources_returns_copy(self):
        """Mutating the returned list must not affect registry state."""
        registry = DataSourceRegistry()
        registry.get_all_sources().append(Mock())
        assert registry.get_all_sources() == []


class TestSearchAllSources:
    @patch("track_id.data_sources.data_source_registry")
    def test_all_sources_succeed(self, mock_registry):
        bc_data = {"auto": {"results": [1, 2]}}
        mb_data = {"recordings": [3]}
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", search_return=bc_data),
            _make_source("MusicBrainz", search_return=mb_data),
        ]

        results = search_all_sources("Artist - Title")

        assert results["Bandcamp"]["success"] is True
        assert results["Bandcamp"]["data"] == bc_data
        assert results["MusicBrainz"]["success"] is True
        assert results["MusicBrainz"]["data"] == mb_data

    @patch("track_id.data_sources.data_source_registry")
    def test_first_source_fails_second_succeeds(self, mock_registry):
        mb_data = {"recordings": []}
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", search_raises=ConnectionError("timeout")),
            _make_source("MusicBrainz", search_return=mb_data),
        ]

        results = search_all_sources("Artist - Title")

        assert results["Bandcamp"]["success"] is False
        assert "timeout" in results["Bandcamp"]["error"]
        assert results["MusicBrainz"]["success"] is True
        assert results["MusicBrainz"]["data"] == mb_data

    @patch("track_id.data_sources.data_source_registry")
    def test_first_source_succeeds_second_fails(self, mock_registry):
        bc_data = {"auto": {"results": []}}
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", search_return=bc_data),
            _make_source("MusicBrainz", search_raises=Exception("api down")),
        ]

        results = search_all_sources("Artist - Title")

        assert results["Bandcamp"]["success"] is True
        assert results["MusicBrainz"]["success"] is False
        assert "api down" in results["MusicBrainz"]["error"]

    @patch("track_id.data_sources.data_source_registry")
    def test_all_sources_fail(self, mock_registry):
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", search_raises=Exception("bc down")),
            _make_source("MusicBrainz", search_raises=Exception("mb down")),
        ]

        results = search_all_sources("Artist - Title")

        assert results["Bandcamp"]["success"] is False
        assert results["MusicBrainz"]["success"] is False

    @patch("track_id.data_sources.data_source_registry")
    def test_no_sources_registered(self, mock_registry):
        mock_registry.get_all_sources.return_value = []

        results = search_all_sources("Artist - Title")

        assert results == {}

    @patch("track_id.data_sources.data_source_registry")
    def test_query_passed_through_unchanged(self, mock_registry):
        source = _make_source("Bandcamp")
        mock_registry.get_all_sources.return_value = [source]

        search_all_sources("Daft Punk - Harder Better Faster Stronger")

        source.search.assert_called_once_with("Daft Punk - Harder Better Faster Stronger")

    @patch("track_id.data_sources.data_source_registry")
    def test_result_includes_source_reference(self, mock_registry):
        source = _make_source("Bandcamp", search_return={})
        mock_registry.get_all_sources.return_value = [source]

        results = search_all_sources("query")

        assert results["Bandcamp"]["source"] is source


class TestEnrichWithAllSources:
    @patch("track_id.data_sources.MP3File")
    @patch("track_id.data_sources.data_source_registry")
    def test_all_sources_succeed(self, mock_registry, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        bc_result = {"file_path": "test.mp3", "added": "bc"}
        mb_result = {"file_path": "test.mp3", "added": "mb"}
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", enrich_return=bc_result),
            _make_source("MusicBrainz", enrich_return=mb_result),
        ]

        result = enrich_with_all_sources("test.mp3")

        assert result["all_results"]["Bandcamp"]["success"] is True
        assert result["all_results"]["MusicBrainz"]["success"] is True

    @patch("track_id.data_sources.MP3File")
    @patch("track_id.data_sources.data_source_registry")
    def test_first_source_result_is_successful_enrichment(self, mock_registry, mock_mp3_class):
        """successful_enrichment should be set to the first source that succeeds."""
        mock_mp3_class.return_value = _make_mp3()
        bc_result = {"file_path": "test.mp3", "added": "bc"}
        mb_result = {"file_path": "test.mp3", "added": "mb"}
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", enrich_return=bc_result),
            _make_source("MusicBrainz", enrich_return=mb_result),
        ]

        result = enrich_with_all_sources("test.mp3")

        assert result["successful_enrichment"] == bc_result

    @patch("track_id.data_sources.MP3File")
    @patch("track_id.data_sources.data_source_registry")
    def test_first_fails_second_succeeds(self, mock_registry, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        mb_result = {"file_path": "test.mp3", "added": "mb"}
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", enrich_raises=Exception("not found on bc")),
            _make_source("MusicBrainz", enrich_return=mb_result),
        ]

        result = enrich_with_all_sources("test.mp3")

        assert result["all_results"]["Bandcamp"]["success"] is False
        assert "not found on bc" in result["all_results"]["Bandcamp"]["error"]
        assert result["all_results"]["MusicBrainz"]["success"] is True
        assert result["successful_enrichment"] == mb_result

    @patch("track_id.data_sources.MP3File")
    @patch("track_id.data_sources.data_source_registry")
    def test_first_succeeds_second_fails(self, mock_registry, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        bc_result = {"file_path": "test.mp3", "added": "bc"}
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", enrich_return=bc_result),
            _make_source("MusicBrainz", enrich_raises=Exception("mb api down")),
        ]

        result = enrich_with_all_sources("test.mp3")

        assert result["all_results"]["Bandcamp"]["success"] is True
        assert result["all_results"]["MusicBrainz"]["success"] is False
        assert result["successful_enrichment"] == bc_result

    @patch("track_id.data_sources.MP3File")
    @patch("track_id.data_sources.data_source_registry")
    def test_all_sources_fail_raises_value_error(self, mock_registry, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", enrich_raises=Exception("bc down")),
            _make_source("MusicBrainz", enrich_raises=Exception("mb down")),
        ]

        with pytest.raises(ValueError, match="No data source could enrich"):
            enrich_with_all_sources("test.mp3")

    @patch("track_id.data_sources.MP3File")
    @patch("track_id.data_sources.data_source_registry")
    def test_no_metadata_and_no_filename_raises(self, mock_registry, mock_mp3_class):
        mp3 = _make_mp3(artist="", title="", parsed=("", ""))
        mock_mp3_class.return_value = mp3
        mock_registry.get_all_sources.return_value = []

        with pytest.raises(ValueError, match="missing artist and title metadata"):
            enrich_with_all_sources("test.mp3")

    @patch("track_id.data_sources.MP3File")
    @patch("track_id.data_sources.data_source_registry")
    def test_falls_back_to_filename_when_no_id3_tags(self, mock_registry, mock_mp3_class):
        mp3 = _make_mp3(artist="", title="", parsed=("Parsed Artist", "Parsed Title"))
        mock_mp3_class.return_value = mp3
        source = _make_source("Bandcamp", enrich_return={"file_path": "test.mp3"})
        mock_registry.get_all_sources.return_value = [source]

        result = enrich_with_all_sources("test.mp3")

        assert result["search_query"] == "Parsed Artist - Parsed Title"

    @patch("track_id.data_sources.MP3File")
    @patch("track_id.data_sources.data_source_registry")
    def test_search_query_built_from_id3_tags(self, mock_registry, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3(artist="Burial", title="Archangel")
        source = _make_source("Bandcamp", enrich_return={"file_path": "test.mp3"})
        mock_registry.get_all_sources.return_value = [source]

        result = enrich_with_all_sources("test.mp3")

        assert result["search_query"] == "Burial - Archangel"

    @patch("track_id.data_sources.MP3File")
    @patch("track_id.data_sources.data_source_registry")
    def test_file_path_in_result(self, mock_registry, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        mock_registry.get_all_sources.return_value = [
            _make_source("Bandcamp", enrich_return={"file_path": "my_track.mp3"}),
        ]

        result = enrich_with_all_sources("my_track.mp3")

        assert result["file_path"] == "my_track.mp3"


class TestExtractArtistNameFromCredits:
    def test_empty_list(self):
        assert extract_artist_name_from_credits([]) == ""

    def test_single_dict_credit(self):
        assert extract_artist_name_from_credits([{"name": "Burial"}]) == "Burial"

    def test_multiple_dict_credits(self):
        credits = [{"name": "Artist A"}, {"name": "Artist B"}]
        assert extract_artist_name_from_credits(credits) == "Artist A Artist B"

    def test_string_credits(self):
        credits = ["Artist A", "Artist B"]
        assert extract_artist_name_from_credits(credits) == "Artist A Artist B"

    def test_mixed_dict_and_string_credits(self):
        credits = [{"name": "Artist A"}, "Artist B"]
        assert extract_artist_name_from_credits(credits) == "Artist A Artist B"

    def test_dict_without_name_key_is_skipped(self):
        credits = [{"id": "123"}, {"name": "Artist B"}]
        assert extract_artist_name_from_credits(credits) == "Artist B"

    def test_all_dicts_without_name_key(self):
        credits = [{"id": "123"}, {"url": "http://example.com"}]
        assert extract_artist_name_from_credits(credits) == ""
