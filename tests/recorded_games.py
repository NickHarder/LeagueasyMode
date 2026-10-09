"""Recorded games for tests: a recording of a built game, with its details and timeline."""

import dataclasses
import datetime
from pathlib import Path
from typing import Final

from pydantic import JsonValue

from game_payloads import (
    CHAMPION_IDS,
    DEFAULT_PLAYERS,
    GAME_ID,
    PlayerSeed,
    all_game_data,
    champion_summary,
    game_start_event,
    gameflow_session,
)
from leagueasymode.inference.gold import passive_gold
from leagueasymode.league_client import GAMEFLOW_SESSION_PATH
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH, GAME_VERSION_PATH, ITEMS_PATH
from leagueasymode.recorder import GAME_DETAILS_PATH_TEMPLATE, TIMELINE_PATH_TEMPLATE
from leagueasymode.recording.writer import RecordingWriter

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


def game_details(
    positions_by_champion: dict[str, str], winning_team_id: int | None = None
) -> JsonValue:
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
        **(
            {
                "teams": [
                    {"teamId": team_id, "win": "Win" if team_id == winning_team_id else "Fail"}
                    for team_id in (100, 200)
                ]
            }
            if winning_team_id is not None
            else {}
        ),
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
    winning_team_id: int | None = None,
    feed_events: list[dict[str, JsonValue]] | None = None,
    past_timelines: dict[int, JsonValue] | None = None,
    client_answers: dict[str, JsonValue] | None = None,
) -> Path:
    """A recording of a built game, one answer a minute to 15:00; the feed shows each event from
    its time on. Past games' timelines, by game id, and other answers of the client, by path, are
    recorded at the start, as the player lookups ask for them."""
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
    for past_game_id, past_timeline in (past_timelines or {}).items():
        writer.write_client_resource(
            received_at_seconds=0.0,
            path=TIMELINE_PATH_TEMPLATE.format(game_id=past_game_id),
            payload=past_timeline,
        )
    for client_path, client_payload in (client_answers or {}).items():
        writer.write_client_resource(
            received_at_seconds=0.0, path=client_path, payload=client_payload
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
                [
                    game_start_event(),
                    *(
                        event
                        for event in feed_events or []
                        if isinstance(event["EventTime"], float)
                        and event["EventTime"] <= minute * 60.0
                    ),
                ],
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
        payload=game_details(details_positions, winning_team_id),
    )
    if timeline is not None:
        writer.write_client_resource(
            received_at_seconds=1000.0,
            path=TIMELINE_PATH_TEMPLATE.format(game_id=GAME_ID),
            payload=timeline,
        )
    writer.write_ended(received_at_seconds=1000.0, reason="game ended")
    return writer.close()


def kill(
    game_time_seconds: float,
    killer_id: int,
    victim_id: int,
    assister_ids: list[int],
    place: tuple[int, int] = (7000, 7000),
) -> JsonValue:
    return {
        "type": "CHAMPION_KILL",
        "timestamp": round(game_time_seconds * 1000),
        "killerId": killer_id,
        "victimId": victim_id,
        "assistingParticipantIds": list[JsonValue](assister_ids),
        "position": {"x": place[0], "y": place[1]},
    }


def monster_kill(
    game_time_seconds: float, team_id: int, monster_type: str, monster_sub_type: str = ""
) -> JsonValue:
    pit = (9866, 4414) if monster_type == "DRAGON" else (5007, 10471)
    return {
        "type": "ELITE_MONSTER_KILL",
        "timestamp": round(game_time_seconds * 1000),
        "killerTeamId": team_id,
        "monsterType": monster_type,
        "monsterSubType": monster_sub_type,
        "position": {"x": pit[0], "y": pit[1]},
    }
