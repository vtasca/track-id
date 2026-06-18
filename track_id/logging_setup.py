"""Centralized logging configuration.

Routes high-fidelity diagnostic logs (including aioslsk's chatty P2P
connection warnings) to a rotating log file instead of the terminal.

Attaching a handler to the root logger here is what keeps the terminal
clean: without any configured handler, Python falls back to its
"last resort" handler, which prints WARNING+ records straight to stderr.
That is the source of the noisy `aioslsk` output during downloads.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "track-id" / "logs"
LOG_FILE = LOG_DIR / "track-id.log"

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_MAX_BYTES = 1_000_000  # ~1 MB per file
_BACKUP_COUNT = 3


def configure_logging(level: int = logging.INFO) -> Path:
    """Send diagnostic logs to a rotating file and keep them off the terminal.

    Idempotent: calling more than once will not attach duplicate handlers.
    Returns the path to the active log file.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    already_configured = any(
        isinstance(h, RotatingFileHandler)
        and getattr(h, "baseFilename", None) == str(LOG_FILE)
        for h in root.handlers
    )
    if not already_configured:
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler.setLevel(level)
        root.addHandler(handler)

    # aioslsk emits a flood of DEBUG/INFO protocol chatter; keep only its
    # WARNING+ records (e.g. the normal "failed to fulfill ConnectToPeer"
    # peer churn) so the file stays useful for diagnostics.
    logging.getLogger("aioslsk").setLevel(logging.WARNING)

    return LOG_FILE
