# track-id
[![Package Validation](https://github.com/vtasca/track-id/actions/workflows/package-validation.yml/badge.svg)](https://github.com/vtasca/track-id/actions/workflows/package-validation.yml) [![Publish PyPI](https://github.com/vtasca/track-id/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/vtasca/track-id/actions/workflows/publish-pypi.yml) [![PyPI version](https://img.shields.io/pypi/v/track-id.svg)](https://pypi.org/project/track-id/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/vtasca/track-id/blob/main/LICENSE)

A Python CLI tool for music metadata enrichment and search. Searches tracks across Bandcamp, MusicBrainz, and Discogs, displays MP3 file info, and enriches MP3 files with metadata from external music databases.

## Features

- **Search**: Search for tracks across Bandcamp, MusicBrainz, and Discogs
- **Info**: Display detailed information about an MP3 file including all ID3 tags
- **Enrich**: Automatically populate an MP3 file's metadata (artist, album, genre, label, styles, track number, artwork, etc.) from Bandcamp, MusicBrainz, and Discogs

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

### Enrich an MP3 file with metadata

Queries Bandcamp, MusicBrainz, and Discogs for a matching track and writes the retrieved metadata directly into the file's ID3 tags:

```bash
track-id enrich "path/to/your/file.mp3"
```

The file must have either existing `Artist` and `Title` ID3 tags, or an `Artist - Title` filename so the tool knows what to search for. All three sources are tried and their results merged — existing tags are never overwritten.

Tags populated across sources include: `Title`, `Artist`, `Album Artist`, `Album`, `Year`, `Track Number`, `Genre`, `Publisher/Label`, `Style` (Discogs community tags), `Artwork`, and a `Discogs URL` reference.

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
│   ├── test_artwork.py
│   ├── test_id3_tags.py
│   ├── test_track_id.py
│   └── test_integration.py
├── pyproject.toml
└── README.md
```

## Contributing

1. Write tests for new features
2. Ensure all tests pass
3. Follow the existing code style
4. Update documentation as needed
