"""Tests for the tag-driven rename command and its template helpers."""

import pytest
from typer.testing import CliRunner

from track_id.mp3_utils import MP3File, build_filename_from_tags, validate_rename_template
from track_id.track_id import app

MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def _make_tagged(path, artist="Test Artist", title="Test Track", **extra):
    path.write_bytes(MP3_FRAME * 4)
    tags = {"TPE1": artist, "TIT2": title, **extra}
    MP3File(str(path)).update_metadata(tags)
    return path


class TestTemplateHelpers:
    def test_default_template(self):
        name = build_filename_from_tags(
            {"TPE1": "Aphex Twin", "TIT2": "Xtal"}, "{artist} - {title}"
        )
        assert name == "Aphex Twin - Xtal"

    def test_all_fields(self):
        metadata = {
            "TPE1": "A", "TIT2": "T", "TALB": "L", "TDRC": "1999",
            "TCON": "House", "TRCK": "3/10",
        }
        name = build_filename_from_tags(
            metadata, "{year} {album} {track} {genre} {artist} {title}"
        )
        assert name == "1999 L 310 House A T"  # '/' sanitized out of track

    def test_missing_referenced_field_raises(self):
        with pytest.raises(ValueError, match="missing tag values for: album"):
            build_filename_from_tags({"TPE1": "A", "TIT2": "T"}, "{album} - {title}")

    def test_illegal_characters_sanitized(self):
        name = build_filename_from_tags(
            {"TPE1": "AC/DC", "TIT2": "Back?"}, "{artist} - {title}"
        )
        assert name == "ACDC - Back"

    def test_unknown_field_rejected(self):
        with pytest.raises(ValueError, match="unknown template field {bpm}"):
            validate_rename_template("{artist} {bpm}")

    def test_valid_template_accepted(self):
        validate_rename_template("{artist} - {title} ({year})")


class TestRenameCommand:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_renames_single_file(self, runner, tmp_path):
        f = _make_tagged(tmp_path / "download123.mp3")

        result = runner.invoke(app, ["rename", str(f)])

        assert result.exit_code == 0
        assert not f.exists()
        assert (tmp_path / "Test Artist - Test Track.mp3").exists()
        assert "renamed 1" in result.output

    def test_renames_directory(self, runner, tmp_path):
        _make_tagged(tmp_path / "a.mp3", artist="One", title="First")
        _make_tagged(tmp_path / "b.mp3", artist="Two", title="Second")

        result = runner.invoke(app, ["rename", str(tmp_path)])

        assert result.exit_code == 0
        assert (tmp_path / "One - First.mp3").exists()
        assert (tmp_path / "Two - Second.mp3").exists()
        assert "renamed 2" in result.output

    def test_dry_run_moves_nothing(self, runner, tmp_path):
        f = _make_tagged(tmp_path / "download123.mp3")

        result = runner.invoke(app, ["rename", str(f), "--dry-run"])

        assert result.exit_code == 0
        assert f.exists()
        assert not (tmp_path / "Test Artist - Test Track.mp3").exists()
        assert "would rename 1" in result.output

    def test_already_named_is_unchanged(self, runner, tmp_path):
        f = _make_tagged(tmp_path / "Test Artist - Test Track.mp3")

        result = runner.invoke(app, ["rename", str(f)])

        assert f.exists()
        assert "1 unchanged" in result.output

    def test_collision_skipped(self, runner, tmp_path):
        _make_tagged(tmp_path / "Test Artist - Test Track.mp3")
        dupe = _make_tagged(tmp_path / "duplicate.mp3")

        result = runner.invoke(app, ["rename", str(dupe)])

        assert dupe.exists()  # untouched
        assert "already exists" in result.output
        assert "1 skipped" in result.output

    def test_untagged_file_skipped(self, runner, tmp_path):
        f = tmp_path / "untagged.mp3"
        f.write_bytes(MP3_FRAME * 4)

        result = runner.invoke(app, ["rename", str(f)])

        assert f.exists()
        assert "missing tag values" in result.output
        assert "1 skipped" in result.output

    def test_custom_template(self, runner, tmp_path):
        f = _make_tagged(tmp_path / "x.mp3", TDRC="2001")

        result = runner.invoke(
            app, ["rename", str(f), "--template", "{year} {artist} - {title}"]
        )

        assert result.exit_code == 0
        assert (tmp_path / "2001 Test Artist - Test Track.mp3").exists()

    def test_bad_template_errors_before_touching_files(self, runner, tmp_path):
        f = _make_tagged(tmp_path / "x.mp3")

        result = runner.invoke(app, ["rename", str(f), "--template", "{nope}"])

        assert result.exit_code == 1
        assert "unknown template field" in result.output
        assert f.exists()

    def test_missing_path_errors(self, runner):
        result = runner.invoke(app, ["rename", "no/such/thing.mp3"])

        assert result.exit_code == 1
