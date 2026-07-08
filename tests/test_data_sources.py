"""Tests for data_sources.py core aggregation logic."""

from unittest.mock import Mock, patch

import pytest

from track_id.data_sources import (
    DataSource,
    DataSourceRegistry,
    enrich_with_all_sources,
    extract_artist_name_from_credits,
    find_best_match,
    match_score,
    normalize_for_match,
    search_all_sources,
)


def _make_source(name, search_return=None, search_raises=None,
                 fetch_return=None, fetch_raises=None, source_metadata=None):
    source = Mock()
    source.name = name
    if search_raises:
        source.search.side_effect = search_raises
    else:
        source.search.return_value = search_return if search_return is not None else {}
    if fetch_raises:
        source.fetch_metadata.side_effect = fetch_raises
    else:
        source.fetch_metadata.return_value = fetch_return if fetch_return is not None else {
            "search_query": f"{name} query",
            "detailed_track": {"id": "1"},
            "source_metadata": source_metadata if source_metadata is not None else {},
        }
    return source


def _make_mp3(artist="Test Artist", title="Test Track", parsed=("", ""), added=None):
    mp3 = Mock()
    mp3.metadata = {}
    if artist:
        mp3.metadata["TPE1"] = artist
    if title:
        mp3.metadata["TIT2"] = title
    mp3.parsed_filename = parsed
    mp3.update_metadata.return_value = added if added is not None else {}
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
    def test_all_sources_succeed(self):
        bc_data = {"auto": {"results": [1, 2]}}
        mb_data = {"recordings": [3]}
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp", search_return=bc_data),
            _make_source("MusicBrainz", search_return=mb_data),
        ]

        results = search_all_sources("Artist - Title", registry)

        assert results["Bandcamp"]["success"] is True
        assert results["Bandcamp"]["data"] == bc_data
        assert results["MusicBrainz"]["success"] is True
        assert results["MusicBrainz"]["data"] == mb_data

    def test_first_source_fails_second_succeeds(self):
        mb_data = {"recordings": []}
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp", search_raises=ConnectionError("timeout")),
            _make_source("MusicBrainz", search_return=mb_data),
        ]

        results = search_all_sources("Artist - Title", registry)

        assert results["Bandcamp"]["success"] is False
        assert "timeout" in results["Bandcamp"]["error"]
        assert results["MusicBrainz"]["success"] is True
        assert results["MusicBrainz"]["data"] == mb_data

    def test_first_source_succeeds_second_fails(self):
        bc_data = {"auto": {"results": []}}
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp", search_return=bc_data),
            _make_source("MusicBrainz", search_raises=Exception("api down")),
        ]

        results = search_all_sources("Artist - Title", registry)

        assert results["Bandcamp"]["success"] is True
        assert results["MusicBrainz"]["success"] is False
        assert "api down" in results["MusicBrainz"]["error"]

    def test_all_sources_fail(self):
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp", search_raises=Exception("bc down")),
            _make_source("MusicBrainz", search_raises=Exception("mb down")),
        ]

        results = search_all_sources("Artist - Title", registry)

        assert results["Bandcamp"]["success"] is False
        assert results["MusicBrainz"]["success"] is False

    def test_no_sources_registered(self):
        registry = Mock()
        registry.get_all_sources.return_value = []

        results = search_all_sources("Artist - Title", registry)

        assert results == {}

    def test_query_passed_through_unchanged(self):
        source = _make_source("Bandcamp")
        registry = Mock()
        registry.get_all_sources.return_value = [source]

        search_all_sources("Daft Punk - Harder Better Faster Stronger", registry)

        source.search.assert_called_once_with("Daft Punk - Harder Better Faster Stronger")

    def test_result_includes_source_reference(self):
        source = _make_source("Bandcamp", search_return={})
        registry = Mock()
        registry.get_all_sources.return_value = [source]

        results = search_all_sources("query", registry)

        assert results["Bandcamp"]["source"] is source


class TestEnrichWithAllSources:
    @patch("track_id.data_sources.MP3File")
    def test_all_sources_succeed(self, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp"),
            _make_source("MusicBrainz"),
        ]

        result = enrich_with_all_sources("test.mp3", registry)

        assert result["all_results"]["Bandcamp"]["success"] is True
        assert result["all_results"]["MusicBrainz"]["success"] is True

    @patch("track_id.data_sources.MP3File")
    def test_first_source_result_is_successful_enrichment(self, mock_mp3_class):
        """successful_enrichment should come from the first source in registry order."""
        mock_mp3_class.return_value = _make_mp3()
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp"),
            _make_source("MusicBrainz"),
        ]

        result = enrich_with_all_sources("test.mp3", registry)

        # The winning result is keyed by the first source's name.
        assert "bandcamp_track" in result["successful_enrichment"]
        assert "musicbrainz_track" not in result["successful_enrichment"]

    @patch("track_id.data_sources.MP3File")
    def test_first_fails_second_succeeds(self, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp", fetch_raises=Exception("not found on bc")),
            _make_source("MusicBrainz"),
        ]

        result = enrich_with_all_sources("test.mp3", registry)

        assert result["all_results"]["Bandcamp"]["success"] is False
        assert "not found on bc" in result["all_results"]["Bandcamp"]["error"]
        assert result["all_results"]["MusicBrainz"]["success"] is True
        assert "musicbrainz_track" in result["successful_enrichment"]

    @patch("track_id.data_sources.MP3File")
    def test_first_succeeds_second_fails(self, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp"),
            _make_source("MusicBrainz", fetch_raises=Exception("mb api down")),
        ]

        result = enrich_with_all_sources("test.mp3", registry)

        assert result["all_results"]["Bandcamp"]["success"] is True
        assert result["all_results"]["MusicBrainz"]["success"] is False
        assert "bandcamp_track" in result["successful_enrichment"]

    @patch("track_id.data_sources.MP3File")
    def test_metadata_merged_first_source_wins_per_field(self, mock_mp3_class):
        """Merged metadata is written once; first source to supply a field wins."""
        mp3 = _make_mp3()
        mock_mp3_class.return_value = mp3
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp", source_metadata={"TALB": "BC Album"}),
            _make_source("MusicBrainz", source_metadata={"TALB": "MB Album", "TDRC": "2024"}),
        ]

        enrich_with_all_sources("test.mp3", registry)

        # update_metadata is called exactly once with the merged dict.
        mp3.update_metadata.assert_called_once_with(
            {"TALB": "BC Album", "TDRC": "2024"}, force=False, dry_run=False
        )

    @patch("track_id.data_sources.MP3File")
    def test_all_sources_fail_raises_value_error(self, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp", fetch_raises=Exception("bc down")),
            _make_source("MusicBrainz", fetch_raises=Exception("mb down")),
        ]

        with pytest.raises(ValueError, match="No data source could enrich"):
            enrich_with_all_sources("test.mp3", registry)

    @patch("track_id.data_sources.MP3File")
    def test_no_metadata_and_no_filename_raises(self, mock_mp3_class):
        mp3 = _make_mp3(artist="", title="", parsed=("", ""))
        mock_mp3_class.return_value = mp3
        registry = Mock()
        registry.get_all_sources.return_value = []

        with pytest.raises(ValueError, match="missing artist and title metadata"):
            enrich_with_all_sources("test.mp3", registry)

    @patch("track_id.data_sources.MP3File")
    def test_falls_back_to_filename_when_no_id3_tags(self, mock_mp3_class):
        mp3 = _make_mp3(artist="", title="", parsed=("Parsed Artist", "Parsed Title"))
        mock_mp3_class.return_value = mp3
        source = _make_source("Bandcamp")
        registry = Mock()
        registry.get_all_sources.return_value = [source]

        result = enrich_with_all_sources("test.mp3", registry)

        assert result["search_query"] == "Parsed Artist - Parsed Title"

    @patch("track_id.data_sources.MP3File")
    def test_search_query_built_from_id3_tags(self, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3(artist="Burial", title="Archangel")
        source = _make_source("Bandcamp")
        registry = Mock()
        registry.get_all_sources.return_value = [source]

        result = enrich_with_all_sources("test.mp3", registry)

        assert result["search_query"] == "Burial - Archangel"

    @patch("track_id.data_sources.MP3File")
    def test_file_path_in_result(self, mock_mp3_class):
        mock_mp3_class.return_value = _make_mp3()
        registry = Mock()
        registry.get_all_sources.return_value = [
            _make_source("Bandcamp"),
        ]

        result = enrich_with_all_sources("my_track.mp3", registry)

        assert result["file_path"] == "my_track.mp3"


class _FakeMP3File:
    """Mimics MP3File's cache-invalidation: after update_metadata, `metadata`
    reflects the post-update state (the newly added fields are now on the file)."""

    def __init__(self, existing):
        self.metadata = dict(existing)
        self.parsed_filename = ("", "")

    def update_metadata(self, new_metadata):
        added = {k: v for k, v in new_metadata.items()
                 if k != "artwork_url" and not self.metadata.get(k)}
        # Simulate reading fresh tags back from disk after saving.
        self.metadata = {**self.metadata, **added}
        return added


class _FakeSource(DataSource):
    def __init__(self, source_metadata):
        super().__init__("Fake")
        self._source_metadata = source_metadata

    def search(self, search_text):
        return {}

    def find_matching_track(self, search_results, artist, title):
        return {"id": "1"}

    def extract_metadata(self, track_data):
        return self._source_metadata


class TestEnrichExistingMetadataSnapshot:
    @patch("track_id.data_sources.MP3File")
    def test_existing_metadata_excludes_newly_added_fields(self, mock_mp3_class):
        # File already has artist + title; enrichment adds album + year.
        existing = {"TPE1": "Test Artist", "TIT2": "Test Track"}
        fake_mp3 = _FakeMP3File(existing)
        mock_mp3_class.return_value = fake_mp3

        source = _FakeSource({"TALB": "New Album", "TDRC": "2024"})
        result = source.enrich_mp3_file("track.mp3")

        # existing_metadata is the pre-update snapshot, not the post-update file.
        assert result["existing_metadata"] == {"TPE1": "Test Artist", "TIT2": "Test Track"}
        assert result["added_metadata"] == {"TALB": "New Album", "TDRC": "2024"}
        # The added fields must not leak into existing_metadata.
        assert "TALB" not in result["existing_metadata"]
        assert "TDRC" not in result["existing_metadata"]


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


class TestMatchScoring:
    """Tests for the shared candidate-scoring helpers."""

    def test_normalize_strips_parentheticals_and_feat(self):
        assert normalize_for_match("Windowlicker (Remastered)") == "windowlicker"
        assert normalize_for_match("Higher feat. Someone") == "higher"
        assert normalize_for_match("Track [2020 Mix]") == "track"

    def test_normalize_collapses_punctuation(self):
        assert normalize_for_match("How We Feelin'?") == "how we feelin"

    def test_exact_match_scores_high(self):
        assert match_score("Aphex Twin", "Xtal", "Aphex Twin", "Xtal") == pytest.approx(1.0)

    def test_decorated_variant_still_matches(self):
        score = match_score("Aphex Twin", "Xtal (Remastered 2019)", "Aphex Twin", "Xtal")
        assert score >= 0.9

    def test_wrong_artist_scores_low(self):
        score = match_score("Someone Else", "Xtal", "Aphex Twin", "Xtal")
        assert score < 0.9

    def test_find_best_match_picks_best_not_first(self):
        candidates = [
            {"artist": "Aphex Twin", "title": "Xtal (Some Other Band Cover)"},
            {"artist": "Aphex Twin", "title": "Xtal"},
        ]
        best = find_best_match(
            candidates, "Aphex Twin", "Xtal",
            get_artist=lambda c: c["artist"], get_title=lambda c: c["title"],
        )
        assert best is not None
        assert best["title"] == "Xtal"

    def test_find_best_match_rejects_poor_candidates(self):
        candidates = [{"artist": "Different Artist", "title": "Different Track"}]
        best = find_best_match(
            candidates, "Test Artist", "Test Track",
            get_artist=lambda c: c["artist"], get_title=lambda c: c["title"],
        )
        assert best is None

    def test_find_best_match_empty_candidates(self):
        assert find_best_match(
            [], "Artist", "Title",
            get_artist=lambda c: "", get_title=lambda c: "",
        ) is None


class TestSearchConcurrency:
    def test_sources_searched_in_parallel(self):
        """Total search time is the slowest source, not the sum."""
        import time as _time

        def slow_search(*args, **kwargs):
            _time.sleep(0.2)
            return {}

        registry = Mock()
        sources = []
        for name in ("A", "B", "C"):
            s = Mock()
            s.name = name
            s.search.side_effect = slow_search
            sources.append(s)
        registry.get_all_sources.return_value = sources

        start = _time.perf_counter()
        results = search_all_sources("query", registry)
        elapsed = _time.perf_counter() - start

        assert elapsed < 0.45  # 3 x 0.2s sequential would be >= 0.6s
        assert list(results) == ["A", "B", "C"]

    def test_on_source_done_fires_for_success_and_failure(self):
        registry = Mock()
        ok = Mock()
        ok.name = "OK"
        ok.search.return_value = {"data": 1}
        bad = Mock()
        bad.name = "Bad"
        bad.search.side_effect = Exception("boom")
        registry.get_all_sources.return_value = [ok, bad]

        seen = {}
        search_all_sources("query", registry, on_source_done=lambda n, r: seen.update({n: r}))

        assert seen["OK"]["success"] is True
        assert seen["Bad"]["success"] is False
        assert "boom" in seen["Bad"]["error"]

    def test_results_in_registry_order_regardless_of_completion(self):
        import time as _time

        registry = Mock()
        slow = Mock()
        slow.name = "Slow"
        slow.search.side_effect = lambda *a: _time.sleep(0.15) or {}
        fast = Mock()
        fast.name = "Fast"
        fast.search.return_value = {}
        registry.get_all_sources.return_value = [slow, fast]

        results = search_all_sources("query", registry)

        assert list(results) == ["Slow", "Fast"]
