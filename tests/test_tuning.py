"""The hand-set thresholds in one file, `tuning.json`, that the owner edits."""

import json
from pathlib import Path

import pytest

from game_payloads import CHAMPION_IDS, all_game_data, puuid_of
from leagueasymode.cli import main
from leagueasymode.engine import compute_overlay_state
from leagueasymode.engine_status import StatusBoard
from leagueasymode.inference.callouts import CalloutRules
from leagueasymode.inference.intel import IntelRules
from leagueasymode.player_intel import GamePlayerRecord, PlayerRecord, recent_games_of
from leagueasymode.tuning import Tuning, changed_values, load_tuning, note_tuning, write_tuning
from test_player_intel import ZED, zed_history


def test_without_a_file_the_tuning_is_the_hand_set_values(tmp_path: Path) -> None:
    assert load_tuning(tmp_path / "tuning.json") == (Tuning(), None)


def test_a_file_changes_only_what_it_names(tmp_path: Path) -> None:
    tuning_path = tmp_path / "tuning.json"
    tuning_path.write_text(
        '{"callouts": {"habit_min_share": 0.8}, "intel": {"one_trick_min_games": 10}}'
    )
    tuning, problem = load_tuning(tuning_path)
    assert problem is None
    assert tuning.callouts.habit_min_share == 0.8
    assert tuning.intel.one_trick_min_games == 10
    assert tuning.callouts.shown_seconds == CalloutRules().shown_seconds
    assert changed_values(tuning) == ["callouts.habit_min_share", "intel.one_trick_min_games"]


@pytest.mark.parametrize(
    ("file_text", "problem"),
    [
        ('{"callouts": {"habit_min_shar": 0.8}}', "callouts.habit_min_shar: extra_forbidden"),
        ('{"callouts": {"habit_min_share": "high"}}', "callouts.habit_min_share: float_parsing"),
        ("not json", "the file: json_invalid"),
    ],
)
def test_a_misspelled_or_wrong_value_leaves_every_default_and_says_where(
    tmp_path: Path, file_text: str, problem: str
) -> None:
    tuning_path = tmp_path / "tuning.json"
    tuning_path.write_text(file_text)
    assert load_tuning(tuning_path) == (Tuning(), problem)


def test_the_written_file_holds_every_value_and_reads_back_the_same(tmp_path: Path) -> None:
    tuning_path = tmp_path / "tuning.json"
    write_tuning(tuning_path, Tuning())
    assert set(json.loads(tuning_path.read_text())) == {
        "callouts",
        "suggestions",
        "intel",
        "lookups",
        "jungle_path",
        "positions",
    }
    assert load_tuning(tuning_path) == (Tuning(), None)


def test_the_engine_shows_what_the_tuning_says() -> None:
    records = {
        ("CHAOS", "zed"): GamePlayerRecord(
            champion_id=CHAMPION_IDS["Zed"],
            record=PlayerRecord(
                ranked=None, recent_games=tuple(recent_games_of(zed_history(), puuid_of(ZED)))
            ),
        )
    }

    def is_zed_main(tuning: Tuning) -> bool:
        state = compute_overlay_state(all_game_data(600.0), player_records=records, tuning=tuning)
        zed = next(card for card in state.players if card.champion_name == "Zed")
        assert zed.intel is not None
        return zed.intel.is_main_champion

    # Three games on Zed make a main by default, not when a main needs four.
    assert is_zed_main(Tuning())
    assert not is_zed_main(Tuning(intel=IntelRules(main_champion_min_games=4)))


def test_the_status_page_says_what_the_tuning_changed(tmp_path: Path) -> None:
    board = StatusBoard(home_directory=tmp_path)
    tuning_path = tmp_path / "tuning.json"
    note_tuning(board, tuning_path, Tuning(), None)
    assert _part(board, "tuning") == ("ok", "Hand-set values; none changed in ~/tuning.json")
    note_tuning(board, tuning_path, Tuning(intel=IntelRules(main_champion_min_games=4)), None)
    assert _part(board, "tuning") == (
        "ok",
        "1 value changed in ~/tuning.json: intel.main_champion_min_games",
    )
    note_tuning(board, tuning_path, Tuning(), "callouts.habit_min_shar: extra_forbidden")
    assert _part(board, "tuning") == (
        "problem",
        "~/tuning.json could not be read (callouts.habit_min_shar: extra_forbidden); the "
        "hand-set values stand",
    )


def test_the_tuning_command_writes_every_value_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tuning_path = tmp_path / "tuning.json"
    monkeypatch.setenv("LEAGUEASYMODE_TUNING", str(tuning_path))
    assert main(["tuning"]) == 0
    assert json.loads(capsys.readouterr().out) == json.loads(Tuning().model_dump_json())
    assert main(["tuning", "--write"]) == 0
    assert load_tuning(tuning_path) == (Tuning(), None)
    # A file already there is the owner's: never written over.
    tuning_path.write_text('{"intel": {"one_trick_min_games": 10}}')
    assert main(["tuning", "--write"]) == 1
    assert tuning_path.read_text() == '{"intel": {"one_trick_min_games": 10}}'


def _part(board: StatusBoard, key: str) -> tuple[str, str]:
    part = next(part for part in board.report().parts if part.key == key)
    return part.state, part.detail
