import json
from pathlib import Path
from typing import Final

import pytest
from pydantic import JsonValue

from data_dragon_fixtures import fixture_patch_stats
from game_payloads import (
    DEFAULT_PLAYERS,
    champion_kill_event,
    dragon_kill_event,
    turret_killed_event,
)
from leagueasymode.game_summary import (
    GameSummary,
    SummaryMoment,
    SummaryPoint,
    game_summary,
    win_swings,
)
from leagueasymode.scoring import read_recorded_game, score_game
from recorded_games import game_timeline, write_scored_recording

SCHEMA_PATH: Final = Path(__file__).parents[1] / "overlay" / "web" / "game_summary.schema.json"


def horde_kill_event(event_id: int, event_time: float, killer_name: str) -> dict[str, JsonValue]:
    return {
        "EventID": event_id,
        "EventName": "HordeKill",
        "EventTime": event_time,
        "KillerName": killer_name,
        "Assisters": [],
    }


FEED: Final = [
    dragon_kill_event(1, 330.0, "Jungle Diff"),
    champion_kill_event(2, 400.0, "Shadow Step", "Ahri", []),
    horde_kill_event(3, 500.0, "Gank Plz"),
    turret_killed_event(4, 610.0, "Turret_T2_L_03_A", "Garen Main"),
]


def summary_of(tmp_path: Path) -> GameSummary:
    recording = write_scored_recording(
        tmp_path,
        DEFAULT_PLAYERS,
        timeline=game_timeline(),
        winning_team_id=100,
        feed_events=FEED,
    )
    game = read_recorded_game(recording)
    return game_summary(recording.name, game, score_game(game, fixture_patch_stats()))


def test_the_summary_says_who_won_with_what_and_for_how_long(tmp_path: Path) -> None:
    summary = summary_of(tmp_path)
    assert (summary.result, summary.champion_name, summary.duration_seconds) == (
        "win",
        "Ahri",
        900.0,
    )
    assert summary.recording_name == "game.jsonl.xz"


def test_the_feed_becomes_the_games_moments_from_your_side(tmp_path: Path) -> None:
    moments = [(moment.kind, moment.side, moment.text) for moment in summary_of(tmp_path).moments]
    assert moments == [
        ("dragon", "ally", "your team took the Fire dragon"),
        ("kill", "enemy", "Zed killed Ahri"),
        ("voidgrubs", "enemy", "their team took the Voidgrubs"),
        ("turret", "ally", "your team took their top outer turret"),
    ]


def test_the_win_chance_and_the_gold_lead_come_minute_by_minute(tmp_path: Path) -> None:
    summary = summary_of(tmp_path)
    assert [point.minute for point in summary.win_chance] == list(range(16))
    assert all(0.0 < point.value < 1.0 for point in summary.win_chance)
    # The timeline gives every player the same gold: no lead, minute by minute.
    assert [point.value for point in summary.gold_lead_true] == [0.0] * 16
    assert len(summary.gold_lead_estimated) == 16
    assert len(summary.swings) == 3


def test_every_estimator_scored_is_in_the_summary(tmp_path: Path) -> None:
    summary = summary_of(tmp_path)
    estimators = [score.estimator for score in summary.scores]
    assert "win chance" in estimators
    win_score = next(score for score in summary.scores if score.estimator == "win chance")
    assert win_score.text.startswith("win chance: 16 minutes, Brier score")


def moment_at(game_time_seconds: float, text: str) -> SummaryMoment:
    return SummaryMoment(game_time_seconds=game_time_seconds, kind="kill", side="ally", text=text)


def test_the_biggest_swings_name_what_happened_in_their_minute() -> None:
    chances = [0.5, 0.52, 0.7, 0.68, 0.4, 0.42]
    series = [SummaryPoint(minute=minute, value=value) for minute, value in enumerate(chances)]
    moments = [moment_at(100.0, "first"), moment_at(200.0, "second"), moment_at(230.0, "third")]
    swings = win_swings(series, moments, count=2)
    assert [swing.minute for swing in swings] == [4, 2]
    assert [swing.change for swing in swings] == pytest.approx([-0.28, 0.18])
    # Minute 2's swing is from 1:00 to 2:00; minute 4's from 3:00 to 4:00.
    assert swings[1].moments == ["first"]
    assert swings[0].moments == ["second", "third"]


def test_the_pages_contract_file_is_current() -> None:
    # overlay/web/src/summary.ts mirrors this schema. When the contract changes, run:
    # uv run python -m leagueasymode.game_summary > overlay/web/game_summary.schema.json
    assert json.loads(SCHEMA_PATH.read_text()) == GameSummary.model_json_schema()
