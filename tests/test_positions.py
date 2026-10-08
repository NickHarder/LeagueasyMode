import dataclasses
from typing import Final

import pytest

from game_payloads import DEFAULT_PLAYERS, all_game_data, player_payload
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import ScoreboardPlayer
from leagueasymode.inference.callouts import CalloutTracker
from leagueasymode.inference.clues import ClueTracker
from leagueasymode.inference.positions import position_estimate
from leagueasymode.inference.rift_map import RIFT_MAP, region_center
from leagueasymode.overlay_state import (
    OverlayState,
    PlayerCard,
    PositionClue,
    PositionEstimate,
    RegionChance,
)

MOVE_SPEED: Final = 380.0


def scoreboard_player(champion_name: str, *, is_dead: bool = False) -> ScoreboardPlayer:
    seed = next(seed for seed in DEFAULT_PLAYERS if seed.champion_name == champion_name)
    return ScoreboardPlayer.model_validate(
        player_payload(dataclasses.replace(seed, is_dead=is_dead, respawn_timer_seconds=10.0))
    )


def at_point(point_name: str, game_time_seconds: float) -> PositionClue:
    return PositionClue(
        kind="turret",
        game_time_seconds=game_time_seconds,
        place="at a turret",
        point_name=point_name,
        region=RIFT_MAP.points[point_name].region,
    )


def estimate(
    champion_name: str,
    role: str,
    clues: list[PositionClue],
    game_time_seconds: float,
    *,
    is_dead: bool = False,
) -> PositionEstimate:
    result = position_estimate(
        scoreboard_player(champion_name, is_dead=is_dead),
        role,
        clues,
        move_speed=MOVE_SPEED,
        game_time_seconds=game_time_seconds,
        ally_team="ORDER",
    )
    assert result is not None
    return result


def test_a_player_just_pinned_is_where_the_clue_put_them() -> None:
    zed = estimate("Zed", "MIDDLE", [at_point("chaos_mid_outer_turret", 600.0)], 600.0)
    mid_x, mid_y = region_center("mid_lane")
    assert zed.regions == [
        RegionChance(
            region="mid_lane", label="mid lane", chance=1.0, x_position=mid_x, y_position=mid_y
        )
    ]
    assert (zed.away_chance, zed.unseen_seconds) == (0.0, 0.0)
    assert zed.reach_mid_seconds == pytest.approx(
        RIFT_MAP.distance("chaos_mid_outer_turret", "mid_center") / MOVE_SPEED
    )


def test_the_places_they_could_be_widen_with_time() -> None:
    clue = at_point("chaos_mid_outer_turret", 600.0)
    zed = estimate("Zed", "MIDDLE", [clue], 615.0)
    assert len(zed.regions) > 1
    assert zed.regions[0].region == "mid_lane"
    assert 0.0 < zed.away_chance < 0.5
    assert zed.unseen_seconds == 15.0


def test_unseen_for_long_only_the_roles_habits_remain() -> None:
    zed = estimate("Zed", "MIDDLE", [at_point("chaos_fountain", 100.0)], 1000.0)
    assert zed.regions[0].region == "mid_lane"
    caitlyn = estimate("Caitlyn", "BOTTOM", [at_point("chaos_fountain", 100.0)], 1000.0)
    assert caitlyn.regions[0].region == "bot_lane"


def test_a_jungler_seen_farming_is_somewhere_in_their_jungle() -> None:
    farming = PositionClue(
        kind="jungle",
        game_time_seconds=600.0,
        place="in the jungle",
        point_name=None,
        region="chaos_jungle",
    )
    vi_jungler = estimate("Vi", "JUNGLE", [farming], 600.0)
    assert {region.label for region in vi_jungler.regions} == {
        "their top jungle",
        "their bot jungle",
    }
    assert sum(region.chance for region in vi_jungler.regions) == pytest.approx(1.0)
    assert vi_jungler.away_chance == pytest.approx(0.0)


def test_the_soonest_to_a_lane_counts_down_from_the_clue() -> None:
    clue = at_point("chaos_mid_outer_turret", 600.0)
    zed = estimate("Zed", "MIDDLE", [clue], 605.0)
    walk_seconds = RIFT_MAP.distance("chaos_mid_outer_turret", "bot_lane_corner") / MOVE_SPEED
    assert zed.reach_bot_seconds == pytest.approx(walk_seconds - 5.0)
    assert estimate("Zed", "MIDDLE", [clue], 700.0).reach_bot_seconds == 0.0


def test_without_a_clue_they_started_in_their_fountain() -> None:
    # Five seconds in, no walk from the fountain has left the base yet.
    zed = estimate("Zed", "MIDDLE", [], 5.0)
    assert zed.unseen_seconds is None
    assert zed.regions[0].label == "their base"


def test_a_dead_player_has_no_position() -> None:
    assert (
        position_estimate(
            scoreboard_player("Zed", is_dead=True),
            "MIDDLE",
            [],
            move_speed=MOVE_SPEED,
            game_time_seconds=600.0,
            ally_team="ORDER",
        )
        is None
    )


def test_the_overlay_shows_where_each_player_likely_is() -> None:
    state = compute_overlay_state(all_game_data(600.0), clue_tracker=ClueTracker())
    zed = next(card for card in state.players if card.champion_name == "Zed")
    assert zed.location is not None
    assert [card.champion_name for card in state.players if card.is_you] == ["Ahri"]
    assert compute_overlay_state(all_game_data(600.0)).players[0].location is None


def you_in_mid() -> PlayerCard:
    return PlayerCard(
        champion_name="Ahri",
        side="ally",
        is_you=True,
        position="MIDDLE",
        role="MIDDLE",
        role_confidence="given",
        level=9,
        is_dead=False,
        respawns_at_game_time_seconds=None,
    )


def missing_enemy(
    champion_name: str, unseen_seconds: float, reach_mid_seconds: float
) -> PlayerCard:
    return PlayerCard(
        champion_name=champion_name,
        side="enemy",
        position="JUNGLE",
        role="JUNGLE",
        role_confidence="given",
        level=9,
        is_dead=False,
        respawns_at_game_time_seconds=None,
        location=PositionEstimate(
            regions=[
                RegionChance(
                    region="top_river",
                    label="top river",
                    chance=0.6,
                    x_position=4700.0,
                    y_position=9800.0,
                )
            ],
            away_chance=0.8,
            unseen_seconds=unseen_seconds,
            reach_top_seconds=30.0,
            reach_mid_seconds=reach_mid_seconds,
            reach_bot_seconds=40.0,
        ),
    )


def state_with(game_time_seconds: float, *enemies: PlayerCard) -> OverlayState:
    return OverlayState(
        is_game_running=True,
        game_time_seconds=game_time_seconds,
        players=[you_in_mid(), *enemies],
    )


def test_a_missing_enemy_who_could_reach_your_lane_soon_is_called_out() -> None:
    callouts = CalloutTracker()
    assert callouts.update(state_with(600.0, missing_enemy("Vi", 10.0, 12.0))) == []
    made = callouts.update(state_with(601.0, missing_enemy("Vi", 25.0, 11.5)))
    assert [(callout.kind, callout.text) for callout in made] == [
        ("missing", "Vi missing 0:25: can reach mid in ~0:12")
    ]


def test_missing_callouts_come_at_most_once_every_30_seconds() -> None:
    callouts = CalloutTracker()
    callouts.update(state_with(600.0))
    first = callouts.update(state_with(601.0, missing_enemy("Vi", 25.0, 11.5)))
    assert len(first) == 1
    soon_after = callouts.update(state_with(620.0, missing_enemy("Zed", 25.0, 5.0)))
    assert [callout.kind for callout in soon_after] == []
    later = callouts.update(state_with(640.0, missing_enemy("Zed", 45.0, 5.0)))
    assert [callout.text for callout in later] == ["Zed missing 0:45: can reach mid in ~0:05"]


def test_an_enemy_far_from_your_lane_is_not_called_out() -> None:
    callouts = CalloutTracker()
    callouts.update(state_with(600.0))
    assert callouts.update(state_with(601.0, missing_enemy("Vi", 25.0, 35.0))) == []
