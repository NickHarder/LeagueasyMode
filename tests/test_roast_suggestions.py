"""The overlay's roast card after a game: three lines, each about a different target."""

from pathlib import Path

from client_game_payloads import (
    details_payload,
    end_of_game_payload,
    summary_payload,
    timeline_payload,
)
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH
from leagueasymode.roast.end_of_game import quick_game_roast
from leagueasymode.roast.last_game import LastGameRoast, last_game_roast
from leagueasymode.roast.rules import LaneRules, RoastRules
from leagueasymode.roast.suggestions import SUGGESTION_COUNT, roast_suggestions
from leagueasymode.scoring import read_recorded_game
from recorded_games import players_at, write_scored_recording


def full_case(tmp_path: Path) -> LastGameRoast:
    recording = write_scored_recording(
        tmp_path,
        players_at(are_positions_given=True),
        timeline=timeline_payload(),
        details=details_payload(),
        client_answers={CHAMPION_SUMMARY_PATH: summary_payload()},
    )
    game = read_recorded_game(recording)
    roast = last_game_roast(
        game.client_resources, game.minute_snapshots[-1], lane_rules=LaneRules()
    )
    assert roast is not None
    return roast


def test_three_lines_the_teams_closing_line_first(tmp_path: Path) -> None:
    rules = RoastRules()
    suggestions = roast_suggestions(full_case(tmp_path), 2, rules)
    assert len(suggestions.lines) == SUGGESTION_COUNT
    assert len(set(suggestions.lines)) == SUGGESTION_COUNT
    assert all(len(line) <= rules.chat_line_max_characters for line in suggestions.lines)
    assert all(line.startswith("gg. ") for line in suggestions.lines)
    assert not suggestions.is_quick


def test_the_spice_changes_the_lines(tmp_path: Path) -> None:
    last_game = full_case(tmp_path)
    assert (
        roast_suggestions(last_game, 1, RoastRules()).lines
        != roast_suggestions(last_game, 4, RoastRules()).lines
    )


def test_a_quick_case_with_no_lanes_still_offers_lines() -> None:
    quick = quick_game_roast(end_of_game_payload())
    assert quick is not None
    suggestions = roast_suggestions(quick, 2, RoastRules())
    assert suggestions.is_quick
    assert 1 <= len(suggestions.lines) <= SUGGESTION_COUNT
    assert len(set(suggestions.lines)) == len(suggestions.lines)
    # "NO LANE VERDICT" is no ruling, so chat does not hear it.
    assert all(line.startswith("gg. Our ") for line in suggestions.lines)
