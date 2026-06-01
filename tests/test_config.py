"""Unit tests for credential config loading."""

from pathlib import Path
from unittest.mock import patch

import pytest

from track_id.config import SoulseekConfig, load_soulseek_config

# Patch load_dotenv so the repo's .env file doesn't bleed into tests that
# need to exercise the missing-credentials code paths.
_no_dotenv = patch("track_id.config.load_dotenv")


class TestLoadSoulseekConfig:
    def test_loads_from_explicit_args(self):
        cfg = load_soulseek_config(username="user1", password="pass1")
        assert cfg == SoulseekConfig(username="user1", password="pass1")

    def test_loads_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("SOULSEEK_USERNAME", "envuser")
        monkeypatch.setenv("SOULSEEK_PASSWORD", "envpass")
        cfg = load_soulseek_config()
        assert cfg.username == "envuser"
        assert cfg.password == "envpass"

    def test_args_override_env(self, monkeypatch):
        monkeypatch.setenv("SOULSEEK_USERNAME", "envuser")
        monkeypatch.setenv("SOULSEEK_PASSWORD", "envpass")
        cfg = load_soulseek_config(username="arguser", password="argpass")
        assert cfg.username == "arguser"
        assert cfg.password == "argpass"

    @_no_dotenv
    def test_raises_when_both_missing(self, _mock, monkeypatch):
        monkeypatch.delenv("SOULSEEK_USERNAME", raising=False)
        monkeypatch.delenv("SOULSEEK_PASSWORD", raising=False)
        with pytest.raises(ValueError, match="username"):
            load_soulseek_config(config_file=Path("/nonexistent/config.toml"))

    @_no_dotenv
    def test_error_message_names_missing_fields(self, _mock, monkeypatch):
        monkeypatch.setenv("SOULSEEK_USERNAME", "user")
        monkeypatch.delenv("SOULSEEK_PASSWORD", raising=False)
        with pytest.raises(ValueError, match="password"):
            load_soulseek_config(config_file=Path("/nonexistent/config.toml"))

    @_no_dotenv
    def test_loads_from_toml_config_file(self, _mock, monkeypatch, tmp_path):
        monkeypatch.delenv("SOULSEEK_USERNAME", raising=False)
        monkeypatch.delenv("SOULSEEK_PASSWORD", raising=False)
        config_file = tmp_path / "config.toml"
        config_file.write_text('[soulseek]\nusername = "fileuser"\npassword = "filepass"\n')
        cfg = load_soulseek_config(config_file=config_file)
        assert cfg.username == "fileuser"
        assert cfg.password == "filepass"

    def test_args_override_config_file(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[soulseek]\nusername = "fileuser"\npassword = "filepass"\n')
        cfg = load_soulseek_config(username="arguser", password="argpass", config_file=config_file)
        assert cfg.username == "arguser"
        assert cfg.password == "argpass"

    @_no_dotenv
    def test_env_overrides_config_file(self, _mock, monkeypatch, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[soulseek]\nusername = "fileuser"\npassword = "filepass"\n')
        monkeypatch.setenv("SOULSEEK_USERNAME", "envuser")
        monkeypatch.delenv("SOULSEEK_PASSWORD", raising=False)
        cfg = load_soulseek_config(config_file=config_file)
        assert cfg.username == "envuser"
        assert cfg.password == "filepass"

    @_no_dotenv
    def test_missing_config_file_falls_through_to_error(self, _mock, monkeypatch):
        monkeypatch.delenv("SOULSEEK_USERNAME", raising=False)
        monkeypatch.delenv("SOULSEEK_PASSWORD", raising=False)
        with pytest.raises(ValueError):
            load_soulseek_config(config_file=Path("/does/not/exist.toml"))
