"""Settings, read from the environment and from the `.env` file at the repository root."""

import sys
from pathlib import Path
from typing import Final

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from leagueasymode.data_dragon import DEFAULT_DATA_DRAGON_BASE_URL
from leagueasymode.game_api import DEFAULT_GAME_API_BASE_URL

# This file is <repository root>/src/leagueasymode/config.py.
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
ENV_FILE: Final = REPOSITORY_ROOT / ".env"
APPLICATION_NAME: Final = "LeagueasyMode"


def default_application_directory() -> Path:
    """Return where the application keeps its files.

    Returns:
        `~/Library/Application Support/LeagueasyMode` on a Mac, and
        `~/.local/share/leagueasymode` elsewhere.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APPLICATION_NAME
    return Path.home() / ".local" / "share" / APPLICATION_NAME.lower()


def default_recordings_directory() -> Path:
    """Return where recordings are kept when no setting says otherwise.

    Returns:
        `recordings` in the application's directory (`default_application_directory`).
    """
    return default_application_directory() / "recordings"


def default_patch_data_directory() -> Path:
    """Return where each patch's Data Dragon files are kept when no setting says otherwise.

    Returns:
        `patch-data` in the application's directory (`default_application_directory`).
    """
    return default_application_directory() / "patch-data"


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
    # A stand-in for the League client, such as a replay's address; empty to find the running one.
    league_client_base_url: str | None = None
    # League's game settings file (`game.cfg`), for where its minimap is, when League is installed
    # somewhere other than the default.
    league_game_config: Path | None = None
    # The overlay's local web server; 0 picks a free port, which `leagueasymode run` prints.
    overlay_port: int = 0
    # Whether `leagueasymode run` also records every game it shows.
    record_while_running: bool = True
    # The pause after each question to the League client about a player, to stay gentle on the
    # client and on Riot: each player is asked about twice per game, one request at a time.
    player_lookup_pause_seconds: float = 0.25
    # Whether the engine may fetch a patch's champion and item stats from Riot's Data Dragon, once
    # a patch, the one request it makes beyond this machine; off, only patches on disk are used.
    download_patch_stats: bool = True
    # Data Dragon's address, or a stand-in's.
    data_dragon_base_url: str = DEFAULT_DATA_DRAGON_BASE_URL
    # Where each patch's Data Dragon files are kept; empty for the default
    # (`default_patch_data_directory`).
    patch_data_directory: Path | None = None
    # The model provider's key, for anything that calls the real model. An empty line in `.env`
    # leaves it unset. To change provider, change this value and the model id; no other place holds
    # a key.
    model_api_key: SecretStr | None = None
