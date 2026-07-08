"""Tests for MP3File.update_metadata write/force/dry-run behavior on real files."""

import shutil

import pytest

from track_id.mp3_utils import MP3File


@pytest.fixture
def mp3_path(tmp_path):
    """A minimal MP3 file (one silent-ish MPEG frame header + padding)."""
    path = tmp_path / "Test Artist - Test Track.mp3"
    frame = b"\xff\xfb\x90\x00" + b"\x00" * 413  # MPEG1 Layer3 128kbps frame
    path.write_bytes(frame * 4)
    return str(path)


class TestUpdateMetadata:
    def test_fills_empty_fields(self, mp3_path):
        mp3 = MP3File(mp3_path)

        added = mp3.update_metadata({"TIT2": "Test Track", "TPE1": "Test Artist"})

        assert added == {"TIT2": "Test Track", "TPE1": "Test Artist"}
        reread = MP3File(mp3_path)
        assert reread.metadata["TIT2"] == "Test Track"
        assert reread.metadata["TPE1"] == "Test Artist"

    def test_existing_fields_not_overwritten_by_default(self, mp3_path):
        MP3File(mp3_path).update_metadata({"TIT2": "Original Title"})

        mp3 = MP3File(mp3_path)
        added = mp3.update_metadata({"TIT2": "New Title", "TALB": "New Album"})

        assert added == {"TALB": "New Album"}
        assert MP3File(mp3_path).metadata["TIT2"] == "Original Title"

    def test_force_overwrites_existing_fields(self, mp3_path):
        MP3File(mp3_path).update_metadata({"TIT2": "Original Title"})

        mp3 = MP3File(mp3_path)
        added = mp3.update_metadata({"TIT2": "New Title"}, force=True)

        assert added == {"TIT2": "New Title"}
        assert MP3File(mp3_path).metadata["TIT2"] == "New Title"

    def test_dry_run_reports_without_writing(self, mp3_path, tmp_path):
        untouched = tmp_path / "copy.mp3"
        shutil.copy(mp3_path, untouched)

        mp3 = MP3File(mp3_path)
        added = mp3.update_metadata(
            {"TIT2": "Test Track", "artwork_url": "https://example.com/a.jpg"},
            dry_run=True,
        )

        assert added["TIT2"] == "Test Track"
        assert added["artwork"] == "Would add album artwork"
        # File bytes are untouched and no tags were written
        assert open(mp3_path, "rb").read() == open(untouched, "rb").read()
        assert MP3File(mp3_path).metadata == {}

    def test_txxx_fields_written(self, mp3_path):
        mp3 = MP3File(mp3_path)

        added = mp3.update_metadata({"TXXX:GENRE": "ambient"})

        assert added == {"TXXX:GENRE": "ambient"}
        assert MP3File(mp3_path).metadata["TXXX:GENRE"] == "ambient"
