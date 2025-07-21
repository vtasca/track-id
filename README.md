# track-id

A nifty Python CLI tool for searching tracks on Bandcamp and displaying MP3 file information.

## Features

- **Search**: Search for tracks on Bandcamp using their API
- **Info**: Display detailed information about MP3 files including metadata

## Installation

### Using uv

The easiest way to get started is by installing `track-id` as a tool:
```bash
uv tool install git+https://github.com/vtasca/track-id
track-id search "Chaos In The CBD"
track-id info "path/to/your/file.mp3"
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

### Search for tracks on Bandcamp

```bash
track-id search "Chaos In The CBD"
```

### Display MP3 file information

```bash
track-id info "path/to/your/file.mp3"
```

## Development

### Setting up the development environment

```bash
# Install development dependencies
uv sync --dev
```

### Running tests

```bash
# Install development dependencies (if not already installed)
uv sync --dev

# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage
uv run pytest --cov=track_id --cov=id3_tags --cov-report=term-missing

# Run specific test files
uv run pytest tests/test_id3_tags.py -v

# Run specific test classes
uv run pytest tests/test_track_id.py::TestTrackIdCLI -v

# Run specific test methods
uv run pytest tests/test_track_id.py::TestTrackIdCLI::test_search_command_exists -v
```

### Test Structure

The test suite is organized as follows:

- `tests/test_id3_tags.py`: Tests for the ID3 tag mapping functionality
- `tests/test_track_id.py`: Tests for the main CLI application
- `tests/test_integration.py`: Integration tests for complete workflows
- `tests/conftest.py`: Shared fixtures and test configuration

### Test Categories

- **Unit Tests**: Test individual functions and components in isolation
- **Integration Tests**: Test complete workflows and interactions between components
- **CLI Tests**: Test the command-line interface using Typer's testing utilities

### Running specific test types

```bash
# Run only unit tests
uv run pytest -m unit

# Run only integration tests
uv run pytest -m integration

# Run tests excluding slow ones
uv run pytest -m "not slow"
```

## Project Structure

```
track-id/
├── track_id/            # Main package
│   ├── __init__.py      # Package initialization
│   ├── track_id.py      # Main CLI application
│   └── id3_tags.py      # ID3 tag mapping definitions
├── tests/               # Test suite
│   ├── __init__.py
│   ├── conftest.py      # Shared fixtures
│   ├── test_id3_tags.py # ID3 tag tests
│   ├── test_track_id.py # Main application tests
│   └── test_integration.py # Integration tests
├── pyproject.toml       # Project configuration
└── README.md           # This file
```

## Contributing

1. Write tests for new features
2. Ensure all tests pass
3. Follow the existing code style
4. Update documentation as needed
