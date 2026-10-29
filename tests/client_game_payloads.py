"""Client-shaped game details and timeline for the roast's tests (phases 11.2 and 11.3).

Ten players in the client's older shape: blue side loses, and our Ahri (participant 3) is in the
middle; red side pulls ahead, and Ahri dies alone to LeBlanc a little before a red dragon.
"""

import re
from typing import Final

from pydantic import JsonValue

GAME_ID: Final = 9000000202
MIDDLE_ID: Final = 3
# Champion ids and the names the champion summary gives them.
CHAMPIONS: Final = {
    1: (24, "Jax"),
    2: (64, "Lee Sin"),
    3: (103, "Ahri"),
    4: (222, "Jinx"),
    5: (117, "Lulu"),
    6: (86, "Garen"),
    7: (254, "Vi"),
    8: (7, "LeBlanc"),
    9: (145, "Kai'Sa"),
    10: (111, "Nautilus"),
}
# Each participant's lane and role, as the client's older shape writes them.
LANES: Final = {
    1: ("TOP", "SOLO"),
    2: ("JUNGLE", "NONE"),
    3: ("MIDDLE", "SOLO"),
    4: ("BOTTOM", "CARRY"),
    5: ("BOTTOM", "SUPPORT"),
}


def summary_payload() -> JsonValue:
    entries: list[JsonValue] = [{"id": -1, "name": "None", "alias": "None"}]
    entries.extend(
        {"id": champion_id, "name": name, "alias": re.sub(r"[^A-Za-z]", "", name)}
        for champion_id, name in CHAMPIONS.values()
    )
    return entries


def details_payload(
    *,
    states_win: bool = True,
    team_position_of_first: str | None = None,
    fields_missing_for_second: tuple[str, ...] = (),
    remade_by_fifth: bool = False,
) -> JsonValue:
    """Return ten players' details: blue side loses, and our Ahri is in the middle.

    Args:
        states_win: Whether each player's stats say whether they won, or only the teams do.
        team_position_of_first: A team position for the first participant, beside lane and role.
        fields_missing_for_second: Stats fields the second participant's answer leaves out.
        remade_by_fifth: Whether the fifth participant's stats say the game was remade.
    """
    participants: list[JsonValue] = []
    identities: list[JsonValue] = []
    for participant_id in range(1, 11):
        lane, role = LANES[(participant_id - 1) % 5 + 1]
        blue = participant_id <= 5
        stats: dict[str, JsonValue] = {
            "kills": participant_id,
            "deaths": 11 - participant_id,
            "assists": 2,
            "visionScore": 10 + participant_id,
            "detectorWardsPlaced": participant_id % 3,
            "enemyMissingPings": 4 if participant_id == 2 else 0,
            "totalDamageDealtToChampions": 1000 * participant_id,
            "totalTimeSpentDead": 30 * (11 - participant_id),
            "longestTimeSpentLiving": 400 + participant_id,
            "gameEndedInSurrender": True,
            "gameEndedInEarlySurrender": remade_by_fifth and participant_id == 5,
        }
        stated: dict[str, JsonValue] = {"win": not blue} if states_win else {}
        missing = fields_missing_for_second if participant_id == 2 else ()
        position: dict[str, JsonValue] = (
            {"teamPosition": team_position_of_first}
            if team_position_of_first and participant_id == 1
            else {}
        )
        participants.append(
            {
                "participantId": participant_id,
                "teamId": 100 if blue else 200,
                "championId": CHAMPIONS[participant_id][0],
                "timeline": {"lane": lane, "role": role},
                **position,
                "stats": {
                    **stated,
                    **{name: value for name, value in stats.items() if name not in missing},
                },
            }
        )
        identities.append(
            {
                "participantId": participant_id,
                "player": {
                    "puuid": f"placeholder-puuid-{participant_id}",
                    "gameName": f"Player {participant_id}",
                    "tagLine": "TEST",
                },
            }
        )
    return {
        "gameId": GAME_ID,
        "gameDuration": 1834,
        "participants": participants,
        "participantIdentities": identities,
        "teams": [
            {"teamId": 100, "win": "Fail", "dragonKills": 1, "baronKills": 0, "towerKills": 2},
            {"teamId": 200, "win": "Win", "dragonKills": 3, "baronKills": 1, "towerKills": 9},
        ],
    }


def timeline_payload(*, listed: bool = False) -> JsonValue:
    """Return a frame a minute to 20:00; red side pulls ahead, and Ahri dies alone to LeBlanc.

    Args:
        listed: Whether each frame lists the participants' numbers rather than keying them by id.
    """
    frames: list[JsonValue] = []
    for minute in range(21):
        participant_frames: dict[str, JsonValue] = {
            str(participant_id): {
                "participantId": participant_id,
                "totalGold": 500 + minute * (300 if participant_id <= 5 else 400),
                "currentGold": 1600 if participant_id == MIDDLE_ID else 200,
                "minionsKilled": minute * (6 if participant_id <= 5 else 7),
                "jungleMinionsKilled": 0,
                "level": min(18, 1 + minute // 2) - (1 if participant_id == MIDDLE_ID else 0),
            }
            for participant_id in range(1, 11)
        }
        events: list[JsonValue] = []
        if minute == 6:
            events.append(
                {
                    "type": "CHAMPION_KILL",
                    "timestamp": 6 * 60_000 + 5_000,
                    "killerId": 8,
                    "victimId": MIDDLE_ID,
                    "assistingParticipantIds": [],
                }
            )
            events.append(
                {
                    "type": "ELITE_MONSTER_KILL",
                    "timestamp": 6 * 60_000 + 35_000,
                    "killerTeamId": 200,
                    "monsterType": "DRAGON",
                }
            )
        frames.append(
            {
                # The client's frames land a little after the minute.
                "timestamp": minute * 60_000 + 250,
                "participantFrames": list(participant_frames.values())
                if listed
                else participant_frames,
                "events": events,
            }
        )
    return {"frames": frames}
