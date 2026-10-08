import dataclasses
from typing import Final

from game_payloads import DEFAULT_PLAYERS, all_game_data
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.clues import ClueTracker
from leagueasymode.inference.gold import PlayerKey
from leagueasymode.inference.wards import WARD_SHOWN_SECONDS, WardTracker
from leagueasymode.overlay_state import PositionEstimate, RegionChance, WardEstimate

CONTROL_WARD: Final = (2055, "Control Ward", 75)
VI_JUNGLER: Final = ("CHAOS", "vi")
IN_THE_RIVER: Final = PositionEstimate(
    regions=[
        RegionChance(region="top_river", label="top river", chance=0.6),
        RegionChance(region="chaos_top_jungle", label="their top jungle", chance=0.3),
    ],
    away_chance=0.4,
    unseen_seconds=12.0,
    reach_top_seconds=10.0,
    reach_mid_seconds=8.0,
    reach_bot_seconds=30.0,
)


def snapshot_with_vi_wards(
    game_time_seconds: float, ward_count: int, *, is_dead: bool = False
) -> GameSnapshot:
    players = tuple(
        dataclasses.replace(seed, items=(CONTROL_WARD,) * ward_count, is_dead=is_dead)
        if seed.champion_name == "Vi"
        else seed
        for seed in DEFAULT_PLAYERS
    )
    return GameSnapshot.model_validate(all_game_data(game_time_seconds, players=players))


def locations(location: PositionEstimate = IN_THE_RIVER) -> dict[PlayerKey, PositionEstimate]:
    return {VI_JUNGLER: location}


def test_a_control_ward_leaving_the_inventory_was_placed_where_they_likely_were() -> None:
    tracker = WardTracker()
    assert tracker.update(snapshot_with_vi_wards(600.0, 2), locations()) == []
    wards = tracker.update(snapshot_with_vi_wards(601.0, 1), locations())
    assert wards == [
        WardEstimate(
            champion_name="Vi",
            side="enemy",
            placed_at_game_time_seconds=601.0,
            region="top_river",
            label="top river",
            chance=0.6,
        )
    ]


def test_a_new_ward_replaces_the_last_one_of_the_same_player() -> None:
    tracker = WardTracker()
    tracker.update(snapshot_with_vi_wards(600.0, 2), locations())
    tracker.update(snapshot_with_vi_wards(601.0, 1), locations())
    elsewhere = IN_THE_RIVER.model_copy(
        update={"regions": [RegionChance(region="bot_river", label="bot river", chance=0.5)]}
    )
    wards = tracker.update(snapshot_with_vi_wards(700.0, 0), locations(elsewhere))
    assert [(ward.label, ward.placed_at_game_time_seconds) for ward in wards] == [
        ("bot river", 700.0)
    ]


def test_a_ward_count_dropping_at_death_is_not_a_placement() -> None:
    tracker = WardTracker()
    tracker.update(snapshot_with_vi_wards(600.0, 1), locations())
    assert tracker.update(snapshot_with_vi_wards(601.0, 0, is_dead=True), locations()) == []


def test_a_ward_is_shown_for_five_minutes_at_most() -> None:
    tracker = WardTracker()
    tracker.update(snapshot_with_vi_wards(600.0, 1), locations())
    tracker.update(snapshot_with_vi_wards(601.0, 0), locations())
    assert tracker.update(snapshot_with_vi_wards(601.0 + WARD_SHOWN_SECONDS, 0), locations())
    assert tracker.update(snapshot_with_vi_wards(602.0 + WARD_SHOWN_SECONDS, 0), locations()) == []


def test_a_new_game_starts_the_tracker_over() -> None:
    tracker = WardTracker()
    tracker.update(snapshot_with_vi_wards(600.0, 1), locations())
    tracker.update(snapshot_with_vi_wards(601.0, 0), locations())
    assert tracker.update(snapshot_with_vi_wards(10.0, 0), locations()) == []


def test_the_overlay_shows_the_control_wards_likely_down() -> None:
    clues = ClueTracker()
    wards = WardTracker()
    for game_time_seconds, ward_count in [(600.0, 1), (601.0, 0)]:
        players = tuple(
            dataclasses.replace(seed, items=(CONTROL_WARD,) * ward_count)
            if seed.champion_name == "Vi"
            else seed
            for seed in DEFAULT_PLAYERS
        )
        state = compute_overlay_state(
            all_game_data(game_time_seconds, players=players),
            clue_tracker=clues,
            ward_tracker=wards,
        )
    assert [(ward.champion_name, ward.side) for ward in state.control_wards] == [("Vi", "enemy")]
