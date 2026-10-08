"""Answers of the game's API and the League client, built for tests.

The shapes follow the game's Live Client Data API (`/liveclientdata/allgamedata`) and the client's
gameflow session. Every name here is invented. A field the code does not read yet is still here, so
that a test sees an answer as large and as nested as a real one.
"""

from dataclasses import dataclass, field
from typing import Final

from pydantic import JsonValue

ORDER: Final = "ORDER"
CHAOS: Final = "CHAOS"


@dataclass(frozen=True)
class PlayerSeed:
    """One player of a built game: who they are and what they play."""

    riot_id_game_name: str
    riot_id_tag_line: str
    champion_name: str
    team: str
    position: str
    summoner_spells: tuple[str, str] = ("Flash", "Ignite")
    level: int = 1
    creep_score: int = 0
    items: tuple[tuple[int, str, int], ...] = field(default=())
    is_dead: bool = False
    respawn_timer_seconds: float = 0.0

    @property
    def riot_id(self) -> str:
        return f"{self.riot_id_game_name}#{self.riot_id_tag_line}"


DEFAULT_PLAYERS: Final = (
    PlayerSeed("Garen Main", "NA1", "Garen", ORDER, "TOP", ("Flash", "Teleport")),
    PlayerSeed("Jungle Diff", "EUW", "LeeSin", ORDER, "JUNGLE", ("Flash", "Smite")),
    PlayerSeed("Ahri", "NA1", "Ahri", ORDER, "MIDDLE"),
    PlayerSeed("Bot Gap", "NA1", "Jinx", ORDER, "BOTTOM", ("Flash", "Heal")),
    PlayerSeed("Warded", "NA1", "Thresh", ORDER, "UTILITY"),
    PlayerSeed("Top Dog", "KR1", "Darius", CHAOS, "TOP", ("Flash", "Teleport")),
    PlayerSeed("Gank Plz", "NA1", "Vi", CHAOS, "JUNGLE", ("Flash", "Smite")),
    PlayerSeed("Shadow Step", "NA1", "Zed", CHAOS, "MIDDLE"),
    PlayerSeed("Headshot", "NA1", "Caitlyn", CHAOS, "BOTTOM", ("Flash", "Heal")),
    PlayerSeed("Light Binder", "NA1", "Lux", CHAOS, "UTILITY", ("Flash", "Exhaust")),
)
ACTIVE_PLAYER_INDEX: Final = 2


def game_start_event() -> dict[str, JsonValue]:
    return {"EventID": 0, "EventName": "GameStart", "EventTime": 0.0}


def dragon_kill_event(
    event_id: int, event_time: float, killer_name: str, dragon_type: str = "Fire"
) -> dict[str, JsonValue]:
    return {
        "EventID": event_id,
        "EventName": "DragonKill",
        "EventTime": event_time,
        "DragonType": dragon_type,
        "Stolen": "False",
        "KillerName": killer_name,
        "Assisters": [],
    }


def champion_kill_event(
    event_id: int, event_time: float, killer_name: str, victim_name: str, assisters: list[str]
) -> dict[str, JsonValue]:
    return {
        "EventID": event_id,
        "EventName": "ChampionKill",
        "EventTime": event_time,
        "KillerName": killer_name,
        "VictimName": victim_name,
        "Assisters": list[JsonValue](assisters),
    }


def player_payload(seed: PlayerSeed) -> dict[str, JsonValue]:
    return {
        "championName": seed.champion_name,
        "isBot": False,
        "isDead": seed.is_dead,
        "items": [
            {
                "canUse": False,
                "consumable": False,
                "count": 1,
                "displayName": display_name,
                "itemID": item_id,
                "price": price,
                "rawDescription": f"GeneratedTip_Item_{item_id}_Description",
                "rawDisplayName": f"Item_{item_id}_Name",
                "slot": slot,
            }
            for slot, (item_id, display_name, price) in enumerate(seed.items)
        ],
        "level": seed.level,
        "position": seed.position,
        "rawChampionName": f"game_character_displayname_{seed.champion_name}",
        "respawnTimer": seed.respawn_timer_seconds,
        "riotId": seed.riot_id,
        "riotIdGameName": seed.riot_id_game_name,
        "riotIdTagLine": seed.riot_id_tag_line,
        "runes": {
            "keystone": {
                "displayName": "Electrocute",
                "id": 8112,
                "rawDescription": "perk_tooltip_Electrocute",
                "rawDisplayName": "perk_displayname_Electrocute",
            },
            "primaryRuneTree": {
                "displayName": "Domination",
                "id": 8100,
                "rawDescription": "perkstyle_tooltip_7200",
                "rawDisplayName": "perkstyle_displayname_7200",
            },
            "secondaryRuneTree": {
                "displayName": "Sorcery",
                "id": 8200,
                "rawDescription": "perkstyle_tooltip_7202",
                "rawDisplayName": "perkstyle_displayname_7202",
            },
        },
        "scores": {
            "assists": 0,
            "creepScore": seed.creep_score,
            "deaths": 0,
            "kills": 0,
            "wardScore": 0.0,
        },
        "skinID": 0,
        "summonerName": seed.riot_id,
        "summonerSpells": {
            "summonerSpellOne": {
                "displayName": seed.summoner_spells[0],
                "rawDescription": "",
                "rawDisplayName": "",
            },
            "summonerSpellTwo": {
                "displayName": seed.summoner_spells[1],
                "rawDescription": "",
                "rawDisplayName": "",
            },
        },
        "team": seed.team,
    }


def all_game_data(
    game_time_seconds: float,
    events: list[dict[str, JsonValue]] | None = None,
    players: tuple[PlayerSeed, ...] = DEFAULT_PLAYERS,
    active_player_index: int = ACTIVE_PLAYER_INDEX,
    map_terrain: str = "Default",
) -> JsonValue:
    active_seed = players[active_player_index]
    return {
        "activePlayer": {
            "abilities": {
                key: {
                    "abilityLevel": 1,
                    "displayName": key,
                    "id": f"Ahri{key}",
                    "rawDescription": "",
                    "rawDisplayName": "",
                }
                for key in ("Q", "W", "E", "R")
            },
            "championStats": {
                "abilityHaste": 0.0,
                "abilityPower": 0.0,
                "armor": 21.0,
                "attackDamage": 53.0,
                "attackRange": 550.0,
                "attackSpeed": 0.668,
                "currentHealth": 590.0,
                "magicResist": 30.0,
                "maxHealth": 590.0,
                "moveSpeed": 330.0,
                "resourceType": "MANA",
                "resourceValue": 418.0,
            },
            "currentGold": 500.0,
            "fullRunes": {
                "generalRunes": [],
                "keystone": {},
                "primaryRuneTree": {},
                "secondaryRuneTree": {},
                "statRunes": [],
            },
            "level": active_seed.level,
            "riotId": active_seed.riot_id,
            "riotIdGameName": active_seed.riot_id_game_name,
            "riotIdTagLine": active_seed.riot_id_tag_line,
            "summonerName": active_seed.riot_id,
            "teamRelativeColors": True,
        },
        "allPlayers": [player_payload(seed) for seed in players],
        "events": {
            "Events": list[JsonValue](events if events is not None else [game_start_event()])
        },
        "gameData": {
            "gameMode": "CLASSIC",
            "gameTime": game_time_seconds,
            "mapName": "Map11",
            "mapNumber": 11,
            "mapTerrain": map_terrain,
        },
    }


GAME_ID: Final = 5123456789


def gameflow_session(phase: str = "InProgress") -> JsonValue:
    return {
        "phase": phase,
        "gameData": {
            "gameId": GAME_ID,
            "queue": {"id": 420, "description": "Ranked Solo/Duo"},
            "teamOne": [
                {
                    "summonerName": seed.riot_id,
                    "puuid": f"puuid-{seed.riot_id_game_name.lower().replace(' ', '-')}-0000",
                    "summonerId": 41000000 + index,
                    "championId": 103,
                }
                for index, seed in enumerate(DEFAULT_PLAYERS[:5])
            ],
            "teamTwo": [
                {
                    "summonerName": seed.riot_id,
                    "puuid": f"puuid-{seed.riot_id_game_name.lower().replace(' ', '-')}-0000",
                    "summonerId": 42000000 + index,
                    "championId": 238,
                }
                for index, seed in enumerate(DEFAULT_PLAYERS[5:])
            ],
        },
    }
