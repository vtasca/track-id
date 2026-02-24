# AGENTS.md

## Cursor Cloud specific instructions

This is a Python CLI tool (`track-id`) for MP3 metadata enrichment. It uses `uv` for dependency management and requires Python 3.9+.

### Quick reference

| Task | Command |
|---|---|
| Install deps | `uv sync` |
| Run app | `uv run track-id` |
| Run tests | `uv run pytest` |
| Type check | `uv run mypy track_id/` |

See `README.md` for full usage and test examples.

### Non-obvious notes

- The `.python-version` file pins Python 3.9. `uv` manages this automatically via `uv python install 3.9` (done at setup time). If the venv is missing or corrupted, `uv sync` will recreate it.
- `pyproject.toml` uses the deprecated `tool.uv.dev-dependencies` field. This produces a harmless warning on every `uv` command; it does not affect functionality.
- All tests use mocks for HTTP calls — no network access or API keys are needed to run the test suite.
- The `info` and `enrich` commands require a local MP3 file path. The `search` command works without any files (e.g. `uv run track-id search "artist name"`).
- No Docker, databases, or background services are needed.
