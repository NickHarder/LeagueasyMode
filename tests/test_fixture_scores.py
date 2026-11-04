"""The real games' scores stay what they were when reading a recording was made faster.

Reading a recorded game took some 7 to 17 seconds a fixture (and some 50 for a whole game), most
of it spent copying each answer whole, working the roles out again for every answer, and finding a
feed name's player by searching the scoreboard. Those were cut without changing what is worked
out: `expected-scores.json` holds what `main` scored on each fixture before the change (at
562fe9d), and every estimator must score the same, to the last digit.
"""

import json
from pathlib import Path
from typing import Final

import pytest

from leagueasymode.scoring import read_recorded_game, score_game

RECORDINGS_DIRECTORY: Final = Path(__file__).parent / "fixtures" / "recorded-games"
EXPECTED_SCORES_PATH: Final = RECORDINGS_DIRECTORY / "expected-scores.json"
EXPECTED_SCORES: Final[dict[str, list[list[object]]]] = json.loads(EXPECTED_SCORES_PATH.read_text())


@pytest.mark.parametrize("recording_name", sorted(EXPECTED_SCORES))
def test_a_real_game_scores_what_it_did_before_reading_was_made_faster(
    recording_name: str,
) -> None:
    game = read_recorded_game(RECORDINGS_DIRECTORY / recording_name)
    scores = score_game(game, None)
    scored = [[score.estimator, score.sample_count, score.value, score.measure] for score in scores]
    assert scored == EXPECTED_SCORES[recording_name]


def test_every_fixture_has_its_expected_scores() -> None:
    fixture_names = {path.name for path in RECORDINGS_DIRECTORY.glob("*.jsonl.xz")}
    assert fixture_names == set(EXPECTED_SCORES)
