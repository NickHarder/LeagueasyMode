import dataclasses
from typing import Final, TypedDict

import pytest

from game_payloads import DEFAULT_PLAYERS, PlayerSeed, all_game_data
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.experience import ExperienceTracker, experience_to_reach
from leagueasymode.inference.gold import PlayerKey
from leagueasymode.overlay_state import LevelEstimate

ZED: Final = ("CHAOS", "zed")
CAITLYN: Final = ("CHAOS", "caitlyn")
VI_JUNGLER: Final = ("CHAOS", "vi")


class SeedChanges(TypedDict, total=False):
    level: int
    is_dead: bool


def players_with(**changes_by_champion: SeedChanges) -> tuple[PlayerSeed, ...]:
    return tuple(
        dataclasses.replace(seed, **changes_by_champion.get(seed.champion_name, {}))
        for seed in DEFAULT_PLAYERS
    )


def observe(
    tracker: ExperienceTracker, game_time_seconds: float, **changes_by_champion: SeedChanges
) -> dict[PlayerKey, LevelEstimate]:
    snapshot = GameSnapshot.model_validate(
        all_game_data(game_time_seconds, players=players_with(**changes_by_champion))
    )
    return tracker.update(snapshot)


def test_each_level_takes_100_more_experience_than_the_last() -> None:
    assert [experience_to_reach(level) for level in (1, 2, 3, 6, 11, 16, 18)] == [
        0,
        280,
        660,
        2400,
        7300,
        14700,
        18360,
    ]


def test_everyone_starts_at_level_one_with_no_experience() -> None:
    estimates = observe(ExperienceTracker(), 20.0)
    zed = estimates[ZED]
    assert (zed.experience, zed.band_experience, zed.progress_to_next_level) == (0, 0, 0.0)
    assert zed.next_power_level == 6


def test_the_rate_before_any_level_up_is_the_roles() -> None:
    estimates = observe(ExperienceTracker(), 20.0)
    # From 1:30: a solo laner 8.5 a second, a duo laner 6, a jungler 8.
    assert estimates[ZED].power_level_at_game_time_seconds == pytest.approx(90 + 2400 / 8.5)
    assert estimates[CAITLYN].power_level_at_game_time_seconds == pytest.approx(90 + 2400 / 6)
    assert estimates[VI_JUNGLER].power_level_at_game_time_seconds == pytest.approx(90 + 2400 / 8)


def test_a_level_up_pins_the_experience() -> None:
    tracker = ExperienceTracker()
    observe(tracker, 60.0)
    zed = observe(tracker, 120.0, Zed={"level": 2})[ZED]
    assert (zed.experience, zed.band_experience, zed.progress_to_next_level) == (280, 0, 0.0)


def test_between_level_ups_experience_grows_at_the_players_own_rate() -> None:
    tracker = ExperienceTracker()
    observe(tracker, 60.0)
    observe(tracker, 120.0, Zed={"level": 2})
    zed = observe(tracker, 140.0, Zed={"level": 2})[ZED]
    # 280 in 30 seconds is 9.33 a second, weighed 0.6 against the prior's 8.5: 9.
    assert zed.experience == 280 + 9 * 20
    assert zed.progress_to_next_level == pytest.approx(180 / 380)
    assert zed.power_level_at_game_time_seconds == pytest.approx(140 + (2400 - 460) / 9)
    assert zed.band_experience == round(1.2816 * 0.2 * 9 * 20)


def test_a_dead_player_gains_no_experience() -> None:
    tracker = ExperienceTracker()
    observe(tracker, 60.0)
    observe(tracker, 120.0, Zed={"level": 2})
    observe(tracker, 130.0, Zed={"level": 2, "is_dead": True})
    observe(tracker, 140.0, Zed={"level": 2, "is_dead": True})
    zed = observe(tracker, 150.0, Zed={"level": 2})[ZED]
    assert zed.experience == 280 + 9 * 10


def test_the_estimate_stays_within_the_level_the_scoreboard_gives() -> None:
    tracker = ExperienceTracker()
    observe(tracker, 60.0)
    observe(tracker, 120.0, Zed={"level": 2})
    zed = observe(tracker, 600.0, Zed={"level": 2})[ZED]
    assert zed.experience == 659
    assert zed.power_level_at_game_time_seconds == pytest.approx(600 + (2400 - 659) / 9)


def test_a_player_first_seen_mid_game_is_somewhere_in_their_level() -> None:
    zed = observe(ExperienceTracker(), 600.0, Zed={"level": 8})[ZED]
    # The prior's 8.5 a second from 1:30 lands inside level 8 (4060 to 5040).
    assert zed.experience == 4335
    assert zed.band_experience == round(1.2816 * 980 / 12**0.5)
    assert zed.next_power_level == 11
    assert zed.power_level_at_game_time_seconds == pytest.approx(600 + (7300 - 4335) / 8.5)


def test_a_player_behind_the_prior_is_taken_as_halfway_through_their_level() -> None:
    zed = observe(ExperienceTracker(), 1395.0, Zed={"level": 5})[ZED]
    assert zed.experience == (1720 + 2400) // 2
    assert zed.power_level_at_game_time_seconds == pytest.approx(1395 + 340 / 8.5)


def test_past_16_there_is_no_power_level_and_at_18_no_next_level() -> None:
    tracker = ExperienceTracker()
    estimates = observe(tracker, 2400.0, Zed={"level": 17}, Caitlyn={"level": 18})
    assert estimates[ZED].next_power_level is None
    assert estimates[ZED].power_level_at_game_time_seconds is None
    assert estimates[ZED].progress_to_next_level is not None
    assert estimates[CAITLYN].progress_to_next_level is None


def test_a_new_game_starts_the_tracker_over() -> None:
    tracker = ExperienceTracker()
    observe(tracker, 600.0, Zed={"level": 8})
    assert observe(tracker, 10.0)[ZED].experience == 0


def test_the_overlay_shows_each_players_experience() -> None:
    state = compute_overlay_state(all_game_data(20.0), experience_tracker=ExperienceTracker())
    assert all(card.level_estimate is not None for card in state.players)
    assert compute_overlay_state(all_game_data(20.0)).players[0].level_estimate is None
