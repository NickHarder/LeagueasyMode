"""The reader of the client's game details and timeline (phase 11.2), on client-shaped payloads."""

import copy
import re
from typing import Final

from pydantic import JsonValue

from client_game_payloads import (
    GAME_ID,
    MIDDLE_ID,
    details_payload,
    summary_payload,
    timeline_payload,
)
from leagueasymode.roast.case import CaseOptions, build_case
from leagueasymode.roast.client_game import (
    ClientGame,
    champion_names,
    participant_id_of,
    read_client_game,
)
from leagueasymode.roast.rules import LaneRules, RoastRules

PATH_STEP: Final = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def read(
    details: JsonValue | None = None,
    timeline: JsonValue | None = None,
    *,
    with_timeline: bool = True,
    friends: frozenset[str] = frozenset(),
) -> ClientGame:
    return read_client_game(
        details if details is not None else details_payload(),
        (timeline if timeline is not None else timeline_payload()) if with_timeline else None,
        names_by_champion_id=champion_names(summary_payload()),
        friend_riot_ids=friends,
        lane_rules=LaneRules(),
    )


def value_at(payload: JsonValue, path: str) -> JsonValue:
    """Follow a path such as `participants[2].stats.kills` into a payload, as a reader would."""
    found = payload
    for key, index in PATH_STEP.findall(path):
        if index:
            assert isinstance(found, list), path
            found = found[int(index)]
        else:
            assert isinstance(found, dict), path
            found = found[key]
    return found


def test_every_cited_value_is_the_value_at_its_path() -> None:
    details = details_payload()
    timeline = timeline_payload()
    game = read(details, timeline)
    cited = [
        exhibit
        for exhibit in game.ledger.exhibits.values()
        if exhibit.source.kind in ("game", "timeline")
    ]
    assert len(cited) > 100
    for exhibit in cited:
        payload = details if exhibit.source.kind == "game" else timeline
        assert exhibit.source.path is not None
        assert value_at(payload, exhibit.source.path) == exhibit.value, exhibit.key


def test_every_computation_names_inputs_that_are_on_file() -> None:
    exhibits = read().ledger.exhibits
    computations = [
        exhibit for exhibit in exhibits.values() if exhibit.source.kind == "computation"
    ]
    assert computations
    for exhibit in computations:
        assert exhibit.source.formula, exhibit.key
        assert set(exhibit.source.input_keys) <= set(exhibits), exhibit.key


def test_players_come_from_lane_and_role_and_the_teams_result() -> None:
    game = read(details_payload(states_win=False))
    players = {player.participant_id: player for player in game.players}
    assert [players[participant_id].position for participant_id in range(1, 6)] == [
        "TOP",
        "JUNGLE",
        "MIDDLE",
        "BOTTOM",
        "UTILITY",
    ]
    assert players[MIDDLE_ID].champion == "Ahri"
    assert players[9].champion == "Kai'Sa"
    assert not players[MIDDLE_ID].won
    assert players[8].won


def test_a_team_position_wins_over_lane_and_role() -> None:
    game = read(details_payload(team_position_of_first="JUNGLE"))
    players = {player.participant_id: player for player in game.players}
    assert players[1].position == "JUNGLE"


def test_friends_are_matched_by_riot_id_in_any_case() -> None:
    players = read(friends=frozenset({"player 4#test"})).players
    assert [player.participant_id for player in players if player.is_friend] == [4]


def test_a_missing_field_gives_no_exhibit_and_no_share_for_its_team() -> None:
    details = details_payload(
        fields_missing_for_second=("visionScore", "totalDamageDealtToChampions")
    )
    exhibits = read(details).ledger.exhibits
    assert "vision_score/p2" not in exhibits
    assert "vision_score/p1" in exhibits
    assert "damage_share/p1" not in exhibits
    assert "damage_share/p6" in exhibits


def test_the_scoreboard_shares_add_up() -> None:
    exhibits = read().ledger.exhibits
    assert exhibits["team_kills/t100"].value == 1 + 2 + 3 + 4 + 5
    assert exhibits["kill_participation/p3"].value == (3 + 2) / 15
    assert exhibits["damage_share/p3"].value == 3000 / 15000


def test_lanes_are_judged_at_the_frame_nearest_fourteen_minutes() -> None:
    exhibits = read().ledger.exhibits
    assert exhibits["clock_14"].display == "14:00"
    assert exhibits["gold_diff_14/p3"].value == (500 + 14 * 300) - (500 + 14 * 400)
    assert exhibits["gold_behind_14/p3"].value == 1400
    assert "gold_ahead_14/p3" not in exhibits
    assert exhibits["lane_outcome_14/p3"].value == "lost"
    assert exhibits["cs_behind_14/p3"].value == 14
    assert exhibits["levels_behind_14/p3"].value == 1


def test_participant_frames_listed_rather_than_keyed_are_read_too() -> None:
    exhibits = read(timeline=timeline_payload(listed=True)).ledger.exhibits
    assert exhibits["gold_at_14/p3"].source.path == "frames[14].participantFrames[2].totalGold"


def test_a_solo_death_before_the_enemy_dragon_is_on_file() -> None:
    exhibits = read().ledger.exhibits
    assert exhibits["first_blood_clock/p3"].display == "6:05"
    assert exhibits["solo_deaths_to_opponent/p3"].value == 1
    assert exhibits["solo_death_1_clock/p3"].display == "6:05"
    assert exhibits["throw_objective/p3"].display == "dragon"
    assert exhibits["throw_seconds_before/p3"].value == 30
    assert exhibits["died_rich_gold/p3"].value == 1600
    assert exhibits["distinct_victims/p8"].value == 1


def test_a_losing_player_gets_the_carry_impossibility_index() -> None:
    exhibits = read().ledger.exhibits
    assert "carry_impossibility_index/p3" in exhibits
    assert "carry_impossibility_index/p8" not in exhibits


def test_without_a_timeline_there_are_no_lane_or_event_exhibits() -> None:
    exhibits = read(with_timeline=False).ledger.exhibits
    assert "kills/p3" in exhibits
    assert not [key for key in exhibits if key.startswith(("gold_", "clock_", "solo_death"))]


def test_a_surrender_is_on_file_and_a_remake_is_not_a_surrender() -> None:
    assert read().ledger.exhibits["surrender"].source.path == (
        "participants[0].stats.gameEndedInSurrender"
    )
    remade = read(details_payload(remade_by_fifth=True))
    assert remade.remade
    assert "surrender" not in remade.ledger.exhibits


def test_the_game_length_and_objectives_are_on_file() -> None:
    exhibits = read().ledger.exhibits
    assert exhibits["game_length"].display == "30:34"
    assert exhibits["dragons/t200"].source.path == "teams[1].dragonKills"
    assert "heralds/t100" not in exhibits


def test_champion_names_skip_the_empty_slot_and_unreadable_entries() -> None:
    names = champion_names([{"id": -1, "name": "None"}, {"id": 64}, {"id": 64, "name": "Lee Sin"}])
    assert names == {64: "Lee Sin"}
    assert champion_names(None) == {}
    assert champion_names({"not": "a list"}) == {}


def test_a_player_is_found_by_their_puuid() -> None:
    assert participant_id_of(details_payload(), "placeholder-puuid-7") == 7
    assert participant_id_of(details_payload(), "someone else") is None
    assert participant_id_of(None, "placeholder-puuid-7") is None


def test_an_unreadable_answer_gives_an_empty_game_not_an_error() -> None:
    game = read({"participants": "not a list"}, {"frames": 3})
    assert game.players == ()
    assert game.ledger.exhibits == {}
    assert not game.remade


def test_a_client_game_becomes_a_cited_case_about_anyone_in_it() -> None:
    game = read()
    for defendant_id in (MIDDLE_ID, 8):
        case = build_case(
            list(game.players),
            game.ledger,
            defendant_id,
            remade=game.remade,
            options=CaseOptions(),
            rules=RoastRules(),
        )
        assert case.game_id == GAME_ID
        assert case.lines
        cited = {lettered.exhibit.key for lettered in case.exhibits}
        for line in case.lines:
            assert set(line.exhibit_keys) <= cited, line.text


def test_reading_does_not_change_the_answers() -> None:
    details = details_payload()
    timeline = timeline_payload()
    details_before = copy.deepcopy(details)
    timeline_before = copy.deepcopy(timeline)
    read(details, timeline)
    assert details == details_before
    assert timeline == timeline_before
