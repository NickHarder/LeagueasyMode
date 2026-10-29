"""The last game's case as the post-game window shows it (phase 11.3)."""

import json
from pathlib import Path
from typing import Final

import pytest

from client_game_payloads import (
    GAME_ID,
    MIDDLE_ID,
    details_payload,
    summary_payload,
    timeline_payload,
)
from leagueasymode.roast.case import CaseOptions
from leagueasymode.roast.case_view import (
    RISK_WARNING,
    CaseView,
    case_options_of,
    case_view,
)
from leagueasymode.roast.client_game import champion_names, read_client_game
from leagueasymode.roast.last_game import LastGameRoast
from leagueasymode.roast.rules import LaneRules, RoastRules

SCHEMA_PATH: Final = Path(__file__).parents[1] / "overlay" / "web" / "roast_case.schema.json"
LEBLANC_ID: Final = 8


def last_game(defendant_id: int = MIDDLE_ID) -> LastGameRoast:
    return LastGameRoast(
        game=read_client_game(
            details_payload(),
            timeline_payload(),
            names_by_champion_id=champion_names(summary_payload()),
            lane_rules=LaneRules(),
        ),
        defendant_participant_id=defendant_id,
    )


def view_of(options: CaseOptions, defendant_id: int = MIDDLE_ID) -> CaseView:
    return case_view(last_game(defendant_id), options, RoastRules())


def test_the_defaults_are_the_whole_team_at_salty() -> None:
    assert case_options_of({}) == CaseOptions(target="team", spice=2, prove=False, take=0)


def test_the_query_sets_every_option() -> None:
    options = case_options_of({"target": "player:8", "spice": "4", "prove": "1", "take": "3"})
    assert options == CaseOptions(target="player:8", spice=4, prove=True, take=3)


@pytest.mark.parametrize(
    "query",
    [
        {"target": "player:11"},
        {"target": "lane:MID"},
        {"target": "everyone"},
        {"spice": "5"},
        {"spice": "0"},
        {"spice": "hot"},
        {"take": "-1"},
    ],
)
def test_a_query_outside_the_options_is_refused(query: dict[str, str]) -> None:
    with pytest.raises(ValueError, match=r"."):
        case_options_of(query)


def test_every_letter_a_line_cites_is_an_exhibit_of_the_case() -> None:
    view = view_of(CaseOptions())
    letters = {exhibit.letter for exhibit in view.exhibits}
    cited = {part.letter for line in view.lines for part in line.parts if part.letter}
    assert view.lines
    assert cited
    assert cited <= letters


def test_the_ten_players_are_offered_from_our_side() -> None:
    view = view_of(CaseOptions())
    assert len(view.players) == 10
    sides = {player.participant_id: player.side for player in view.players}
    assert [sides[participant_id] for participant_id in (1, 5, 6, 10)] == [
        "ally",
        "ally",
        "enemy",
        "enemy",
    ]
    assert [player.champion for player in view.players if player.is_defendant] == ["Ahri"]


def test_our_side_follows_the_player_on_this_machine() -> None:
    view = view_of(CaseOptions(), defendant_id=LEBLANC_ID)
    sides = {player.participant_id: player.side for player in view.players}
    assert sides[LEBLANC_ID] == "ally"
    assert sides[MIDDLE_ID] == "enemy"


def test_the_board_names_each_lanes_champions_with_the_gold_at_fourteen() -> None:
    board = {lane.position: lane for lane in view_of(CaseOptions()).board}
    middle = board["MIDDLE"]
    assert (middle.ally_champion, middle.enemy_champion) == ("Ahri", "LeBlanc")
    assert middle.outcome == "lost"
    assert middle.gold_difference == "-1,400"
    assert middle.cs_difference == "-14"
    assert middle.letter is not None


def test_one_enemy_can_be_the_target() -> None:
    view = view_of(CaseOptions(target="player:8", spice=3))
    named = [
        part.text for line in view.lines for part in line.parts if part.text in ("LeBlanc", "Ahri")
    ]
    assert view.target == "player:8"
    assert "LeBlanc" in named


def test_the_risk_warning_shows_at_tilted_and_above() -> None:
    assert [view_of(CaseOptions(spice=level)).risk_warning for level in (1, 2, 3, 4)] == [
        None,
        None,
        RISK_WARNING,
        RISK_WARNING,
    ]
    assert view_of(CaseOptions(spice=4)).spice_name == "Chat-Restricted Speedrun"


def test_the_closing_line_fits_the_chat_limit() -> None:
    for level in (1, 2, 3, 4):
        view = view_of(CaseOptions(spice=level))
        assert 0 < len(view.closing_line) <= view.closing_line_limit


def test_the_view_says_which_game_it_is() -> None:
    assert view_of(CaseOptions()).game_id == GAME_ID


def test_the_schema_file_is_current() -> None:
    # overlay/web/src/case_state.ts mirrors this schema. When the contract changes, run:
    # uv run python -m leagueasymode.roast.case_view > overlay/web/roast_case.schema.json
    assert json.loads(SCHEMA_PATH.read_text()) == CaseView.model_json_schema()
