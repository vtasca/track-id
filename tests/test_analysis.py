"""Tests for the file inspection module behind analyze and doctor."""

import pytest
from typer.testing import CliRunner

from track_id.analysis import (
    CORE_TAGS,
    inspect_file,
    iter_audio_files,
    sniff_audio_format,
)
from track_id.mp3_utils import MP3File
from track_id.track_id import app

MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413  # MPEG1 Layer3 128kbps frame


@pytest.fixture
def mp3_path(tmp_path):
    path = tmp_path / "Test Artist - Test Track.mp3"
    path.write_bytes(MP3_FRAME * 4)
    return str(path)


@pytest.fixture
def fake_mp3_path(tmp_path):
    """An HTML error page saved with an .mp3 extension."""
    path = tmp_path / "junk.mp3"
    path.write_bytes(b"<html><body>404 Not Found</body></html>" * 20)
    return str(path)


class TestInspectFile:
    def test_reads_stream_properties(self, mp3_path):
        report = inspect_file(mp3_path)

        assert report.actual_format == "mp3"
        assert report.claimed_format == "mp3"
        assert not report.format_mismatch
        assert report.readable
        assert report.bitrate == 128000
        assert report.sample_rate == 44100
        assert report.channels == 2

    def test_reports_missing_core_tags(self, mp3_path):
        report = inspect_file(mp3_path)

        assert report.missing_tags == list(CORE_TAGS)
        assert not report.has_artwork

    def test_sees_written_tags(self, mp3_path):
        MP3File(mp3_path).update_metadata({"TIT2": "Test Track", "TPE1": "Test Artist"})

        report = inspect_file(mp3_path)

        assert report.tags["TIT2"] == "Test Track"
        assert report.missing_tags == ["TALB", "TDRC"]

    def test_fake_mp3_is_flagged_not_raised(self, fake_mp3_path):
        report = inspect_file(fake_mp3_path)

        assert report.actual_format is None
        assert not report.readable
        assert "not a recognized audio file" in report.problems()

    def test_mislabeled_flac_reports_mismatch(self, tmp_path):
        path = tmp_path / "labeled.mp3"
        path.write_bytes(b"fLaC" + b"\x00" * 100)

        report = inspect_file(str(path))

        assert report.actual_format == "flac"
        assert report.format_mismatch
        assert any("bytes are flac" in p for p in report.problems())

    def test_low_bitrate_flagged_against_threshold(self, mp3_path):
        report = inspect_file(mp3_path)  # 128 kbps fixture

        assert any("128 kbps < 192 kbps" in p for p in report.problems(192))
        assert not any("kbps" in p for p in report.problems(128))

    def test_clean_file_has_no_problems(self, mp3_path):
        mp3 = MP3File(mp3_path)
        mp3.update_metadata(
            {"TIT2": "Title", "TPE1": "Artist", "TALB": "Album", "TDRC": "2020"}
        )
        # Write artwork directly (no network)
        from mutagen.id3 import APIC, ID3
        id3 = ID3(mp3_path)
        id3["APIC:"] = APIC(encoding=3, mime="image/jpeg", type=3, desc="", data=b"\xff\xd8\xff fake")
        id3.save(mp3_path)

        report = inspect_file(mp3_path)

        assert report.problems(128) == []
        assert report.has_artwork


class TestIterAudioFiles:
    def test_recursive_sorted_and_skips_hidden(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "b.mp3").write_bytes(MP3_FRAME)
        (tmp_path / "sub" / "a.mp3").write_bytes(MP3_FRAME)
        (tmp_path / ".hidden.mp3").write_bytes(MP3_FRAME)
        (tmp_path / "notes.txt").write_text("not audio")

        files = iter_audio_files(tmp_path)

        assert [f.name for f in files] == ["b.mp3", "a.mp3"]


class TestSniffReexports:
    def test_soulseek_downloader_aliases_still_work(self):
        from track_id.soulseek_downloader import (
            _FORMAT_ALIASES,
            _sanitize_filename,
            _sniff_audio_format,
        )

        assert _sniff_audio_format is sniff_audio_format
        assert "mp3" in _FORMAT_ALIASES
        assert _sanitize_filename("a/b") == "ab"


class TestAnalyzeCommand:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_analyze_reports_file(self, runner, mp3_path):
        result = runner.invoke(app, ["analyze", mp3_path])

        assert result.exit_code == 0
        assert "128 kbps" in result.output
        assert "missing tags" in result.output

    def test_analyze_missing_file(self, runner):
        result = runner.invoke(app, ["analyze", "no/such/file.mp3"])

        assert result.exit_code == 1
        assert "does not exist" in result.output
