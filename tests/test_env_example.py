from pathlib import Path
from typing import Final

import pytest
from pydantic import ValidationError

from leagueasymode.config import APPLICATION_SETTINGS_FILE, ENV_FILE, Settings

ENV_EXAMPLE: Final = ENV_FILE.with_name(".env.example")
PREFIX: Final = "LEAGUEASYMODE_"


def example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text().splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#") or "=" not in stripped_line:
            continue
        variable_name, _, variable_value = stripped_line.partition("=")
        values[variable_name] = variable_value
    return values


def test_settings_use_the_documented_prefix() -> None:
    assert Settings.model_config.get("env_prefix") == PREFIX


def test_env_example_lists_every_setting_with_its_default() -> None:
    values = example_values()
    for field_name, field in Settings.model_fields.items():
        variable_name = f"{PREFIX}{field_name.upper()}"
        assert variable_name in values, f"{variable_name} is missing from .env.example"
        if not field.is_required():
            expected_value = "" if field.default is None else str(field.default)
            assert values[variable_name] == expected_value, (
                f"{variable_name} is {values[variable_name]!r} in .env.example "
                f"but the code's default is {expected_value!r}"
            )


def test_env_example_names_no_setting_the_code_does_not_have() -> None:
    known_variable_names = {f"{PREFIX}{field_name.upper()}" for field_name in Settings.model_fields}
    unknown_variable_names = {
        variable_name
        for variable_name in example_values()
        if variable_name.startswith(PREFIX) and variable_name not in known_variable_names
    }
    assert not unknown_variable_names, f"unknown settings in .env.example: {unknown_variable_names}"


def test_the_env_file_may_hold_the_names_of_other_layers(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{PREFIX}ENVIRONMENT=staging\nGEMINI_API_KEY=another-layers-key\n")
    assert Settings(_env_file=env_file).environment == "staging"


def test_a_misspelled_setting_in_the_env_file_is_an_error(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{PREFIX}LOG_LEVLE=DEBUG\n")
    with pytest.raises(ValidationError, match="log_levle"):
        Settings(_env_file=env_file)


def test_an_empty_key_in_the_env_file_counts_as_not_set(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{PREFIX}MODEL_API_KEY=\n")
    assert Settings(_env_file=env_file).model_api_key is None


def test_the_model_key_comes_from_the_env_file_and_is_never_printed(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{PREFIX}MODEL_API_KEY=not-a-real-key\n")
    settings = Settings(_env_file=env_file)
    assert settings.model_api_key is not None
    assert settings.model_api_key.get_secret_value() == "not-a-real-key"
    assert "not-a-real-key" not in repr(settings)


def test_an_installed_app_reads_its_own_settings_and_a_clone_its_env() -> None:
    # The repository's `.env` comes last, so it wins where both exist.
    assert Settings.model_config.get("env_file") == (APPLICATION_SETTINGS_FILE, ENV_FILE)
    assert APPLICATION_SETTINGS_FILE.name == "settings.env"


def test_the_apps_settings_file_is_read(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.env"
    settings_file.write_text("LEAGUEASYMODE_RECORD_WHILE_RUNNING=false\n")
    assert not Settings(_env_file=(settings_file, tmp_path / "missing.env")).record_while_running


def test_no_test_writes_to_the_players_own_files() -> None:
    settings = Settings()
    for file_path in (
        settings.accuracy_history,
        settings.last_game_summary,
        settings.model_weights,
        settings.preferences,
    ):
        assert file_path is not None
        assert "application" in file_path.parts
