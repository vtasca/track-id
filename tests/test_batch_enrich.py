"""Tests for directory-mode enrichment."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from track_id.track_id import app

MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def _result(added):
    return {"successful_enrichment": {"added_metadata": added}}


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def music_dir(tmp_path):
    for name in ("a.mp3", "b.mp3", "c.mp3"):
        (tmp_path / name).write_bytes(MP3_FRAME * 4)
    return tmp_path


class TestEnrichDirectory:
    @patch("track_id.track_id.unified_enrich")
    def test_mixed_outcomes_counted(self, mock_enrich, runner, music_dir):
        mock_enrich.side_effect = [
            _result({"TALB": "Album", "TDRC": "2020"}),      # a: enriched
            _result({"artwork": "Artwork already exists, skipped"}),  # b: nothing new
            ValueError("No data source could enrich the file"),       # c: unmatched
        ]

        result = runner.invoke(app, ["enrich", str(music_dir)])

        assert result.exit_code == 0
        assert mock_enrich.call_count == 3
        assert "+2 fields" in result.output
        assert "already tagged" in result.output
        assert "No data source" in result.output
        assert "enriched 1" in result.output
        assert "1 already tagged" in result.output
        assert "1 unmatched" in result.output

    @patch("track_id.track_id.unified_enrich")
    def test_files_processed_in_sorted_order(self, mock_enrich, runner, music_dir):
        mock_enrich.return_value = _result({})

        runner.invoke(app, ["enrich", str(music_dir)])

        called_paths = [c.args[0] for c in mock_enrich.call_args_list]
        assert [p.split("/")[-1] for p in called_paths] == ["a.mp3", "b.mp3", "c.mp3"]

    @patch("track_id.track_id.unified_enrich")
    def test_flags_passed_through(self, mock_enrich, runner, music_dir):
        mock_enrich.return_value = _result({"TALB": "X"})

        result = runner.invoke(app, ["enrich", str(music_dir), "--force", "--dry-run"])

        assert result.exit_code == 0
        for call in mock_enrich.call_args_list:
            assert call.kwargs == {"force": True, "dry_run": True}
        assert "would enrich 3" in result.output
        assert "dry run: no changes were written" in result.output

    def test_empty_directory_warns(self, runner, tmp_path):
        result = runner.invoke(app, ["enrich", str(tmp_path)])

        assert result.exit_code == 0
        assert "no .mp3 files found" in result.output

    @patch("track_id.track_id.unified_enrich")
    def test_one_failure_does_not_stop_the_batch(self, mock_enrich, runner, music_dir):
        mock_enrich.side_effect = [
            ConnectionError("network down"),
            _result({"TALB": "X"}),
            _result({"TALB": "Y"}),
        ]

        result = runner.invoke(app, ["enrich", str(music_dir)])

        assert result.exit_code == 0
        assert mock_enrich.call_count == 3
        assert "enriched 2" in result.output
        assert "1 unmatched" in result.output
