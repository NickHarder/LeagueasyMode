import dataclasses
from typing import Final

import pytest

from game_payloads import (
    DEFAULT_PLAYERS,
    all_game_data,
    baron_kill_event,
    dragon_kill_event,
    game_start_event,
    turret_killed_event,
)
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.gold import GoldTracker
from leagueasymode.inference.objectives import buff_timers, dragon_timer, inhibitor_timers
from leagueasymode.inference.win_chance import (
    WIN_CHANCE_RULES,
    WinFeatures,
    win_chance,
    win_features,
)
from leagueasymode.overlay_state import TeamGold, WinReason

EVEN_GAME: Final = WinFeatures(
    game_minutes=15.0,
    is_blue_side=True,
    gold_lead=0.0,
    gold_lead_deviation=0.0,
    team_gold_scale=25_000.0,
    level_lead=0,
    turret_lead=0,
    inhibitor_lead=0,
    dragon_lead=0,
    soul=0,
    baron=0,
    elder=0,
    ally_alive=5,
    enemy_alive=5,
)
NO_SIDE: Final = dataclasses.replace(WIN_CHANCE_RULES, blue_side_weight=0.0)


def test_an_even_game_is_a_coin_flip() -> None:
    chance = win_chance(EVEN_GAME, NO_SIDE)
    assert chance.ally_chance == pytest.approx(0.5)
    assert chance.reasons == []


def test_the_blue_side_starts_a_little_ahead() -> None:
    blue = win_chance(EVEN_GAME).ally_chance
    red = win_chance(dataclasses.replace(EVEN_GAME, is_blue_side=False)).ally_chance
    assert 0.5 < blue < 0.53
    assert blue + red == pytest.approx(1.0)


def test_a_lead_for_one_side_is_the_same_deficit_for_the_other() -> None:
    ahead = dataclasses.replace(EVEN_GAME, gold_lead=3000.0, turret_lead=2, baron=1, level_lead=4)
    behind = dataclasses.replace(
        EVEN_GAME, gold_lead=-3000.0, turret_lead=-2, baron=-1, level_lead=-4
    )
    assert win_chance(ahead, NO_SIDE).ally_chance + win_chance(
        behind, NO_SIDE
    ).ally_chance == pytest.approx(1.0)


def test_a_medium_gold_lead_at_15_is_about_three_in_four() -> None:
    # Seasons 7 to 10: a medium lead at 15:00 wins 75% or more, a large one 90% or more.
    medium = win_chance(dataclasses.replace(EVEN_GAME, gold_lead=2500.0), NO_SIDE)
    large = win_chance(dataclasses.replace(EVEN_GAME, gold_lead=5000.0), NO_SIDE)
    assert 0.70 <= medium.ally_chance <= 0.80
    assert large.ally_chance >= 0.85


def test_an_unsure_gold_lead_counts_for_less() -> None:
    sure = win_chance(dataclasses.replace(EVEN_GAME, gold_lead=3000.0), NO_SIDE)
    unsure = win_chance(
        dataclasses.replace(EVEN_GAME, gold_lead=3000.0, gold_lead_deviation=3000.0), NO_SIDE
    )
    assert 0.5 < unsure.ally_chance < sure.ally_chance


def test_early_gold_is_measured_against_a_floor_not_the_little_earned() -> None:
    early = dataclasses.replace(
        EVEN_GAME, game_minutes=3.0, gold_lead=400.0, team_gold_scale=4000.0
    )
    assert win_chance(early, NO_SIDE).ally_chance < 0.62


def test_players_down_weigh_more_late() -> None:
    early = dataclasses.replace(EVEN_GAME, game_minutes=8.0, enemy_alive=3)
    late = dataclasses.replace(EVEN_GAME, game_minutes=35.0, enemy_alive=3)
    assert 0.5 < win_chance(early, NO_SIDE).ally_chance < win_chance(late, NO_SIDE).ally_chance


def test_the_two_largest_reasons_are_named_from_your_side() -> None:
    features = dataclasses.replace(
        EVEN_GAME, gold_lead=-2100.0, baron=1, dragon_lead=1, turret_lead=-1
    )
    reasons = win_chance(features, NO_SIDE).reasons
    assert [reason.label for reason in reasons] == ["gold \u22122.1k", "Baron"]
    assert reasons[0].effect < 0 < reasons[1].effect
    assert isinstance(reasons[0], WinReason)


def test_each_reason_reads_from_your_side() -> None:
    def labels(features: WinFeatures) -> list[str]:
        rules = dataclasses.replace(NO_SIDE, gold_share_weight=0.0)
        return [reason.label for reason in win_chance(features, rules).reasons]

    assert labels(dataclasses.replace(EVEN_GAME, soul=-1)) == ["their soul"]
    assert labels(dataclasses.replace(EVEN_GAME, elder=-1, turret_lead=3)) == [
        "their Elder",
        "turrets +3",
    ]
    assert labels(dataclasses.replace(EVEN_GAME, game_minutes=30.0, enemy_alive=3)) == ["5v3"]
    assert labels(dataclasses.replace(EVEN_GAME, inhibitor_lead=1, dragon_lead=-2)) == [
        "inhibitors +1",
        "dragons \u22122",
    ]


def features_of(payload: object, team_gold: TeamGold | None = None) -> WinFeatures:
    snapshot = GameSnapshot.model_validate(payload)
    return win_features(
        snapshot,
        team_gold=team_gold,
        team_item_gold=None,
        dragon=dragon_timer(snapshot),
        buffs=buff_timers(snapshot),
        inhibitors=inhibitor_timers(snapshot),
    )


def test_the_game_gives_the_structures_monsters_and_players_alive() -> None:
    events = [
        game_start_event(),
        dragon_kill_event(1, 400.0, "Jungle Diff"),
        dragon_kill_event(2, 800.0, "Gank Plz"),
        dragon_kill_event(3, 1100.0, "Jungle Diff"),
        turret_killed_event(4, 900.0, "Turret_T2_R_03_A", "Bot Gap"),
        turret_killed_event(5, 950.0, "Turret_T2_L_03_A", "Garen Main"),
        turret_killed_event(6, 960.0, "Turret_T1_C_05_A", "Shadow Step"),
        baron_kill_event(7, 1250.0, "Jungle Diff"),
    ]
    players = tuple(
        dataclasses.replace(seed, is_dead=True, respawn_timer_seconds=20.0)
        if seed.champion_name == "Zed"
        else dataclasses.replace(seed, level=11 if seed.team == "ORDER" else 10)
        for seed in DEFAULT_PLAYERS
    )
    features = features_of(all_game_data(1300.0, events, players))
    assert features.game_minutes == pytest.approx(1300.0 / 60.0)
    assert features.is_blue_side
    assert (features.turret_lead, features.dragon_lead, features.baron) == (1, 1, 1)
    assert (features.ally_alive, features.enemy_alive) == (5, 4)
    # Zed's level stays 1 while dead in the built game: four enemies at 10, one at 1.
    assert features.level_lead == 55 - 41
    assert (features.gold_lead, features.gold_lead_deviation) == (0.0, 0.0)


def test_the_gold_lead_and_its_band_come_from_the_team_gold() -> None:
    features = features_of(
        all_game_data(900.0),
        TeamGold(ally_total_gold=26_000, enemy_total_gold=24_000, lead_band_gold=1282),
    )
    assert features.gold_lead == 2000.0
    assert features.team_gold_scale == 25_000.0
    assert features.gold_lead_deviation == pytest.approx(1000.0, rel=1e-3)


def test_the_overlay_shows_the_win_chance() -> None:
    without_gold = compute_overlay_state(all_game_data(600.0)).win_chance
    assert without_gold is not None
    assert without_gold.ally_chance == pytest.approx(win_chance(EVEN_GAME).ally_chance)
    # Ahri holds 500 gold at 10:00, exact, against the others' estimates: her team is behind.
    with_gold = compute_overlay_state(all_game_data(600.0), gold_tracker=GoldTracker()).win_chance
    assert with_gold is not None
    assert with_gold.ally_chance < without_gold.ally_chance


def test_the_overlay_uses_the_weights_it_is_given() -> None:
    hand_set = compute_overlay_state(all_game_data(600.0)).win_chance
    refit = compute_overlay_state(
        all_game_data(600.0),
        win_rules=dataclasses.replace(WIN_CHANCE_RULES, blue_side_weight=0.5),
    ).win_chance
    assert hand_set is not None
    assert refit is not None
    assert refit.ally_chance > hand_set.ally_chance
