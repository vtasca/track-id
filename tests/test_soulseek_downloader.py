"""Unit tests for Soulseek downloader ranking and filtering logic."""

import pytest
from track_id.soulseek_downloader import SlskResult, rank_results, _sanitize_filename


def _make_result(**kwargs) -> SlskResult:
    defaults = dict(
        username="peer",
        remote_path="\\Music\\Artist - Title.mp3",
        file_size=8 * 1024 * 1024,  # 8 MB
        extension="mp3",
        bitrate=320,
        duration=240,
        avg_speed=1000,
        has_free_slots=True,
    )
    defaults.update(kwargs)
    return SlskResult(**defaults)


# --- rank_results ---

class TestRankResults:
    def test_empty_returns_empty(self):
        assert rank_results([], "Artist", "Title") == []

    def test_returns_same_count(self):
        results = [_make_result(), _make_result(username="peer2")]
        ranked = rank_results(results, "Artist", "Title")
        assert len(ranked) == 2

    def test_prefers_close_filename_match(self):
        good = _make_result(remote_path="\\Music\\Artist - Title.mp3")
        bad = _make_result(username="peer2", remote_path="\\Random\\Totally Different Track.mp3")
        ranked = rank_results([bad, good], "Artist", "Title")
        assert ranked[0] is good

    def test_prefers_higher_bitrate(self):
        high = _make_result(bitrate=320)
        low = _make_result(username="peer2", bitrate=128)
        ranked = rank_results([low, high], "Artist", "Title")
        assert ranked[0] is high

    def test_prefers_mp3_over_flac(self):
        mp3 = _make_result(extension="mp3")
        flac = _make_result(username="peer2", extension="flac")
        # Identical filename and bitrate — format is the tiebreaker
        ranked = rank_results([flac, mp3], "Artist", "Title")
        assert ranked[0] is mp3

    def test_penalises_files_below_min_size(self):
        small = _make_result(file_size=100)       # too small
        normal = _make_result(username="peer2", file_size=5 * 1024 * 1024)
        ranked = rank_results([small, normal], "Artist", "Title")
        assert ranked[0] is normal

    def test_penalises_files_above_max_size(self):
        huge = _make_result(file_size=200 * 1024 * 1024)  # 200 MB
        normal = _make_result(username="peer2", file_size=5 * 1024 * 1024)
        ranked = rank_results([huge, normal], "Artist", "Title")
        assert ranked[0] is normal

    def test_scores_are_between_0_and_1(self):
        results = [_make_result(), _make_result(username="peer2", bitrate=64, extension="flac")]
        ranked = rank_results(results, "Artist", "Title")
        for r in ranked:
            assert 0.0 <= r.score <= 1.0

    def test_sorted_descending(self):
        results = [
            _make_result(username=f"peer{i}", bitrate=64 + i * 64)
            for i in range(4)
        ]
        ranked = rank_results(results, "Artist", "Title")
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_unknown_bitrate_does_not_crash(self):
        r = _make_result(bitrate=None)
        ranked = rank_results([r], "Artist", "Title")
        assert len(ranked) == 1
        assert 0.0 <= ranked[0].score <= 1.0

    def test_unknown_bitrate_gets_mild_penalty(self):
        known = _make_result(bitrate=192)
        unknown = _make_result(username="peer2", bitrate=None)
        ranked = rank_results([known, unknown], "Artist", "Title")
        # 192 kbps should beat unknown bitrate
        assert ranked[0] is known

    def test_case_insensitive_filename_matching(self):
        r = _make_result(remote_path="\\Music\\ARTIST - TITLE.MP3")
        ranked = rank_results([r], "artist", "title")
        assert ranked[0].score > 0.4  # good match despite case difference

    def test_prefers_peer_with_free_slot(self):
        free = _make_result(has_free_slots=True)
        busy = _make_result(username="peer2", has_free_slots=False)
        # Identical otherwise — a free upload slot is the tiebreaker
        ranked = rank_results([busy, free], "Artist", "Title")
        assert ranked[0] is free

    def test_prefers_faster_peer(self):
        fast = _make_result(avg_speed=2_000_000)   # 2 MB/s, caps at 1.0
        slow = _make_result(username="peer2", avg_speed=10_000)
        ranked = rank_results([slow, fast], "Artist", "Title")
        assert ranked[0] is fast

    def test_free_slot_outweighs_minor_bitrate_edge(self):
        # A ready peer at 256 kbps should beat a busy peer at 320 kbps:
        # availability (0.12) dominates the small bitrate gap (0.20 * 0.2).
        ready = _make_result(bitrate=256, has_free_slots=True)
        busy = _make_result(username="peer2", bitrate=320, has_free_slots=False)
        ranked = rank_results([busy, ready], "Artist", "Title")
        assert ranked[0] is ready

    def test_zero_speed_does_not_crash(self):
        r = _make_result(avg_speed=0)
        ranked = rank_results([r], "Artist", "Title")
        assert 0.0 <= ranked[0].score <= 1.0


# --- _sanitize_filename ---

class TestSanitizeFilename:
    def test_removes_invalid_chars(self):
        assert "/" not in _sanitize_filename("a/b")
        assert "\\" not in _sanitize_filename("a\\b")
        assert ":" not in _sanitize_filename("a:b")
        assert "?" not in _sanitize_filename("a?b")
        assert "*" not in _sanitize_filename("a*b")

    def test_preserves_normal_chars(self):
        assert _sanitize_filename("Artist - Title") == "Artist - Title"

    def test_strips_whitespace(self):
        assert _sanitize_filename("  Name  ") == "Name"

    def test_empty_string(self):
        assert _sanitize_filename("") == ""


# --- SlskResult.display_name ---

class TestSlskResultDisplayName:
    def test_unix_path(self):
        r = _make_result(remote_path="/music/artist/file.mp3")
        assert r.display_name == "file.mp3"

    def test_windows_path(self):
        r = _make_result(remote_path="\\Music\\Artist - Title.mp3")
        assert r.display_name == "Artist - Title.mp3"

    def test_bare_filename(self):
        r = _make_result(remote_path="file.mp3")
        assert r.display_name == "file.mp3"
