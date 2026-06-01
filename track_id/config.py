"""Credential and configuration management for track-id."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

_CONFIG_FILE = Path.home() / ".config" / "track-id" / "config.toml"


@dataclass
class SoulseekConfig:
    username: str
    password: str


def load_soulseek_config(
    username: Optional[str] = None,
    password: Optional[str] = None,
    config_file: Path = _CONFIG_FILE,
) -> SoulseekConfig:
    """Load Soulseek credentials with priority: args > env vars > .env file > config file."""
    load_dotenv(override=False)  # populate os.environ from .env without overriding existing vars
    u = username or os.environ.get("SOULSEEK_USERNAME")
    p = password or os.environ.get("SOULSEEK_PASSWORD")

    if not (u and p) and config_file.exists() and tomllib is not None:
        with open(config_file, "rb") as f:
            data = tomllib.load(f)
        slsk = data.get("soulseek", {})
        u = u or slsk.get("username")
        p = p or slsk.get("password")

    if not u or not p:
        missing = []
        if not u:
            missing.append("username")
        if not p:
            missing.append("password")
        raise ValueError(
            f"Soulseek credentials missing ({', '.join(missing)}). "
            "Set SOULSEEK_USERNAME and SOULSEEK_PASSWORD environment variables, "
            f"or add them to {config_file}:\n\n"
            "  [soulseek]\n"
            '  username = "your_username"\n'
            '  password = "your_password"'
        )

    return SoulseekConfig(username=u, password=p)
