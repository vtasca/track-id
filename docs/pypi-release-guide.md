# PyPI release guide for `track-id`

This guide documents the release path that is now wired into this repository.

## One-time setup

1. Create and verify accounts:
   - https://pypi.org
   - https://test.pypi.org
2. In both PyPI and TestPyPI, configure a **Trusted Publisher** for this repo:
   - Owner: `vtasca`
   - Repository: `track-id`
   - Workflow file: `publish-pypi.yml`
   - Environment: leave empty unless you add environment protection rules
3. Ensure you have permission to create GitHub releases in this repository.

## What this repository now includes

- Package metadata in `pyproject.toml` ready for PyPI.
- CI package check workflow: `.github/workflows/package-check.yml`.
- Publish workflow: `.github/workflows/publish-pypi.yml`.

## Release checklist (every release)

1. Update the version in `pyproject.toml` under `[project].version`.
2. Commit and push the version change.
3. Wait for package checks to pass in GitHub Actions.
4. Publish to **TestPyPI** (recommended dry run):
   - Run the `Publish Python package` workflow manually.
   - Choose input `repository = testpypi`.
5. Verify install from TestPyPI:
   - `python -m venv /tmp/track-id-test && source /tmp/track-id-test/bin/activate`
   - `pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ track-id==<version>`
   - `track-id --version`
6. Publish to **PyPI**:
   - Preferred: create a GitHub Release (for example `v0.1.4`), which triggers publish to PyPI.
   - Alternative: run workflow dispatch with `repository = pypi`.
7. Verify public install:
   - `python -m venv /tmp/track-id-prod && source /tmp/track-id-prod/bin/activate`
   - `pip install track-id==<version>`
   - `track-id --version`

## Local preflight commands

Run these before making a release:

1. `uv sync --dev`
2. `uv run pytest`
3. `rm -rf dist`
4. `uv build`
5. `uvx twine check dist/*`

If `twine check` passes and tests are green, the artifact is usually safe to publish.
