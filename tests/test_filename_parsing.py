"""Edge-case tests for MP3File._parse_artist_title_from_filename()."""

import pytest
from track_id.mp3_utils import MP3File


def mp3(tmp_path, stem):
    """Create a zero-byte .mp3 file and return an MP3File for it."""
    path = tmp_path / f"{stem}.mp3"
    path.touch()
    return MP3File(str(path))


class TestFilenameParserBasic:
    def test_standard_artist_dash_title(self, tmp_path):
        assert mp3(tmp_path, "Artist - Title").parsed_filename == ("Artist", "Title")

    def test_colon_separator(self, tmp_path):
        assert mp3(tmp_path, "Artist:Title").parsed_filename == ("Artist", "Title")

    def test_extra_whitespace_around_dash(self, tmp_path):
        assert mp3(tmp_path, "Artist   -   Title").parsed_filename == ("Artist", "Title")

    def test_no_separator_returns_empty(self, tmp_path):
        assert mp3(tmp_path, "JustATitle").parsed_filename == ("", "")

    def test_directory_prefix_is_ignored(self, tmp_path):
        # os.path.basename must strip the directory component
        sub = tmp_path / "some" / "deep" / "path"
        sub.mkdir(parents=True)
        path = sub / "Artist - Title.mp3"
        path.touch()
        assert MP3File(str(path)).parsed_filename == ("Artist", "Title")


class TestFilenameParserMultipleSeparators:
    def test_multiple_dashes_title_keeps_remainder(self, tmp_path):
        # Non-greedy first group: artist gets the part before the FIRST dash
        assert mp3(tmp_path, "Artist - My Long Title - Remix").parsed_filename == (
            "Artist",
            "My Long Title - Remix",
        )

    def test_three_dash_segments(self, tmp_path):
        assert mp3(tmp_path, "A - B - C - D").parsed_filename == ("A", "B - C - D")


class TestFilenameParserBrackets:
    def test_bracket_prefix_stripped(self, tmp_path):
        assert mp3(tmp_path, "[Label] Artist - Title").parsed_filename == ("Artist", "Title")

    def test_multiple_bracket_groups_stripped(self, tmp_path):
        assert mp3(tmp_path, "[Cat] [Dog] Artist - Title").parsed_filename == ("Artist", "Title")

    def test_bracket_only_filename_returns_empty(self, tmp_path):
        assert mp3(tmp_path, "[SomeLabel]").parsed_filename == ("", "")

    def test_bracket_only_multiple_returns_empty(self, tmp_path):
        assert mp3(tmp_path, "[A] [B] [C]").parsed_filename == ("", "")


class TestFilenameParserMissingParts:
    def test_missing_artist_returns_empty(self, tmp_path):
        # "- Title" has no artist component
        assert mp3(tmp_path, "- Title").parsed_filename == ("", "")

    def test_missing_title_returns_empty(self, tmp_path):
        # "Artist -" has no title component
        assert mp3(tmp_path, "Artist -").parsed_filename == ("", "")

    def test_whitespace_title_returns_empty(self, tmp_path):
        # "Artist - " — title is whitespace only after strip
        assert mp3(tmp_path, "Artist - ").parsed_filename == ("", "")


class TestFilenameParserUnicode:
    def test_accented_characters(self, tmp_path):
        assert mp3(tmp_path, "Björk - Jóga").parsed_filename == ("Björk", "Jóga")

    def test_cyrillic_characters(self, tmp_path):
        assert mp3(tmp_path, "Земфира - Ариведерчи").parsed_filename == (
            "Земфира",
            "Ариведерчи",
        )

    def test_japanese_characters(self, tmp_path):
        assert mp3(tmp_path, "坂本龍一 - Merry Christmas Mr Lawrence").parsed_filename == (
            "坂本龍一",
            "Merry Christmas Mr Lawrence",
        )


class TestFilenameParserRealWorldPatterns:
    def test_track_number_prefix_stays_in_artist_field(self, tmp_path):
        # "01. Artist - Title" — the dot means no early dash match, so
        # the number+dot ends up prepended to the artist name
        assert mp3(tmp_path, "01. Artist - Title").parsed_filename == ("01. Artist", "Title")

    def test_parenthetical_year_in_title(self, tmp_path):
        assert mp3(tmp_path, "Arca - Mutant (2015)").parsed_filename == (
            "Arca",
            "Mutant (2015)",
        )

    def test_parenthetical_in_artist(self, tmp_path):
        assert mp3(tmp_path, "Various Artists (VA) - Some Track").parsed_filename == (
            "Various Artists (VA)",
            "Some Track",
        )
