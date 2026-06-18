"""Unit tests for Soulseek downloader ranking and filtering logic."""

import pytest
from track_id.soulseek_downloader import (
    SlskResult,
    rank_results,
    _sanitize_filename,
    _sniff_audio_format,
)


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


class TestSniffAudioFormat:
    @pytest.mark.parametrize("header,expected", [
        (b"fLaC\x00\x00\x00\x22", "flac"),
        (b"ID3\x04\x00\x00\x00\x00", "mp3"),
        (b"\xff\xfb\x90\x00", "mp3"),               # MPEG-1 Layer III frame
        (b"\xff\xf1\x50\x80", "aac"),               # ADTS AAC (layer bits 00)
        (b"OggS\x00\x02\x00\x00", "ogg"),
        (b"RIFF\x24\x08\x00\x00WAVE", "wav"),
        (b"\x00\x00\x00\x20ftypM4A ", "mp4"),
    ])
    def test_recognizes_audio_headers(self, tmp_path, header, expected):
        p = tmp_path / "f.bin"
        p.write_bytes(header + b"\x00" * 64)
        assert _sniff_audio_format(p) == expected

    @pytest.mark.parametrize("data", [
        b"<!DOCTYPE html><html>error</html>",       # HTML error page
        b"PK\x03\x04not really audio",              # zip archive
        b"\x00\x00",                                 # too short
    ])
    def test_rejects_non_audio(self, tmp_path, data):
        p = tmp_path / "f.bin"
        p.write_bytes(data)
        assert _sniff_audio_format(p) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert _sniff_audio_format(tmp_path / "nope.mp3") is None


# --- race_download ---

import asyncio

from aioslsk.transfer.model import TransferState

from track_id.config import SoulseekConfig
from track_id.soulseek_downloader import DownloadError, SoulseekDownloader

_S = TransferState.State


class _FakeState:
    def __init__(self, value):
        self.VALUE = value


class _FakeTransfer:
    """A transfer whose state walks through `states`, one step per access."""

    def __init__(self, states, *, started=False, local_path=None, filesize=None):
        self._states = states
        self._idx = 0
        self.start_time = 1.0 if started else None
        self.bytes_transfered = filesize or 0
        self.filesize = filesize
        self.local_path = local_path
        self.fail_reason = None
        self.abort_reason = None

    @property
    def state(self):
        value = self._states[self._idx]
        if self._idx < len(self._states) - 1:
            self._idx += 1
        return _FakeState(value)


class _FakeTransfers:
    def __init__(self, transfers):
        self._queue = list(transfers)
        self.requested = []   # (username, filename) in request order
        self.aborted = []     # transfer objects that were aborted

    async def download(self, username, filename):
        self.requested.append((username, filename))
        return self._queue.pop(0)

    async def abort(self, transfer):
        self.aborted.append(transfer)


class _FakeClient:
    def __init__(self, transfers):
        self.transfers = _FakeTransfers(transfers)


def _downloader(transfers, download_dir):
    dl = SoulseekDownloader(SoulseekConfig("u", "p"), download_dir)
    dl._client = _FakeClient(transfers)
    return dl


# ID3v2 header followed by an MPEG frame sync — passes content verification.
_MP3_HEADER = b"ID3\x04\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x00"


def _winner_transfer(tmp_path, name="src.mp3"):
    """A transfer that starts downloading then completes, with a real file."""
    src = tmp_path / name
    src.write_bytes(_MP3_HEADER + b"\x00" * 1010)
    return _FakeTransfer([_S.DOWNLOADING, _S.COMPLETE], started=True,
                         local_path=str(src), filesize=1024)


class TestRaceDownload:
    def test_first_started_peer_wins_and_losers_aborted(self, tmp_path):
        loser_a = _FakeTransfer([_S.QUEUED])
        winner = _winner_transfer(tmp_path)
        loser_b = _FakeTransfer([_S.QUEUED])
        dl = _downloader([loser_a, winner, loser_b], tmp_path)
        cands = [
            _make_result(username="a"),
            _make_result(username="winner"),
            _make_result(username="b"),
        ]
        dest = tmp_path / "out.mp3"

        result = asyncio.run(dl.race_download(cands, dest, parallelism=3))

        assert result == dest
        assert dest.exists()
        aborted = dl._client.transfers.aborted
        assert loser_a in aborted and loser_b in aborted
        assert winner not in aborted

    def test_failed_peer_dropped_and_next_requested(self, tmp_path):
        failed = _FakeTransfer([_S.FAILED])
        winner = _winner_transfer(tmp_path)
        dl = _downloader([failed, winner], tmp_path)
        cands = [_make_result(username="dead"), _make_result(username="good")]
        dest = tmp_path / "out.mp3"

        # parallelism=1 forces sequential refill on failure
        result = asyncio.run(dl.race_download(cands, dest, parallelism=1))

        assert result == dest
        assert dl._client.transfers.requested == [
            ("dead", cands[0].remote_path),
            ("good", cands[1].remote_path),
        ]

    def test_peer_stuck_in_queue_is_aborted_and_replaced(self, tmp_path):
        stuck = _FakeTransfer([_S.QUEUED])  # never starts
        winner = _winner_transfer(tmp_path)
        dl = _downloader([stuck, winner], tmp_path)
        cands = [_make_result(username="slow"), _make_result(username="good")]
        dest = tmp_path / "out.mp3"

        # queue_timeout=0 means an unstarted peer is dropped on first poll
        result = asyncio.run(
            dl.race_download(cands, dest, parallelism=1, queue_timeout=0.0)
        )

        assert result == dest
        assert stuck in dl._client.transfers.aborted

    def test_all_candidates_fail_raises(self, tmp_path):
        dl = _downloader(
            [_FakeTransfer([_S.FAILED]), _FakeTransfer([_S.FAILED])], tmp_path
        )
        cands = [_make_result(username="a"), _make_result(username="b")]

        with pytest.raises(DownloadError):
            asyncio.run(dl.race_download(cands, tmp_path / "out.mp3", parallelism=2))

    def test_winner_failing_midway_falls_back_to_next(self, tmp_path):
        # First peer starts then dies; the fallback peer completes.
        flaky = _FakeTransfer([_S.DOWNLOADING, _S.FAILED], started=True)
        winner = _winner_transfer(tmp_path)
        dl = _downloader([flaky, winner], tmp_path)
        cands = [_make_result(username="flaky"), _make_result(username="good")]
        dest = tmp_path / "out.mp3"

        result = asyncio.run(dl.race_download(cands, dest, parallelism=1))

        assert result == dest
        assert dest.exists()
