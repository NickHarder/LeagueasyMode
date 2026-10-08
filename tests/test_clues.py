import dataclasses
from typing import Final, TypedDict

from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    all_game_data,
    baron_kill_event,
    champion_kill_event,
    dragon_kill_event,
    game_start_event,
    herald_kill_event,
    inhibitor_killed_event,
    turret_killed_event,
)
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.clues import ClueTracker
from leagueasymode.inference.gold import PlayerKey
from leagueasymode.overlay_state import BackEstimate, PositionClue

AHRI: Final = ("ORDER", "ahri")
DARIUS: Final = ("CHAOS", "darius")
VI_JUNGLER: Final = ("CHAOS", "vi")
ZED: Final = ("CHAOS", "zed")


class SeedChanges(TypedDict, total=False):
    creep_score: int
    is_dead: bool
    respawn_timer_seconds: float


def observe(
    tracker: ClueTracker,
    game_time_seconds: float,
    events: list[dict[str, JsonValue]] | None = None,
    last_backs: dict[PlayerKey, BackEstimate] | None = None,
    **changes_by_champion: SeedChanges,
) -> dict[PlayerKey, list[PositionClue]]:
    players = tuple(
        dataclasses.replace(seed, **changes_by_champion.get(seed.champion_name, {}))
        for seed in DEFAULT_PLAYERS
    )
    snapshot = GameSnapshot.model_validate(
        all_game_data(game_time_seconds, events=events, players=players)
    )
    return tracker.update(snapshot, last_backs or {})


def latest(clues: dict[PlayerKey, list[PositionClue]], key: PlayerKey) -> PositionClue:
    return clues[key][-1]


def test_a_turret_taken_puts_the_champions_credited_with_it_there() -> None:
    turret = turret_killed_event(1, 600.0, "Turret_T1_L_03_A", "Top Dog", ["Gank Plz"])
    clues = observe(ClueTracker(), 610.0, [game_start_event(), turret])
    assert latest(clues, DARIUS) == PositionClue(
        kind="turret",
        game_time_seconds=600.0,
        place="at the top outer turret",
        point_name="order_top_outer_turret",
        region="top_lane",
    )
    assert latest(clues, VI_JUNGLER).point_name == "order_top_outer_turret"
    assert ZED not in clues


def test_an_inhibitor_taken_puts_its_takers_at_it() -> None:
    inhibitor = inhibitor_killed_event(1, 1500.0, "Barracks_T2_C1", "Ahri")
    clue = latest(observe(ClueTracker(), 1510.0, [game_start_event(), inhibitor]), AHRI)
    assert (clue.kind, clue.point_name, clue.place) == (
        "turret",
        "chaos_mid_inhibitor",
        "at the mid inhibitor",
    )


def test_epic_monsters_put_their_takers_at_their_pit() -> None:
    events = [
        game_start_event(),
        dragon_kill_event(1, 400.0, "Gank Plz"),
        herald_kill_event(2, 960.0, "Shadow Step"),
        baron_kill_event(3, 1300.0, "Top Dog"),
    ]
    clues = observe(ClueTracker(), 1310.0, events)
    assert (latest(clues, VI_JUNGLER).point_name, latest(clues, VI_JUNGLER).place) == (
        "dragon_pit",
        "at Dragon",
    )
    assert (latest(clues, ZED).point_name, latest(clues, ZED).place) == ("baron_pit", "at Herald")
    assert (latest(clues, DARIUS).point_name, latest(clues, DARIUS).place) == (
        "baron_pit",
        "at Baron",
    )


def test_a_champion_a_turret_kills_was_at_that_turret() -> None:
    executed = champion_kill_event(1, 700.0, "Turret_T2_C_05_A", "Ahri", [])
    clue = latest(observe(ClueTracker(), 710.0, [game_start_event(), executed]), AHRI)
    assert (clue.point_name, clue.region) == ("chaos_mid_outer_turret", "mid_lane")


def test_a_respawn_puts_them_in_base() -> None:
    tracker = ClueTracker()
    observe(tracker, 400.0, Zed={"is_dead": True, "respawn_timer_seconds": 20.0})
    clue = latest(observe(tracker, 420.0), ZED)
    assert (clue.kind, clue.game_time_seconds, clue.point_name, clue.place) == (
        "fountain",
        420.0,
        "chaos_fountain",
        "in base",
    )


def test_a_trip_to_base_puts_them_in_base_when_they_shopped() -> None:
    back = BackEstimate(shopped_at_game_time_seconds=455.0, returns_at_game_time_seconds=480.0)
    clue = latest(observe(ClueTracker(), 460.0, last_backs={ZED: back}), ZED)
    assert (clue.kind, clue.game_time_seconds, clue.point_name) == (
        "fountain",
        455.0,
        "chaos_fountain",
    )


def test_creep_score_rising_puts_a_laner_in_their_lane() -> None:
    tracker = ClueTracker()
    observe(tracker, 490.0, Zed={"creep_score": 10})
    clue = latest(observe(tracker, 500.0, Zed={"creep_score": 20}), ZED)
    assert (clue.kind, clue.game_time_seconds, clue.region, clue.place) == (
        "lane",
        500.0,
        "mid_lane",
        "in the mid lane",
    )


def test_a_junglers_creep_score_puts_them_in_the_jungle() -> None:
    tracker = ClueTracker()
    observe(tracker, 490.0, Vi={"creep_score": 10})
    clue = latest(observe(tracker, 500.0, Vi={"creep_score": 14}), VI_JUNGLER)
    assert (clue.kind, clue.point_name, clue.region, clue.place) == (
        "jungle",
        None,
        "chaos_jungle",
        "in the jungle",
    )


def test_clues_come_in_time_order() -> None:
    tracker = ClueTracker()
    observe(tracker, 490.0, Zed={"creep_score": 10})
    turret = turret_killed_event(1, 495.0, "Turret_T1_C_05_A", "Shadow Step")
    clues = observe(tracker, 500.0, [game_start_event(), turret], Zed={"creep_score": 20})
    assert [clue.kind for clue in clues[ZED]] == ["turret", "lane"]


def test_a_new_game_starts_the_tracker_over() -> None:
    tracker = ClueTracker()
    observe(tracker, 490.0, Zed={"creep_score": 10})
    observe(tracker, 500.0, Zed={"creep_score": 20})
    assert ZED not in observe(tracker, 10.0)


def test_the_overlay_shows_each_players_latest_clue() -> None:
    tracker = ClueTracker()
    turret = turret_killed_event(1, 600.0, "Turret_T1_L_03_A", "Top Dog")
    state = compute_overlay_state(
        all_game_data(610.0, events=[game_start_event(), turret]), clue_tracker=tracker
    )
    darius = next(card for card in state.players if card.champion_name == "Darius")
    assert darius.last_clue is not None
    assert darius.last_clue.place == "at the top outer turret"
