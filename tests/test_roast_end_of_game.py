"""A quick case from the end-of-game stats (phase 11.7), before the timeline comes."""

import re
from pathlib import Path
from typing import Final

from pydantic import JsonValue

from client_game_payloads import CHAMPIONS, GAME_ID, MIDDLE_ID, end_of_game_payload
from data_dragon_fixtures import fixture_patch_stats
from game_payloads import GAME_ID as RECORDED_GAME_ID
from leagueasymode.cli import _keep_quick_roast, after_the_game
from leagueasymode.data_dragon import PatchStats
from leagueasymode.friends import FriendsList
from leagueasymode.roast.case import CaseOptions, build_case
from leagueasymode.roast.case_view import case_view
from leagueasymode.roast.end_of_game import quick_game_roast
from leagueasymode.roast.last_game import LastGameRoast, roast_path_beside
from leagueasymode.roast.rules import RoastRules
from recorded_games import game_timeline, players_at, write_scored_recording

PATH_STEP: Final = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def value_at(payload: JsonValue, path: str) -> JsonValue:
    found = payload
    for key, index in PATH_STEP.findall(path):
        if index:
            assert isinstance(found, list), path
            found = found[int(index)]
        else:
            assert isinstance(found, dict), path
            found = found[key]
    return found


async def no_patch_stats(_game_version: str | None) -> PatchStats | None:
    return fixture_patch_stats()


def test_the_stats_give_the_ten_players_and_the_player_here() -> None:
    roast = quick_game_roast(
        end_of_game_payload(), friend_riot_ids=FriendsList(riot_ids=("player 4#test",)).riot_id_keys
    )
    assert roast is not None
    assert roast.is_quick
    assert roast.defendant_participant_id == MIDDLE_ID
    players = roast.game.players
    assert [player.champion for player in players] == [name for _, name in CHAMPIONS.values()]
    assert [player.position for player in players[:5]] == [
        "TOP",
        "JUNGLE",
        "MIDDLE",
        "BOTTOM",
        "UTILITY",
    ]
    assert [player.won for player in players] == [False] * 5 + [True] * 5
    assert [player.participant_id for player in players if player.is_friend] == [4]


def test_every_cited_value_is_the_value_at_its_path() -> None:
    payload = end_of_game_payload()
    roast = quick_game_roast(payload)
    assert roast is not None
    cited = [exhibit for exhibit in roast.game.ledger.exhibits.values() if exhibit.source.path]
    assert len(cited) == 10 * 6 + 1
    for exhibit in cited:
        assert exhibit.source.path is not None
        assert value_at(payload, exhibit.source.path) == exhibit.value, exhibit.key
    assert roast.game.ledger.exhibits["kill_participation/p3"].value == (3 + 2) / 15
    assert roast.game.ledger.game_id == GAME_ID


def test_the_quick_case_rules_on_the_scoreboard_alone() -> None:
    roast = quick_game_roast(end_of_game_payload())
    assert roast is not None
    case = build_case(
        list(roast.game.players),
        roast.game.ledger,
        roast.defendant_participant_id,
        remade=False,
        options=CaseOptions(),
        rules=RoastRules(),
    )
    assert case.verdict.title == "NO LANE VERDICT"
    assert case.lines
    view = case_view(roast, CaseOptions(), RoastRules())
    assert view.is_quick
    assert view.board == ()


def test_without_names_teams_of_five_or_the_player_here_there_is_no_quick_case() -> None:
    assert quick_game_roast(end_of_game_payload(names_given=False)) is None
    names = dict(CHAMPIONS.values())
    named = quick_game_roast(end_of_game_payload(names_given=False), names_by_champion_id=names)
    assert named is not None
    assert quick_game_roast(end_of_game_payload(blue_players=4)) is None
    assert quick_game_roast(end_of_game_payload(local_puuid="someone else")) is None
    assert quick_game_roast(None) is None


def test_the_quick_case_is_kept_beside_the_summary(tmp_path: Path) -> None:
    summary_path = tmp_path / "last-game.json"
    _keep_quick_roast(end_of_game_payload(), summary_path, frozenset())
    kept = LastGameRoast.model_validate_json(roast_path_beside(summary_path).read_text())
    assert kept.is_quick
    # Nothing is kept from stats that give no quick case.
    other = tmp_path / "other.json"
    _keep_quick_roast(end_of_game_payload(blue_players=4), other, frozenset())
    assert not roast_path_beside(other).exists()


async def test_the_full_case_replaces_the_quick_one(tmp_path: Path) -> None:
    summary_path = tmp_path / "history" / "last-game.json"
    summary_path.parent.mkdir()
    _keep_quick_roast(end_of_game_payload(), summary_path, frozenset())
    recording = write_scored_recording(
        tmp_path, players_at(are_positions_given=True), timeline=game_timeline()
    )
    await after_the_game(
        recording,
        no_patch_stats,
        history_path=tmp_path / "history" / "accuracy-history.jsonl",
        summary_path=summary_path,
    )
    kept = LastGameRoast.model_validate_json(roast_path_beside(summary_path).read_text())
    assert not kept.is_quick


async def test_a_quick_case_stays_when_its_games_details_never_come(tmp_path: Path) -> None:
    summary_path = tmp_path / "history" / "last-game.json"
    summary_path.parent.mkdir()
    # The recorded game's details hold no players: no full case.
    recording = write_scored_recording(
        tmp_path,
        players_at(are_positions_given=True),
        timeline=game_timeline(),
        details={"gameId": RECORDED_GAME_ID, "participants": []},
    )
    quick = quick_game_roast(end_of_game_payload())
    assert quick is not None
    for game_id, should_stay in ((RECORDED_GAME_ID, True), (GAME_ID, False)):
        roast_path_beside(summary_path).write_text(
            quick.model_copy(
                update={
                    "game": quick.game.model_copy(
                        update={"ledger": quick.game.ledger.model_copy(update={"game_id": game_id})}
                    )
                }
            ).model_dump_json()
        )
        await after_the_game(
            recording,
            no_patch_stats,
            history_path=tmp_path / "history" / "accuracy-history.jsonl",
            summary_path=summary_path,
        )
        assert roast_path_beside(summary_path).exists() == should_stay
