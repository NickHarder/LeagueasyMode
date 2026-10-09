import dataclasses
from typing import Final

import pytest

from game_payloads import CHAMPION_IDS, DEFAULT_PLAYERS, all_game_data
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.jungle_path import CAMP_RULES, JunglePathTracker, travel_seconds
from leagueasymode.jungle_starts import JungleStarts
from leagueasymode.overlay_state import CampTimer, JunglePath
from leagueasymode.player_intel import GamePlayerRecord, PlayerRecord

MOVE_SPEED: Final = CAMP_RULES.default_move_speed
CLEAR_SECONDS: Final = CAMP_RULES.clear_seconds
# Vi, on the red team, as the engine and the records know her.
VI_KEY: Final = ("CHAOS", "vi")


def snapshot_with_vi_at(game_time_seconds: float, creep_score: int) -> GameSnapshot:
    players = tuple(
        dataclasses.replace(seed, creep_score=creep_score) if seed.champion_name == "Vi" else seed
        for seed in DEFAULT_PLAYERS
    )
    return GameSnapshot.model_validate(all_game_data(game_time_seconds, players=players))


def follow(
    tracker: JunglePathTracker, creep_scores_by_time: list[tuple[float, int]]
) -> tuple[list[JunglePath], list[CampTimer]]:
    result: tuple[list[JunglePath], list[CampTimer]] = ([], [])
    for game_time_seconds, creep_score in creep_scores_by_time:
        result = tracker.update(snapshot_with_vi_at(game_time_seconds, creep_score))
    return result


def vi_path(paths: list[JunglePath]) -> JunglePath:
    return next(path for path in paths if path.champion_name == "Vi")


def red_krugs_raptors() -> list[tuple[float, int]]:
    """Vi starts at red buff when it spawns at 1:30, then takes the krugs and the raptors."""
    red_done = CAMP_RULES.first_spawn_seconds + CLEAR_SECONDS["red_buff"]
    krugs_done = (
        red_done
        + travel_seconds("chaos_red_buff", "chaos_krugs", MOVE_SPEED)
        + CLEAR_SECONDS["krugs"]
    )
    raptors_done = (
        krugs_done
        + travel_seconds("chaos_krugs", "chaos_raptors", MOVE_SPEED)
        + CLEAR_SECONDS["raptors"]
    )
    return [
        (80.0, 0),
        (red_done, 4),
        (krugs_done, 8),
        (raptors_done, 12),
        (raptors_done + 10.0, 12),
    ]


def test_bursts_of_creep_score_decode_into_the_camps_that_fit_them() -> None:
    paths, _ = follow(JunglePathTracker(), red_krugs_raptors())
    vi_jungler = vi_path(paths)
    assert vi_jungler.side == "enemy"
    assert vi_jungler.recent_camps == ["their red", "their krugs", "their raptors"]


def test_their_next_camp_is_the_soonest_they_could_start_on_their_side() -> None:
    times = red_krugs_raptors()
    paths, _ = follow(JunglePathTracker(), times)
    raptors_done = times[3][0]
    soonest = min(
        ("wolves", "blue_buff", "gromp"),
        key=lambda kind: travel_seconds("chaos_raptors", f"chaos_{kind}", MOVE_SPEED),
    )
    vi_jungler = vi_path(paths)
    words = {"wolves": "their wolves", "blue_buff": "their blue", "gromp": "their gromp"}
    assert vi_jungler.next_camp == words[soonest]
    assert vi_jungler.next_camp_at_game_time_seconds == pytest.approx(
        max(
            raptors_done + travel_seconds("chaos_raptors", f"chaos_{soonest}", MOVE_SPEED),
            raptors_done + 10.0,
        )
    )


def test_each_camp_cleared_comes_back_after_its_respawn() -> None:
    times = red_krugs_raptors()
    _, timers = follow(JunglePathTracker(), times)
    red_done, krugs_done, raptors_done = times[1][0], times[2][0], times[3][0]
    assert [(timer.label, timer.cleared_by) for timer in timers] == [
        ("their krugs", "enemy"),
        ("their raptors", "enemy"),
        ("their red", "enemy"),
    ]
    assert [timer.respawns_at_game_time_seconds for timer in timers] == pytest.approx(
        [krugs_done + 135.0, raptors_done + 135.0, red_done + 300.0]
    )


def test_rises_close_together_are_one_camp() -> None:
    red_done = CAMP_RULES.first_spawn_seconds + CLEAR_SECONDS["red_buff"]
    paths, _ = follow(
        JunglePathTracker(),
        [(80.0, 0), (red_done - 3.0, 2), (red_done, 4), (red_done + 10.0, 4)],
    )
    # One camp, not two; which buff it was, one burst alone cannot tell.
    assert len(vi_path(paths).recent_camps) == 1


def one_buff_burst() -> list[tuple[float, int]]:
    """Vi takes one camp of a buff's time as the camps spawn: either buff, or the krugs."""
    buff_done = CAMP_RULES.first_spawn_seconds + CLEAR_SECONDS["red_buff"]
    return [(80.0, 0), (buff_done, 4), (buff_done + 10.0, 4)]


def first_camp_with_start(jungle_starts: JungleStarts) -> str:
    tracker = JunglePathTracker()
    paths: list[JunglePath] = []
    for game_time_seconds, creep_score in one_buff_burst():
        paths, _ = tracker.update(
            snapshot_with_vi_at(game_time_seconds, creep_score),
            jungle_starts={VI_KEY: jungle_starts},
        )
    return vi_path(paths).recent_camps[0]


def test_a_junglers_usual_start_decides_a_first_camp_the_burst_alone_cannot() -> None:
    assert first_camp_with_start(JungleStarts(blue_count=4, red_count=0)) == "their blue"
    assert first_camp_with_start(JungleStarts(blue_count=0, red_count=4)) in {
        "their red",
        "their krugs",
    }


def test_a_first_camp_seen_late_in_the_game_is_not_weighed_as_a_start() -> None:
    # The overlay started at 3:20: the first burst it sees is not the game's first clear. Before
    # the scuttles spawn, a buff's side would otherwise decide it.
    late_burst = [(200.0, 10), (210.0, 14), (220.0, 14)]

    def first_camp(jungle_starts: JungleStarts | None) -> str:
        tracker = JunglePathTracker()
        paths: list[JunglePath] = []
        for game_time_seconds, creep_score in late_burst:
            paths, _ = tracker.update(
                snapshot_with_vi_at(game_time_seconds, creep_score),
                jungle_starts={VI_KEY: jungle_starts} if jungle_starts is not None else None,
            )
        return vi_path(paths).recent_camps[0]

    assert first_camp(JungleStarts(blue_count=0, red_count=4)) == first_camp(None)


def test_an_even_record_of_starts_weighs_nothing() -> None:
    # Red, krugs and raptors decode as they do without a record.
    tracker = JunglePathTracker()
    paths: list[JunglePath] = []
    for game_time_seconds, creep_score in red_krugs_raptors():
        paths, _ = tracker.update(
            snapshot_with_vi_at(game_time_seconds, creep_score),
            jungle_starts={VI_KEY: JungleStarts(blue_count=2, red_count=2)},
        )
    assert vi_path(paths).recent_camps == ["their red", "their krugs", "their raptors"]


def test_the_engine_hands_the_tracker_each_junglers_usual_start() -> None:
    vi_seed = next(seed for seed in DEFAULT_PLAYERS if seed.champion_name == "Vi")
    records = {
        VI_KEY: GamePlayerRecord(
            champion_id=CHAMPION_IDS["Vi"],
            record=PlayerRecord(
                ranked=None,
                recent_games=(),
                jungle_starts=JungleStarts(blue_count=0, red_count=4),
            ),
        )
    }
    tracker = JunglePathTracker()
    states = [
        compute_overlay_state(
            all_game_data(
                game_time_seconds,
                players=tuple(
                    dataclasses.replace(seed, creep_score=creep_score) if seed is vi_seed else seed
                    for seed in DEFAULT_PLAYERS
                ),
            ),
            player_records=records,
            jungle_tracker=tracker,
        )
        for game_time_seconds, creep_score in one_buff_burst()
    ]
    # Without her habit, the burst alone decodes as her blue buff.
    vi_jungler = next(path for path in states[-1].jungle_paths if path.champion_name == "Vi")
    assert vi_jungler.recent_camps[0] in {"their red", "their krugs"}


def test_a_camp_cleared_is_not_cleared_again_before_it_is_back() -> None:
    red_done = CAMP_RULES.first_spawn_seconds + CLEAR_SECONDS["red_buff"]
    # A second burst right where red buff stands, while it is still down.
    paths, _ = follow(
        JunglePathTracker(),
        [(80.0, 0), (red_done, 4), (red_done + 20.0, 8), (red_done + 30.0, 8)],
    )
    second_camp = vi_path(paths).recent_camps[-1]
    assert second_camp != "their red"


def test_a_burst_under_way_is_not_decoded_yet() -> None:
    red_done = CAMP_RULES.first_spawn_seconds + CLEAR_SECONDS["red_buff"]
    paths, _ = follow(JunglePathTracker(), [(80.0, 0), (red_done, 4), (red_done + 2.0, 4)])
    assert vi_path(paths).recent_camps == []


def test_a_new_game_starts_the_tracker_over() -> None:
    tracker = JunglePathTracker()
    follow(tracker, red_krugs_raptors())
    paths, timers = tracker.update(snapshot_with_vi_at(10.0, 0))
    assert vi_path(paths).recent_camps == []
    assert timers == []


def test_the_overlay_shows_both_junglers_paths_and_the_camps_down() -> None:
    tracker = JunglePathTracker()
    states = [
        compute_overlay_state(
            all_game_data(
                game_time_seconds,
                players=tuple(
                    dataclasses.replace(seed, creep_score=creep_score)
                    if seed.champion_name == "Vi"
                    else seed
                    for seed in DEFAULT_PLAYERS
                ),
            ),
            jungle_tracker=tracker,
        )
        for game_time_seconds, creep_score in red_krugs_raptors()
    ]
    last_state = states[-1]
    assert sorted(path.champion_name for path in last_state.jungle_paths) == ["LeeSin", "Vi"]
    assert [timer.label for timer in last_state.camp_timers] == [
        "their krugs",
        "their raptors",
        "their red",
    ]
