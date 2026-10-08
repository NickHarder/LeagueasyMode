"""Settings, read from the environment and from the `.env` file at the repository root."""

import sys
from pathlib import Path
from typing import Final

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from leagueasymode.game_api import DEFAULT_GAME_API_BASE_URL

# This file is <repository root>/src/leagueasymode/config.py.
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
ENV_FILE: Final = REPOSITORY_ROOT / ".env"
APPLICATION_NAME: Final = "LeagueasyMode"


def default_recordings_directory() -> Path:
    """Return where recordings are kept when no setting says otherwise.

    Returns:
        `~/Library/Application Support/LeagueasyMode/recordings` on a Mac, and
        `~/.local/share/leagueasymode/recordings` elsewhere.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APPLICATION_NAME / "recordings"
    return Path.home() / ".local" / "share" / APPLICATION_NAME.lower() / "recordings"


class Settings(BaseSettings):
    """The service's configuration.

    One `.env` at the repository root holds the keys and settings of every layer. This class reads
    the names that start with its prefix, whatever directory a command runs in, and leaves the other
    layers' names alone. A name with the prefix that is not a field is an error, so a misspelling
    cannot pass unnoticed. A real environment variable wins over the file.

    Every field is listed in `.env.example` with the default written here;
    `tests/test_env_example.py` fails when the two drift apart.
    """

    model_config = SettingsConfigDict(
        env_prefix="LEAGUEASYMODE_",
        env_file=ENV_FILE,
        dotenv_filtering="match_prefix",
        env_ignore_empty=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    environment: str = "development"
    log_level: str = "INFO"
    # How often the game's API is asked during a game.
    poll_interval_seconds: float = 0.5
    # The game's API. A replay (`leagueasymode replay`) serves plain HTTP on another port.
    game_api_base_url: str = DEFAULT_GAME_API_BASE_URL
    # Where recordings are kept; empty for the default (`default_recordings_directory`).
    recordings_directory: Path | None = None
    # The League client's lockfile, when League is installed somewhere other than the default.
    league_client_lockfile: Path | None = None
    # The model provider's key, for anything that calls the real model. An empty line in `.env`
    # leaves it unset. To change provider, change this value and the model id; no other place holds
    # a key.
    model_api_key: SecretStr | None = None
