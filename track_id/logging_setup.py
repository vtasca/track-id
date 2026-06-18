"""Centralized logging configuration.

Routes high-fidelity diagnostic logs (including aioslsk's chatty P2P
connection warnings) to a per-run log file instead of the terminal.

Each invocation writes to its own timestamped file under the log
directory, so a single run is easy to read in isolation without older
runs interleaved. Attaching a handler to the root logger here is also
what keeps the terminal clean: without any configured handler, Python
falls back to its "last resort" handler, which prints WARNING+ records
straight to stderr. That is the source of the noisy `aioslsk` output
during downloads.
"""

import logging
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "track-id" / "logs"

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_KEEP_RUNS = 20  # prune older per-run logs beyond this many


def configure_logging(level: int = logging.INFO) -> Path:
    """Send this run's diagnostic logs to a fresh timestamped file.

    Idempotent within a single run: calling more than once returns the
    same file and will not attach duplicate handlers. Returns the path to
    the active log file.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Reuse the handler already created for this process, if any.
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "_track_id_run", False):
            return Path(h.baseFilename)

    _prune_old_runs()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_file = LOG_DIR / f"track-id-{timestamp}.log"

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.setLevel(level)
    handler._track_id_run = True  # type: ignore[attr-defined]
    root.addHandler(handler)

    # aioslsk emits a flood of DEBUG/INFO protocol chatter; keep only its
    # WARNING+ records (e.g. the normal "failed to fulfill ConnectToPeer"
    # peer churn) so the file stays useful for diagnostics.
    logging.getLogger("aioslsk").setLevel(logging.WARNING)

    return log_file


def _prune_old_runs() -> None:
    """Keep only the most recent ``_KEEP_RUNS`` per-run log files."""
    runs = sorted(
        LOG_DIR.glob("track-id-*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in runs[_KEEP_RUNS:]:
        try:
            stale.unlink()
        except OSError:
            pass
