"""Locate and load the Personal API key without ever echoing it."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

log = logging.getLogger(__name__)

KEY_VAR = "GARMIN_PERSONAL_API_KEY"
BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"


class ConfigError(RuntimeError):
    """Raised when the key cannot be loaded. Messages never contain the key."""


def home_dir() -> Path:
    return Path(os.environ.get("GARMIN_MCP_HOME", "~/.garmin-mcp")).expanduser()


def env_file() -> Path:
    return home_dir() / ".env"


def _warn_if_open(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        log.warning("%s is readable by other users (mode %o); run: chmod 600 %s", path, mode, path)


def load_api_key(path: Path | None = None) -> str:
    """Read GARMIN_PERSONAL_API_KEY from the .env file (the process env wins if set)."""
    from_env = os.environ.get(KEY_VAR, "").strip()
    if from_env:
        return from_env
    path = path or env_file()
    if not path.exists():
        raise ConfigError(f"Key file {path} not found. Create it with a line {KEY_VAR}=<your key>.")
    _warn_if_open(path)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip().removeprefix("export ").strip() == KEY_VAR:
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    raise ConfigError(f"{KEY_VAR} is empty in {path}. Open the file and paste your Personal API key after the '='.")
