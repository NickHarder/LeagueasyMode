"""Team calls (phase 11.9): calm calls for the team, at most one a minute, naming no one."""

import hashlib
import json
import re
import string
from collections.abc import Mapping
from typing import Final

import pytest
from pydantic import JsonValue

from game_payloads import all_game_data, champion_kill_event, game_start_event
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.overlay_state import (
    DragonTimer,
    ObjectiveTimer,
    OverlayState,
    TeamGold,
    WinChance,
)
from leagueasymode.roast.rules import TeamCallRules
from leagueasymode.roast.safety import floor_problems
from leagueasymode.roast.team_calls import TeamCallLines, TeamCallTracker, load_team_call_lines

NOW: Final = 1000.0
# The team calls' lines the owner approved on 2026-10-28. A change to any line changes this; the
# new line goes to the owner before the fingerprint does.
APPROVED_TEAM_CALL_LINES_SHA256: Final = (
    "4d84fec861aa87e2be56aca56abe5befd8636ef5635ff85d57a8c16c973f70a0"
)
SLOTS: Final = frozenset({"monster", "clock", "count", "seconds", "target", "next", "gold"})
BOT_GAP: Final = "Bot Gap"


def dragon_at(spawns_at: float, status: str = "not_spawned") -> DragonTimer:
    return DragonTimer.model_validate(
        {
            "objective": "dragon",
            "status": status,
            "spawns_at_game_time_seconds": spawns_at,
            "ally_dragon_count": 0,
            "enemy_dragon_count": 0,
            "soul_type": None,
            "soul_holder": None,
        }
    )


def state_at(
    now: float = NOW,
    events: list[dict[str, JsonValue]] | None = None,
    *,
    dead: dict[str, float] | None = None,
    updates: Mapping[str, object] | None = None,
) -> tuple[OverlayState, GameSnapshot]:
    """A state at a time, with these champions dead until these times, and these fields set."""
    payload = all_game_data(now, [game_start_event(), *(events or [])])
    state = compute_overlay_state(payload)
    dead_until = dead or {}
    cards = [
        card.model_copy(
            update={
                "is_dead": card.champion_name in dead_until,
                "respawns_at_game_time_seconds": dead_until.get(card.champion_name),
            }
        )
        for card in state.players
    ]
    quiet: dict[str, object] = {
        "dragon": None,
        "objectives": [],
        "team_gold": None,
        "win_chance": None,
    }
    changed = state.model_copy(update={**quiet, "players": cards, **(updates or {})})
    return changed, GameSnapshot.model_validate(payload)


def first_call_text(state_and_snapshot: tuple[OverlayState, GameSnapshot]) -> str | None:
    call = TeamCallTracker(TeamCallRules()).update(*state_and_snapshot)
    return call.text if call is not None else None


def test_an_objective_spawning_soon() -> None:
    soon = state_at(updates={"dragon": dragon_at(NOW + 85.0)})
    assert first_call_text(soon) == (
        "Dragon in 1:25. Let's not die, ward around it and start moving."
    )
    assert first_call_text(state_at(updates={"dragon": dragon_at(NOW + 50.0)})) is None
    off_the_rift = state_at(updates={"dragon": dragon_at(NOW + 85.0), "is_summoners_rift": False})
    assert first_call_text(off_the_rift) is None


def test_enemies_down_long_enough_while_we_are_up() -> None:
    dead = {"Zed": NOW + 25.4, "Vi": NOW + 30.0, "Lux": NOW + 41.0}
    assert first_call_text(state_at(dead=dead)) == (
        "3 of theirs are down for 25s. Let's take a tower now."
    )
    baron_up = ObjectiveTimer(
        objective="baron", status="alive", spawns_at_game_time_seconds=None, is_rule_verified=True
    )
    with_baron = state_at(dead=dead, updates={"objectives": [baron_up]})
    assert first_call_text(with_baron) == "3 of theirs are down for 25s. Let's take Baron now."
    # Two of them about to be back is no window.
    assert first_call_text(state_at(dead={"Zed": NOW + 25.0, "Vi": NOW + 10.0})) is None


def test_a_fight_lost_sends_the_team_to_the_next_objective() -> None:
    dead = {"Garen": NOW + 30.0, "Ahri": NOW + 30.0, "Jinx": NOW + 30.0, "Zed": NOW + 20.0}
    lost = state_at(dead=dead, updates={"dragon": dragon_at(1120.0)})
    assert first_call_text(lost) == "Reset and buy. Next up is Dragon at 18:40, let's group for it."
    traded = state_at(dead={**dead, "Vi": NOW + 20.0, "Lux": NOW + 20.0})
    assert first_call_text(traded) is None


def test_a_teammates_death_streak_names_no_one() -> None:
    deaths = [
        champion_kill_event(index, NOW - 200 + 60 * index, "Headshot", BOT_GAP, [])
        for index in (1, 2, 3)
    ]
    tracker = TeamCallTracker(TeamCallRules())
    call = tracker.update(*state_at(events=deaths))
    assert call is not None
    assert call.text == "We're fine. Next up is the next objective, let's play for that."
    assert BOT_GAP.lower() not in call.call_id.lower()
    assert "Jinx" not in call.text
    # Deaths spread over more than four minutes are no streak.
    spread = [
        champion_kill_event(index, NOW - 400 + 150 * index, "Headshot", BOT_GAP, [])
        for index in (0, 1, 2)
    ]
    assert first_call_text(state_at(events=spread)) is None


def test_behind_in_gold_but_still_winnable() -> None:
    gold = TeamGold(ally_total_gold=20_000, enemy_total_gold=22_600, lead_band_gold=800)
    winnable = state_at(
        updates={"team_gold": gold, "win_chance": WinChance(ally_chance=0.41, reasons=[])}
    )
    assert first_call_text(winnable) == (
        "About 2.5k gold down, but this is winnable. Let's play safe and fight on our terms."
    )
    lost_cause = state_at(
        updates={"team_gold": gold, "win_chance": WinChance(ally_chance=0.2, reasons=[])}
    )
    assert first_call_text(lost_cause) is None


def test_at_most_one_call_a_minute() -> None:
    tracker = TeamCallTracker(TeamCallRules())
    gold = TeamGold(ally_total_gold=20_000, enemy_total_gold=23_000, lead_band_gold=800)
    winnable = {"team_gold": gold, "win_chance": WinChance(ally_chance=0.4, reasons=[])}
    both = state_at(updates={"dragon": dragon_at(NOW + 80.0), **winnable})
    first = tracker.update(*both)
    assert first is not None
    assert first.kind == "objective_soon"
    assert tracker.update(*state_at(NOW + 30.0, updates=winnable)) is None
    later = tracker.update(*state_at(NOW + 61.0, updates=winnable))
    assert later is not None
    assert later.kind == "behind_but_winnable"


def test_off_the_rift_no_call_speaks_of_buying_or_objectives() -> None:
    # The owner, 2026-10-29, in ARAM: "i am getting stuff like reset for obj even in aram". ARAM
    # has no recall and no epic monsters; a window to push holds anywhere.
    off_the_rift: dict[str, object] = {"is_summoners_rift": False}
    lost = {"Garen": NOW + 30.0, "Ahri": NOW + 30.0, "Jinx": NOW + 30.0, "Zed": NOW + 20.0}
    assert first_call_text(state_at(dead=lost, updates=off_the_rift)) is None
    deaths = [
        champion_kill_event(index, NOW - 200 + 60 * index, "Headshot", BOT_GAP, [])
        for index in (1, 2, 3)
    ]
    assert first_call_text(state_at(events=deaths, updates=off_the_rift)) is None
    enemies_down = {"Zed": NOW + 25.4, "Vi": NOW + 30.0, "Lux": NOW + 41.0}
    assert first_call_text(state_at(dead=enemies_down, updates=off_the_rift)) == (
        "3 of theirs are down for 25s. Let's take a tower now."
    )


def test_no_call_while_a_fight_is_on() -> None:
    # As with the callouts: a death in the last 8 seconds is a fight still on, and the call waits
    # for it to end, so a fight does not bring a call at each death.
    dead = {"Zed": NOW + 25.4, "Vi": NOW + 30.0, "Lux": NOW + 41.0}
    just_now = [champion_kill_event(1, NOW - 3.0, "Headshot", "Lux", [])]
    assert first_call_text(state_at(events=just_now, dead=dead)) is None
    a_while_ago = [champion_kill_event(1, NOW - 9.0, "Headshot", "Lux", [])]
    assert first_call_text(state_at(events=a_while_ago, dead=dead)) == (
        "3 of theirs are down for 25s. Let's take a tower now."
    )


def test_the_numbers_window_callout_says_what_enemies_down_would() -> None:
    # One line a fight: with the numbers window shown, the same news as a team call stays off the
    # overlay; ⌃⌥C still copies it.
    tracker = TeamCallTracker(TeamCallRules())
    tracker.update(*state_at(dead={"Zed": NOW + 25.4, "Vi": NOW + 30.0, "Lux": NOW + 41.0}))
    assert tracker.callouts(NOW + 1.0, is_numbers_window_shown=True) == []
    (callout,) = tracker.callouts(NOW + 1.0)
    assert callout.text == "3 of theirs are down for 25s. Let's take a tower now."
    assert [call.kind for call in tracker.calls] == ["enemies_down"]


def test_a_call_shows_for_a_few_seconds_as_a_callout() -> None:
    tracker = TeamCallTracker(TeamCallRules(shown_seconds=8.0))
    tracker.update(*state_at(updates={"dragon": dragon_at(NOW + 85.0)}))
    (callout,) = tracker.callouts(NOW + 1.0)
    assert callout.kind == "team_call"
    assert callout.shown_until_game_time_seconds == NOW + 8.0
    assert tracker.callouts(NOW + 8.0) == []


def test_no_game_forgets_the_calls() -> None:
    tracker = TeamCallTracker(TeamCallRules())
    tracker.update(*state_at(updates={"dragon": dragon_at(NOW + 85.0)}))
    assert tracker.calls
    tracker.update(OverlayState(is_game_running=False), None)
    assert not tracker.calls


@pytest.mark.parametrize("kind", list(TeamCallLines.model_fields))
def test_each_line_uses_known_slots_and_holds_the_floor(kind: str) -> None:
    line = getattr(load_team_call_lines(), kind)
    slots = {field for _, field, _, _ in string.Formatter().parse(line) if field}
    assert slots <= SLOTS
    assert floor_problems(line) == []
    # Every number comes from a slot.
    assert not re.search(r"\d", re.sub(r"\{\w+\}", "", line))


def test_the_team_call_lines_are_the_ones_the_owner_approved() -> None:
    canonical = json.dumps(load_team_call_lines().model_dump(), sort_keys=True, ensure_ascii=False)
    assert hashlib.sha256(canonical.encode()).hexdigest() == APPROVED_TEAM_CALL_LINES_SHA256
