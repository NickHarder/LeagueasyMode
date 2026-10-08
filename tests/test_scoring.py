import dataclasses
import datetime
from pathlib import Path
from typing import Final

import pytest
from pydantic import JsonValue

from data_dragon_fixtures import FIXTURE_FILES, fixture_patch_stats
from game_payloads import (
    CHAMPION_IDS,
    DEFAULT_PLAYERS,
    GAME_ID,
    PlayerSeed,
    all_game_data,
    champion_summary,
    gameflow_session,
)
from leagueasymode.cli import main
from leagueasymode.data_dragon import PatchStatsStore
from leagueasymode.inference.gold import passive_gold
from leagueasymode.inference.rift_map import MapPoint, RiftMap
from leagueasymode.league_client import GAMEFLOW_SESSION_PATH
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH, GAME_VERSION_PATH, ITEMS_PATH
from leagueasymode.recorder import GAME_DETAILS_PATH_TEMPLATE, TIMELINE_PATH_TEMPLATE
from leagueasymode.recording.writer import RecordingWriter
from leagueasymode.scoring import (
    read_recorded_game,
    score_backs,
    score_combat_stats,
    score_experience,
    score_gold,
    score_map,
    score_next_items,
    score_recording,
    score_roles,
)

# Clear signals for each role: Smite for the junglers, Teleport for the top laners, Heal for the
# bottom laners, and a support with far less CS than their mid laner.
CREEP_SCORES: Final = {
    "Garen": 110,
    "LeeSin": 60,
    "Ahri": 150,
    "Jinx": 160,
    "Thresh": 20,
    "Darius": 105,
    "Vi": 55,
    "Zed": 140,
    "Caitlyn": 170,
    "Lux": 25,
}


def players_at(*, are_positions_given: bool, level: int = 9) -> tuple[PlayerSeed, ...]:
    return tuple(
        dataclasses.replace(
            seed,
            position=seed.position if are_positions_given else "",
            creep_score=CREEP_SCORES[seed.champion_name],
            level=level,
        )
        for seed in DEFAULT_PLAYERS
    )


def game_details(positions_by_champion: dict[str, str]) -> JsonValue:
    lane_and_role = {
        "TOP": ("TOP", "SOLO"),
        "JUNGLE": ("JUNGLE", "NONE"),
        "MIDDLE": ("MIDDLE", "SOLO"),
        "BOTTOM": ("BOTTOM", "CARRY"),
        "UTILITY": ("BOTTOM", "SUPPORT"),
    }
    return {
        "gameId": GAME_ID,
        "participants": [
            {
                "participantId": index + 1,
                "championId": CHAMPION_IDS[seed.champion_name],
                "teamId": 100 if seed.team == "ORDER" else 200,
                "timeline": {
                    "lane": lane_and_role[positions_by_champion[seed.champion_name]][0],
                    "role": lane_and_role[positions_by_champion[seed.champion_name]][1],
                },
            }
            for index, seed in enumerate(DEFAULT_PLAYERS)
        ],
    }


def game_timeline(
    gold_off_by: int = 0, events_by_minute: dict[int, list[JsonValue]] | None = None
) -> JsonValue:
    """A timeline in which every player has earned the starting and passive gold, and spent none."""
    return {
        "frameInterval": 60000,
        "frames": [
            {
                "timestamp": minute * 60000 + 25,
                "participantFrames": {
                    str(index + 1): {
                        "participantId": index + 1,
                        "currentGold": round(500 + passive_gold(minute * 60.0)) + gold_off_by,
                        "totalGold": round(500 + passive_gold(minute * 60.0)) + gold_off_by,
                        "level": 1,
                        "xp": 0,
                        "minionsKilled": 0,
                        "jungleMinionsKilled": 0,
                    }
                    for index in range(len(DEFAULT_PLAYERS))
                },
                "events": (events_by_minute or {}).get(minute, []),
            }
            for minute in range(16)
        ],
    }


def write_scored_recording(
    directory: Path,
    players: tuple[PlayerSeed, ...],
    positions_by_champion: dict[str, str] | None = None,
    timeline: JsonValue | None = None,
    zed_buys_at_minute: int | None = None,
    items_payload: JsonValue | None = None,
) -> Path:
    writer = RecordingWriter(directory / "game.jsonl", keyframe_interval_seconds=60.0)
    writer.write_started(
        started_at=datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
        recorder_version="test",
        poll_interval_seconds=0.5,
    )
    writer.write_client_resource(
        received_at_seconds=0.0, path=GAMEFLOW_SESSION_PATH, payload=gameflow_session()
    )
    writer.write_client_resource(
        received_at_seconds=0.0, path=CHAMPION_SUMMARY_PATH, payload=champion_summary()
    )
    writer.write_client_resource(
        received_at_seconds=0.0, path=GAME_VERSION_PATH, payload="16.19.712.1234"
    )
    if items_payload is not None:
        writer.write_client_resource(
            received_at_seconds=0.0, path=ITEMS_PATH, payload=items_payload
        )
    for minute in range(16):
        has_zed_bought = zed_buys_at_minute is not None and minute >= zed_buys_at_minute
        writer.write_snapshot(
            received_at_seconds=minute * 60.0,
            payload=all_game_data(
                minute * 60.0,
                players=tuple(
                    dataclasses.replace(seed, items=((1036, "Long Sword", 350),))
                    if has_zed_bought and seed.champion_name == "Zed"
                    else seed
                    for seed in players
                ),
            ),
        )
    details_positions = positions_by_champion or {
        seed.champion_name: seed.position for seed in DEFAULT_PLAYERS
    }
    writer.write_client_resource(
        received_at_seconds=1000.0,
        path=GAME_DETAILS_PATH_TEMPLATE.format(game_id=GAME_ID),
        payload=game_details(details_positions),
    )
    if timeline is not None:
        writer.write_client_resource(
            received_at_seconds=1000.0,
            path=TIMELINE_PATH_TEMPLATE.format(game_id=GAME_ID),
            payload=timeline,
        )
    writer.write_ended(received_at_seconds=1000.0, reason="game ended")
    return writer.close()


def test_the_role_estimator_finds_every_role_the_game_gave_once_they_are_hidden(
    tmp_path: Path,
) -> None:
    game = read_recorded_game(
        write_scored_recording(tmp_path, players_at(are_positions_given=True))
    )
    score = score_roles(game)
    assert score is not None
    assert (score.sample_count, score.value) == (10, 1.0)
    assert score.measure == "share_correct"


def test_without_positions_the_game_details_are_the_truth(tmp_path: Path) -> None:
    # The details say Ahri and Thresh swapped, which the signals do not show.
    swapped = {seed.champion_name: seed.position for seed in DEFAULT_PLAYERS}
    swapped["Ahri"], swapped["Thresh"] = "UTILITY", "MIDDLE"
    recording = write_scored_recording(tmp_path, players_at(are_positions_given=False), swapped)
    score = score_roles(read_recorded_game(recording))
    assert score is not None
    assert (score.sample_count, score.value) == (10, 0.8)


def test_a_recording_without_truth_scores_no_roles(tmp_path: Path) -> None:
    writer = RecordingWriter(tmp_path / "bare.jsonl", keyframe_interval_seconds=60.0)
    writer.write_started(
        started_at=datetime.datetime(2026, 10, 8, tzinfo=datetime.UTC),
        recorder_version="test",
        poll_interval_seconds=0.5,
    )
    writer.write_snapshot(
        received_at_seconds=0.0,
        payload=all_game_data(600.0, players=players_at(are_positions_given=False)),
    )
    writer.write_ended(received_at_seconds=1.0, reason="game ended")
    assert score_roles(read_recorded_game(writer.close())) is None


def test_your_exact_stats_score_the_combat_stats_estimate(tmp_path: Path) -> None:
    # At level 1 with no items, the estimate is the base stats, which are the exact ones here.
    level_one = write_scored_recording(tmp_path, players_at(are_positions_given=True, level=1))
    score = score_combat_stats(read_recorded_game(level_one), fixture_patch_stats())
    assert score is not None
    assert score.measure == "mean_absolute_percent_error"
    assert score.sample_count == 16
    assert score.value == pytest.approx(0.0)


def test_an_estimate_off_from_your_exact_stats_scores_its_error(tmp_path: Path) -> None:
    # At level 9 the estimate grows; the built game's exact stats stay at level 1's.
    level_nine = write_scored_recording(tmp_path, players_at(are_positions_given=True))
    score = score_combat_stats(read_recorded_game(level_nine), fixture_patch_stats())
    assert score is not None
    assert score.value > 10.0


def test_score_prints_each_estimators_score(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recording = write_scored_recording(tmp_path, players_at(are_positions_given=True, level=1))
    patch_data_directory = tmp_path / "patch-data"
    PatchStatsStore(patch_data_directory).save("16.19.1", FIXTURE_FILES)
    monkeypatch.setenv("LEAGUEASYMODE_PATCH_DATA_DIRECTORY", str(patch_data_directory))
    monkeypatch.setenv("LEAGUEASYMODE_DOWNLOAD_PATCH_STATS", "false")
    assert main(["score", str(recording)]) == 0
    printed = capsys.readouterr().out
    assert "roles: 10/10 correct (100%)" in printed
    assert "combat stats (yours): 16 moments, 0.0% off on average" in printed


def test_scores_come_together_for_a_recording(tmp_path: Path) -> None:
    recording = write_scored_recording(tmp_path, players_at(are_positions_given=True, level=1))
    scores = score_recording(recording, fixture_patch_stats())
    assert [score.estimator for score in scores] == ["roles", "combat stats (yours)"]


def test_gold_is_scored_for_every_player_but_you_against_the_timeline(tmp_path: Path) -> None:
    recording = write_scored_recording(tmp_path, DEFAULT_PLAYERS, timeline=game_timeline())
    scores = score_gold(read_recorded_game(recording))
    # Nine players (your own gold is exact) at each of 15 minutes, all exactly right.
    assert [(score.estimator, score.sample_count, score.value) for score in scores] == [
        ("gold earned", 135, 0.0),
        ("gold unspent", 135, 0.0),
        ("gold band", 135, 1.0),
    ]


def test_gold_off_by_more_than_the_band_is_scored_as_outside_it(tmp_path: Path) -> None:
    recording = write_scored_recording(
        tmp_path, DEFAULT_PLAYERS, timeline=game_timeline(gold_off_by=100)
    )
    earned, unspent, band = score_gold(read_recorded_game(recording))
    assert (earned.value, unspent.value) == (100.0, 100.0)
    # The band passes 100 gold from 11:00, when 9:30 of unseen income is that unsure.
    assert band.value == pytest.approx(5 / 15)
    assert band.describe() == "gold band: holds the truth 45/135 times (33%)"
    assert earned.describe() == "gold earned: 135 player-minutes, 100 gold off on average"


def test_a_recording_without_a_timeline_scores_no_gold(tmp_path: Path) -> None:
    recording = write_scored_recording(tmp_path, DEFAULT_PLAYERS)
    assert score_gold(read_recorded_game(recording)) == []


def test_experience_is_scored_for_every_player_against_the_timeline(tmp_path: Path) -> None:
    # Everyone stays level 1 with no experience; the estimate grows at each role's prior rate from
    # 1:30, a solo laner 8.5 a second, a duo laner 6, a jungler 8, until the level's 279.
    recording = write_scored_recording(tmp_path, DEFAULT_PLAYERS, timeline=game_timeline())
    experience, band = score_experience(read_recorded_game(recording))
    at_two_minutes = 2 * (8.5 + 8.0 + 8.5 + 6.0 + 6.0) * 30
    from_three_minutes = 10 * 13 * 279
    assert experience.sample_count == 150
    assert experience.value == pytest.approx((at_two_minutes + from_three_minutes) / 150, abs=0.1)
    assert experience.describe().startswith("experience: 150 player-minutes, 257 experience off")
    assert band.estimator == "experience band"


def purchase(participant_id: int, game_time_seconds: float) -> JsonValue:
    return {
        "type": "ITEM_PURCHASED",
        "timestamp": round(game_time_seconds * 1000),
        "participantId": participant_id,
        "itemId": 1036,
    }


def test_backs_are_scored_against_the_timelines_purchases(tmp_path: Path) -> None:
    # Zed (participant 8) shops at 8:00 alive, which the tracker sees. Caitlyn (9) shops at 10:00,
    # which the built scoreboard never shows, and at 12:30 after dying at 12:00, which is the
    # death's shopping. Vi (7) buys two things within 30 seconds: one trip.
    kill_on_caitlyn: JsonValue = {
        "type": "CHAMPION_KILL",
        "timestamp": 720000,
        "victimId": 9,
        "killerId": 1,
    }
    events_by_minute: dict[int, list[JsonValue]] = {
        8: [purchase(8, 480.5)],
        10: [purchase(9, 600.0), purchase(7, 610.0), purchase(7, 625.0)],
        12: [kill_on_caitlyn, purchase(9, 750.0)],
    }
    recording = write_scored_recording(
        tmp_path,
        DEFAULT_PLAYERS,
        timeline=game_timeline(events_by_minute=events_by_minute),
        zed_buys_at_minute=8,
    )
    of_the_timeline, of_those_seen = score_backs(read_recorded_game(recording))
    assert of_the_timeline.describe() == "backs (of the timeline's): 1/3 matched (33%)"
    assert of_those_seen.describe() == "backs (of those seen): 1/1 matched (100%)"


ITEMS_FOR_THE_BUILD_PATH: Final[JsonValue] = [
    {"id": 1036, "name": "Long Sword", "priceTotal": 350, "to": [3031]},
    {"id": 1038, "name": "B. F. Sword", "priceTotal": 1300, "to": [3031]},
    {"id": 1018, "name": "Cloak of Agility", "priceTotal": 600, "to": [3031]},
    {"id": 1029, "name": "Cloth Armor", "priceTotal": 300, "to": [3068]},
    {"id": 1058, "name": "Needlessly Large Rod", "priceTotal": 1200, "to": [3089]},
    {
        "id": 3031,
        "name": "Infinity Edge",
        "priceTotal": 3400,
        "from": [1038, 1018, 1036],
        "categories": ["Damage", "CriticalStrike"],
    },
    {
        "id": 3089,
        "name": "Rabadon's Deathcap",
        "priceTotal": 3600,
        "from": [1058, 1058],
        "categories": ["SpellDamage"],
    },
    {
        "id": 3068,
        "name": "Sunfire Aegis",
        "priceTotal": 2700,
        "from": [1029],
        "categories": ["Health", "Armor"],
    },
]


def item_purchase(participant_id: int, game_time_seconds: float, item_id: int) -> JsonValue:
    return {
        "type": "ITEM_PURCHASED",
        "timestamp": round(game_time_seconds * 1000),
        "participantId": participant_id,
        "itemId": item_id,
    }


def test_next_items_are_scored_against_the_next_finished_item_bought(tmp_path: Path) -> None:
    # Caitlyn (participant 9) holds a B. F. Sword and buys Infinity Edge at 15:00: right at each
    # of minutes 0 to 14. Lux (10) buys Sunfire Aegis at 10:00, where a mage is taken to buy
    # Rabadon's: wrong at minutes 0 to 9.
    players = tuple(
        dataclasses.replace(seed, items=((1038, "B. F. Sword", 1300),))
        if seed.champion_name == "Caitlyn"
        else seed
        for seed in DEFAULT_PLAYERS
    )
    events_by_minute: dict[int, list[JsonValue]] = {
        10: [item_purchase(10, 600.0, 3068)],
        15: [item_purchase(9, 900.0, 3031)],
    }
    recording = write_scored_recording(
        tmp_path,
        players,
        timeline=game_timeline(events_by_minute=events_by_minute),
        items_payload=ITEMS_FOR_THE_BUILD_PATH,
    )
    score = score_next_items(read_recorded_game(recording), fixture_patch_stats())
    assert score is not None
    assert score.describe() == "next item: 15/25 correct (60%)"


def test_the_map_is_scored_by_how_far_the_timelines_positions_lie_from_its_paths(
    tmp_path: Path,
) -> None:
    # A map of one path along the x axis; one position on it, one 300 units off it.
    one_path = RiftMap(
        [MapPoint("west", 0.0, 0.0, "lane"), MapPoint("east", 1000.0, 0.0, "lane")],
        [("west", "east")],
    )
    frames: JsonValue = {
        "frames": [
            {
                "timestamp": 60000,
                "participantFrames": {
                    "1": {"participantId": 1, "position": {"x": 500, "y": 0}},
                    "2": {"participantId": 2, "position": {"x": 500, "y": 300}},
                },
            }
        ]
    }
    recording = write_scored_recording(tmp_path, DEFAULT_PLAYERS, timeline=frames)
    score = score_map(read_recorded_game(recording), one_path)
    assert score is not None
    assert score.describe() == "map: 2 positions, 150 units from its paths on average"
