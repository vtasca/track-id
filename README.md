# track-id
[![Package Validation](https://github.com/vtasca/track-id/actions/workflows/package-validation.yml/badge.svg)](https://github.com/vtasca/track-id/actions/workflows/package-validation.yml) [![Publish PyPI](https://github.com/vtasca/track-id/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/vtasca/track-id/actions/workflows/publish-pypi.yml) [![PyPI version](https://img.shields.io/pypi/v/track-id.svg)](https://pypi.org/project/track-id/) [![Downloads](https://static.pepy.tech/badge/track-id)](https://pepy.tech/project/track-id) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/vtasca/track-id/blob/main/LICENSE)

A Python CLI tool for music metadata enrichment, search, and download. Searches and downloads tracks from Soulseek, displays MP3 file info, and enriches MP3 files with metadata from Bandcamp, MusicBrainz, and Discogs.

## Features

- **Download**: Search Soulseek for a track — or a whole wishlist via `--from` — and download the best match, with automatic metadata enrichment
- **Search**: Search for tracks across Bandcamp, MusicBrainz, and Discogs
- **Info**: Display detailed information about an MP3 file including all ID3 tags
- **Enrich**: Automatically populate the metadata of an MP3 file — or a whole directory — (artist, album, genre, label, styles, track number, artwork, etc.) from Bandcamp, MusicBrainz, and Discogs
- **Rename**: Rename files from their tags using a template like `{artist} - {title}`
- **Doctor**: Scan a library for fake audio files, low bitrates, and missing tags or artwork
- **Analyze**: Deep-inspect one file — real container format, bitrate mode, encoder, tag completeness

## Installation

### Using uv

Install from PyPI as a tool:
```bash
uv tool install track-id
track-id --version
track-id search "Chaos In The CBD"
```

### Using pip

Install from PyPI with pip:
```bash
pip install track-id
track-id --version
track-id search "Chaos In The CBD"
track-id info "path/to/your/file.mp3"
track-id enrich "path/to/your/file.mp3"
```

### Clone and install locally

Mainly for development purposes:
```bash
# Clone the repository
git clone https://github.com/vtasca/track-id
cd track-id

# Install dependencies
uv sync
```

## Usage

### Download a track from Soulseek

Searches the Soulseek network, ranks candidates by bitrate and filename match, downloads the best result, and automatically enriches the file with metadata from Bandcamp, MusicBrainz, and Discogs:

```bash
track-id download "Aphex Twin - Windowlicker"
track-id download "Burial - Archangel" --output-dir ~/Music
track-id download "DJ Krush - Ha Doh" --min-bitrate 320 --timeout 20

# Batch: one 'Artist - Title' query per line (# comments and blanks are skipped),
# all downloaded over a single Soulseek connection
track-id download --from tracks.txt
```

Files are saved to `downloads/` by default. Credentials are required — set them once:

```bash
# Option 1: .env file in the project root (copy from .env.example)
cp .env.example .env  # then fill in your username and password

# Option 2: environment variables
export SOULSEEK_USERNAME=your_username
export SOULSEEK_PASSWORD=your_password

# Option 3: ~/.config/track-id/config.toml
# [soulseek]
# username = "your_username"
# password = "your_password"
```

A free Soulseek account can be created at [slsknet.org](https://www.slsknet.org/news/node/1).

Available options:

| Flag | Default | Description |
|---|---|---|
| `--from` | — | Text file of queries to download in one batch |
| `--output-dir` / `-o` | `downloads/` | Directory to save the file |
| `--min-bitrate` | `192` | Minimum acceptable bitrate in kbps |
| `--timeout` / `-T` | `10.0` | Seconds to collect search results |
| `--attempts` | `5` | Max download attempts before giving up |
| `--no-enrich` | — | Skip metadata enrichment after download |

### Search for tracks

Search across Bandcamp, MusicBrainz, and Discogs simultaneously:

```bash
track-id search "Chaos In The CBD"
track-id search "Burial - Archangel" --top 5
```

The `--top` / `-t` flag controls how many results are shown per source (default: 3).

### Display MP3 file information

```bash
track-id info "path/to/your/file.mp3"
```

### Enrich MP3 files with metadata

Queries Bandcamp, MusicBrainz, and Discogs for a matching track and writes the retrieved metadata directly into the file's ID3 tags:

```bash
track-id enrich "path/to/your/file.mp3"

# A whole directory (recursive), with a per-file ledger and summary
track-id enrich ~/Music/incoming/

# Preview without writing, or overwrite fields that already have values
track-id enrich "file.mp3" --dry-run
track-id enrich "file.mp3" --force
```

Each file must have either existing `Artist` and `Title` ID3 tags, or an `Artist - Title` filename so the tool knows what to search for. All three sources are tried and their results merged — existing tags are never overwritten unless `--force` is passed.

Tags populated across sources include: `Title`, `Artist`, `Album Artist`, `Album`, `Year`, `Track Number`, `Genre`, `Publisher/Label`, `Style` (Discogs community tags), `Artwork`, and a `Discogs URL` reference.

### Rename files from their tags

```bash
track-id rename "file.mp3"                                # '{artist} - {title}'
track-id rename ~/Music --template "{year} {artist} - {title}" --dry-run
```

Available template fields: `{artist}` `{title}` `{album}` `{year}` `{genre}` `{track}`. Files with missing tag values or name collisions are skipped, never clobbered.

### Check library health

```bash
track-id doctor ~/Music --min-bitrate 256
```

Recursively flags files that aren't real audio (e.g. an HTML error page saved as `.mp3`), fall below the bitrate threshold, or lack core tags or artwork.

### Analyze a single file

```bash
track-id analyze "file.mp3"
```

Reports the true container format (from magic bytes, not the extension), bitrate and CBR/VBR mode, sample rate, encoder, all tags, and any problems found.

## Development

### Setting up the development environment

```bash
uv sync --dev
```

### Running tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=track_id --cov-report=term-missing

# Run a specific file
uv run pytest tests/test_data_sources.py -v
```

## Project Structure

```
track-id/
├── track_id/
│   ├── track_id.py           # CLI commands (Typer app)
│   ├── unified_api.py        # Orchestrates search/enrich across all sources
│   ├── data_sources.py       # Abstract base class + registry
│   ├── bandcamp_api.py       # Bandcamp data source
│   ├── musicbrainz_api.py    # MusicBrainz data source
│   ├── discogs_api.py        # Discogs data source
│   ├── enrichment_handlers.py# Shared enrichment logic
│   ├── analysis.py           # File inspection — format sniffing, stream/tag checks
│   ├── soulseek_downloader.py# Soulseek download via aioslsk
│   ├── config.py             # Credential loading (.env / env vars / config file)
│   ├── mp3_utils.py          # MP3File class — ID3 read/write, filename parsing
│   ├── display.py            # Rich console output
│   ├── id3_tags.py           # Canonical ID3 tag name mapping
│   └── __init__.py
├── tests/
│   ├── conftest.py
│   ├── test_data_sources.py
│   ├── test_bandcamp_api.py
│   ├── test_musicbrainz_api.py
│   ├── test_discogs_api.py
│   ├── test_soulseek_downloader.py
│   ├── test_config.py
│   ├── test_artwork.py
│   ├── test_id3_tags.py
│   ├── test_track_id.py
│   └── test_integration.py
├── .env.example              # Credential template
├── pyproject.toml
└── README.md
```

## Contributing

1. Write tests for new features
2. Ensure all tests pass
3. Follow the existing code style
4. Update documentation as needed
