# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Track-ID** is a Python CLI tool for music metadata enrichment and search. It searches tracks across multiple music data sources (Bandcamp, MusicBrainz), displays MP3 file info, and enriches MP3 files with metadata from external music databases.

## Commands

```bash
# Install dependencies
uv sync

# Run the CLI
uv run track-id search "Artist - Title"
uv run track-id info path/to/file.mp3
uv run track-id enrich path/to/file.mp3

# Run tests
uv run pytest
uv run pytest tests/test_bandcamp_api.py -v   # single file
uv run pytest -m unit                          # unit tests only
uv run pytest -m integration                   # integration tests only
uv run pytest -m "not slow"                    # exclude slow tests
uv run pytest --cov=track_id --cov-report=term-missing

# Type checking
mypy track_id/
```

## Architecture

### Data Source Plugin System

New music sources are added by subclassing `DataSource` in `data_sources.py` and registering with `DataSourceRegistry`. Each source must implement:
- `search(search_text)` — call external API, return raw response
- `find_matching_track(search_results, artist, title)` — select best match
- `extract_metadata(track_data)` — normalize to ID3 tag dict
- `enrich_mp3_file(file_path)` — orchestrates enrichment end-to-end

`unified_api.py` initializes all sources and aggregates results across them.

### Data Flow

```
CLI (track_id.py)
  → unified_api.py        # aggregates across sources
    → DataSourceRegistry  # dispatches to each source
      → BandcampDataSource / MusicBrainzDataSource
    → MP3File (mp3_utils.py)  # reads/writes ID3 tags via mutagen
  → display.py            # Rich console output
```

### Key Files

| File | Role |
|------|------|
| `track_id/track_id.py` | CLI commands (Typer app) |
| `track_id/unified_api.py` | Orchestrates search/enrich across all sources |
| `track_id/data_sources.py` | Abstract base class + registry |
| `track_id/mp3_utils.py` | `MP3File` class — ID3 read/write, filename parsing |
| `track_id/display.py` | All Rich console output |
| `track_id/enrichment_handlers.py` | Shared logic reused by concrete data sources |

### MP3File

`MP3File` in `mp3_utils.py` is the core data object. It wraps mutagen for ID3 tag access, parses `Artist - Title` filenames, caches metadata, and handles artwork download. Pass it between layers rather than raw file paths wherever possible.

### ID3 Tags

`id3_tags.py` holds the canonical mapping of tag names used across the project. When adding new metadata fields, update this file first.
