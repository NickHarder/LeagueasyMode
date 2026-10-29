"""Moments about friends (phase 11.6): exact facts, once per game per friend and threshold."""

import dataclasses
import hashlib
import json
import re
import string
from typing import Final

import pytest
from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    PlayerSeed,
    all_game_data,
    baron_kill_event,
    champion_kill_event,
    dragon_kill_event,
    game_start_event,
)
from leagueasymode.engine import compute_overlay_state
from leagueasymode.friends import FriendsList
from leagueasymode.game_state import GameSnapshot
from leagueasymode.overlay_state import PlayerCard
from leagueasymode.roast.moments import Moment, MomentLines, MomentTracker, load_moment_lines
from leagueasymode.roast.rules import MomentRules
from leagueasymode.roast.safety import floor_problems

AHRI_PLAYER: Final = "Ahri"
ZED_PLAYER: Final = "Shadow Step"
VI_PLAYER: Final = "Gank Plz"
GAREN_PLAYER: Final = "Garen Main"
# The moments' lines the owner approved on 2026-10-28. A change to any line changes this; the new
# line goes to the owner before the fingerprint does.
APPROVED_MOMENT_LINES_SHA256: Final = (
    "07f44664ee474c40440e4f4b87adfeef3b2483e20eb0a8fa8c233afbede032ad"
)
SLOTS: Final = frozenset(
    {"friend", "opponent", "count", "kills", "seconds", "creep", "clock", "monster"}
)


def seeds_with_creep(ahri_creep: int, zed_creep: int) -> tuple[PlayerSeed, ...]:
    return tuple(
        dataclasses.replace(seed, creep_score=ahri_creep)
        if seed.champion_name == "Ahri"
        else dataclasses.replace(seed, creep_score=zed_creep)
        if seed.champion_name == "Zed"
        else seed
        for seed in DEFAULT_PLAYERS
    )


def answer(
    game_time_seconds: float,
    events: list[dict[str, JsonValue]],
    players: tuple[PlayerSeed, ...] = DEFAULT_PLAYERS,
) -> tuple[GameSnapshot, list[PlayerCard]]:
    """The game's answer at a time, and the cards for it with Ahri, the player here, a friend."""
    payload = all_game_data(game_time_seconds, [game_start_event(), *events], players=players)
    friends = FriendsList(riot_ids=("Ahri#NA1",))
    cards = compute_overlay_state(payload, friend_riot_ids=friends.riot_id_keys).players
    return GameSnapshot.model_validate(payload), cards


def moments_of(
    game_time_seconds: float,
    events: list[dict[str, JsonValue]],
    players: tuple[PlayerSeed, ...] = DEFAULT_PLAYERS,
) -> list[Moment]:
    tracker = MomentTracker(MomentRules())
    tracker.update(*answer(game_time_seconds, events, players))
    return list(tracker.moments)


def test_dying_alone_to_the_lane_opponent_a_second_and_third_time() -> None:
    kills = [
        champion_kill_event(1, 100.0, VI_PLAYER, GAREN_PLAYER, []),
        champion_kill_event(2, 200.0, ZED_PLAYER, AHRI_PLAYER, []),
        champion_kill_event(3, 300.0, ZED_PLAYER, AHRI_PLAYER, [VI_PLAYER]),
        champion_kill_event(4, 400.0, ZED_PLAYER, AHRI_PLAYER, []),
    ]
    assert [moment.text for moment in moments_of(450.0, kills) if moment.kind == "solo_death"] == [
        "Ahri has died to Zed alone 2 times now. Lane diff, live."
    ]
    third = [*kills, champion_kill_event(5, 500.0, ZED_PLAYER, AHRI_PLAYER, [])]
    solo_texts = [moment.text for moment in moments_of(550.0, third) if moment.kind == "solo_death"]
    assert solo_texts[-1] == "Ahri has died to Zed alone 3 times now. Lane diff, live."
    assert len(solo_texts) == 2


def test_dying_just_before_the_enemy_takes_a_dragon_or_baron() -> None:
    events = [
        champion_kill_event(1, 100.0, ZED_PLAYER, AHRI_PLAYER, [VI_PLAYER]),
        dragon_kill_event(2, 140.0, VI_PLAYER),
        champion_kill_event(3, 1500.0, VI_PLAYER, AHRI_PLAYER, []),
        baron_kill_event(4, 1590.0, VI_PLAYER),
        champion_kill_event(5, 1700.0, VI_PLAYER, AHRI_PLAYER, []),
        dragon_kill_event(6, 1720.0, VI_PLAYER, dragon_type="Elder"),
    ]
    texts = [
        moment.text
        for moment in moments_of(1800.0, events)
        if moment.kind == "death_before_objective"
    ]
    # Baron came 90 seconds after the death: too late to count.
    assert texts == [
        "Ahri died 40 seconds before their dragon. Very generous.",
        "Ahri died 20 seconds before their Elder Dragon. Very generous.",
    ]


def test_a_monster_our_team_takes_is_no_moment() -> None:
    events = [
        champion_kill_event(1, 100.0, ZED_PLAYER, AHRI_PLAYER, []),
        dragon_kill_event(2, 130.0, GAREN_PLAYER),
    ]
    assert not [
        moment for moment in moments_of(200.0, events) if moment.kind == "death_before_objective"
    ]


def test_giving_up_first_blood() -> None:
    events = [champion_kill_event(1, 161.0, VI_PLAYER, AHRI_PLAYER, [ZED_PLAYER])]
    assert [moment.text for moment in moments_of(200.0, events)] == [
        "Ahri gave up first blood at 2:41. Setting the tone."
    ]
    someone_else_first = [
        champion_kill_event(1, 100.0, VI_PLAYER, GAREN_PLAYER, []),
        champion_kill_event(2, 161.0, VI_PLAYER, AHRI_PLAYER, []),
    ]
    assert not [
        moment for moment in moments_of(200.0, someone_else_first) if moment.kind == "first_blood"
    ]


def test_creep_score_behind_at_ten_and_fourteen_minutes() -> None:
    at_ten = moments_of(605.0, [], seeds_with_creep(ahri_creep=50, zed_creep=80))
    assert [moment.text for moment in at_ten] == [
        "Ahri is at least 30 CS behind Zed at 10:00. The minions are winning."
    ]
    # 29 behind at 14:00 is under that minute's threshold of 30.
    assert moments_of(845.0, [], seeds_with_creep(ahri_creep=90, zed_creep=119)) == []
    # Read only just after the minute: an answer at 11:00 checks nothing.
    assert moments_of(660.0, [], seeds_with_creep(ahri_creep=50, zed_creep=80)) == []


def test_the_lane_opponents_kills_while_the_friend_has_none() -> None:
    kills = [
        champion_kill_event(index, 100.0 * index, ZED_PLAYER, AHRI_PLAYER, [VI_PLAYER])
        for index in (1, 2, 3)
    ]
    streak = [
        moment.text for moment in moments_of(400.0, kills) if moment.kind == "opponent_streak"
    ]
    assert streak == ["Zed has killed Ahri 3 times, and Ahri has no kills. Lane diff."]
    with_a_reply = [*kills[:2], champion_kill_event(9, 250.0, AHRI_PLAYER, VI_PLAYER, []), kills[2]]
    assert not [
        moment for moment in moments_of(400.0, with_a_reply) if moment.kind == "opponent_streak"
    ]


def test_no_lane_moment_when_a_role_is_only_a_guess() -> None:
    snapshot, cards = answer(
        450.0,
        [
            champion_kill_event(index, 100.0 * index, ZED_PLAYER, AHRI_PLAYER, [])
            for index in (1, 2, 3)
        ],
    )
    guessed = [
        card.model_copy(update={"role_confidence": "guess"})
        if card.champion_name == "Zed"
        else card
        for card in cards
    ]
    tracker = MomentTracker(MomentRules())
    tracker.update(snapshot, guessed)
    # First blood needs no opponent; the lane moments do.
    assert [moment.kind for moment in tracker.moments] == ["first_blood"]


def test_no_moments_without_friends() -> None:
    payload = all_game_data(450.0, [champion_kill_event(1, 100.0, ZED_PLAYER, AHRI_PLAYER, [])])
    cards = compute_overlay_state(payload).players
    tracker = MomentTracker(MomentRules())
    assert tracker.update(GameSnapshot.model_validate(payload), cards) == []


def test_each_moment_is_made_once_and_a_new_game_starts_over() -> None:
    tracker = MomentTracker(MomentRules())
    events = [champion_kill_event(1, 161.0, VI_PLAYER, AHRI_PLAYER, [])]
    assert len(tracker.update(*answer(170.0, events))) == 1
    assert tracker.update(*answer(171.0, events)) == []
    assert len(tracker.moments) == 1
    # The clock went back: another game.
    assert (
        len(
            tracker.update(
                *answer(165.0 - 60.0, [champion_kill_event(1, 100.0, VI_PLAYER, AHRI_PLAYER, [])])
            )
        )
        == 1
    )
    tracker.update(None, [])
    assert not tracker.moments


def test_a_moment_shows_for_a_few_seconds_from_when_it_is_noticed() -> None:
    tracker = MomentTracker(MomentRules(shown_seconds=8.0))
    tracker.update(*answer(170.0, [champion_kill_event(1, 161.0, VI_PLAYER, AHRI_PLAYER, [])]))
    (callout,) = tracker.callouts(171.0)
    assert callout.kind == "moment"
    assert callout.shown_until_game_time_seconds == 178.0
    assert tracker.callouts(178.0) == []
    assert tracker.callouts(None) == []


def test_a_moment_noticed_long_after_is_kept_to_copy_but_not_shown() -> None:
    # As when the engine starts in the middle of a game.
    tracker = MomentTracker(MomentRules())
    tracker.update(*answer(1200.0, [champion_kill_event(1, 161.0, VI_PLAYER, AHRI_PLAYER, [])]))
    assert [moment.kind for moment in tracker.moments] == ["first_blood"]
    assert tracker.callouts(1201.0) == []


@pytest.mark.parametrize("kind", list(MomentLines.model_fields))
def test_each_line_uses_known_slots_and_holds_the_floor(kind: str) -> None:
    line = getattr(load_moment_lines(), kind)
    slots = {field for _, field, _, _ in string.Formatter().parse(line) if field}
    assert slots <= SLOTS
    assert floor_problems(line) == []
    # Every number comes from a slot.
    assert not re.search(r"\d", re.sub(r"\{\w+\}", "", line).replace("CS", ""))


def test_the_moment_lines_are_the_ones_the_owner_approved() -> None:
    canonical = json.dumps(load_moment_lines().model_dump(), sort_keys=True, ensure_ascii=False)
    assert hashlib.sha256(canonical.encode()).hexdigest() == APPROVED_MOMENT_LINES_SHA256
