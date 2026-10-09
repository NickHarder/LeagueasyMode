"""What every test shares: no test reads or writes the player's own files in their home folder."""

from pathlib import Path
from typing import Final

import pytest

# The settings that name a file in the application's directory, which a test that runs the engine,
# records a game or scores one would otherwise read or write.
APPLICATION_FILE_SETTINGS: Final = {
    "LEAGUEASYMODE_ACCURACY_HISTORY": "accuracy-history.jsonl",
    "LEAGUEASYMODE_LAST_GAME_SUMMARY": "last-game.json",
    "LEAGUEASYMODE_MODEL_WEIGHTS": "model-weights.json",
    "LEAGUEASYMODE_PREFERENCES": "preferences.json",
}


@pytest.fixture(autouse=True)
def application_files_in_the_tests_own_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point each of the application's files at the test's temporary folder.

    A test that names a file itself, through its settings or its environment, still wins.
    """
    application_directory = tmp_path / "application"
    for variable_name, file_name in APPLICATION_FILE_SETTINGS.items():
        monkeypatch.setenv(variable_name, str(application_directory / file_name))
