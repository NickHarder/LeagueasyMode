"""Settings, read from the environment and from the `.env` file at the repository root."""

from pathlib import Path
from typing import Final

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# This file is <repository root>/src/leagueasymode/config.py.
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
ENV_FILE: Final = REPOSITORY_ROOT / ".env"


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
    # The model provider's key, for anything that calls the real model. An empty line in `.env`
    # leaves it unset. To change provider, change this value and the model id; no other place holds
    # a key.
    model_api_key: SecretStr | None = None
