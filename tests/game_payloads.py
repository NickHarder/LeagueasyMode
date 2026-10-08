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


# Data Dragon's id of each summoner spell, by the name the game shows.
SUMMONER_SPELL_IDS: Final = {
    "Flash": "SummonerFlash",
    "Ignite": "SummonerDot",
    "Teleport": "SummonerTeleport",
    "Smite": "SummonerSmite",
    "Heal": "SummonerHeal",
    "Exhaust": "SummonerExhaust",
    "Barrier": "SummonerBarrier",
    "Cleanse": "SummonerBoost",
    "Ghost": "SummonerHaste",
}


def raw_summoner_spell_name(display_name: str) -> str:
    spell_id = SUMMONER_SPELL_IDS.get(display_name, display_name)
    return f"GeneratedTip_SummonerSpell_{spell_id}_DisplayName"


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
                "rawDisplayName": raw_summoner_spell_name(seed.summoner_spells[0]),
            },
            "summonerSpellTwo": {
                "displayName": seed.summoner_spells[1],
                "rawDescription": "",
                "rawDisplayName": raw_summoner_spell_name(seed.summoner_spells[1]),
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
    current_gold: float = 500.0,
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
            "currentGold": current_gold,
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


# The client's champion ids, by the alias the game uses in `rawChampionName`.
CHAMPION_IDS: Final = {
    "Garen": 86,
    "LeeSin": 64,
    "Ahri": 103,
    "Jinx": 222,
    "Thresh": 412,
    "Darius": 122,
    "Vi": 254,
    "Zed": 238,
    "Caitlyn": 51,
    "Lux": 99,
}


def puuid_of(seed: PlayerSeed) -> str:
    return f"puuid-{seed.riot_id_game_name.lower().replace(' ', '-')}-0000"


def champion_summary() -> JsonValue:
    champions: list[JsonValue] = [{"id": -1, "name": "None", "alias": "None"}]
    champions.extend(
        {"id": champion_id, "name": alias, "alias": alias}
        for alias, champion_id in CHAMPION_IDS.items()
    )
    return champions


def gameflow_session(phase: str = "InProgress") -> JsonValue:
    return {
        "phase": phase,
        "gameData": {
            "gameId": GAME_ID,
            "queue": {"id": 420, "description": "Ranked Solo/Duo"},
            "teamOne": [
                {
                    "summonerName": seed.riot_id,
                    "puuid": puuid_of(seed),
                    "summonerId": 41000000 + index,
                    "championId": CHAMPION_IDS[seed.champion_name],
                }
                for index, seed in enumerate(DEFAULT_PLAYERS[:5])
            ],
            "teamTwo": [
                {
                    "summonerName": seed.riot_id,
                    "puuid": puuid_of(seed),
                    "summonerId": 42000000 + index,
                    "championId": CHAMPION_IDS[seed.champion_name],
                }
                for index, seed in enumerate(DEFAULT_PLAYERS[5:])
            ],
        },
    }


def ranked_stats(tier: str, division: str, league_points: int, wins: int, losses: int) -> JsonValue:
    solo_entry: dict[str, JsonValue] = {
        "queueType": "RANKED_SOLO_5x5",
        "tier": tier,
        "division": division,
        "leaguePoints": league_points,
        "wins": wins,
        "losses": losses,
        "isProvisional": False,
    }
    flex_entry: dict[str, JsonValue] = {
        "queueType": "RANKED_FLEX_SR",
        "tier": "",
        "division": "NA",
        "leaguePoints": 0,
        "wins": 0,
        "losses": 0,
        "isProvisional": False,
    }
    return {
        "queues": [solo_entry, flex_entry],
        "queueMap": {"RANKED_SOLO_5x5": solo_entry, "RANKED_FLEX_SR": flex_entry},
    }


@dataclass(frozen=True)
class PastGame:
    """One game of a player's history: what they played, where, and whether they won."""

    champion_id: int
    lane: str
    role: str
    is_win: bool
    map_id: int = 11
    duration_seconds: int = 1800
    item_ids: tuple[int, ...] = ()


def match_history(puuid: str, past_games: list[PastGame]) -> JsonValue:
    return {
        "accountId": 9000001,
        "platformId": "NA1",
        "games": {
            "gameCount": len(past_games),
            "games": [
                {
                    "gameId": 5000000000 + index,
                    "gameCreation": 1790000000000 - index * 3600000,
                    "gameDuration": past_game.duration_seconds,
                    "gameMode": "CLASSIC",
                    "mapId": past_game.map_id,
                    "queueId": 420,
                    "participantIdentities": [
                        {"participantId": 1, "player": {"puuid": puuid, "accountId": 9000001}}
                    ],
                    "participants": [
                        {
                            "participantId": 1,
                            "championId": past_game.champion_id,
                            "teamId": 100,
                            "stats": {
                                "win": past_game.is_win,
                                "kills": 5,
                                "deaths": 3,
                                **{
                                    f"item{slot}": item_id
                                    for slot, item_id in enumerate(past_game.item_ids)
                                },
                            },
                            "timeline": {"lane": past_game.lane, "role": past_game.role},
                        }
                    ],
                }
                for index, past_game in enumerate(past_games)
            ],
        },
    }


def baron_kill_event(event_id: int, event_time: float, killer_name: str) -> dict[str, JsonValue]:
    return {
        "EventID": event_id,
        "EventName": "BaronKill",
        "EventTime": event_time,
        "Stolen": "False",
        "KillerName": killer_name,
        "Assisters": [],
    }


def herald_kill_event(event_id: int, event_time: float, killer_name: str) -> dict[str, JsonValue]:
    return {
        "EventID": event_id,
        "EventName": "HeraldKill",
        "EventTime": event_time,
        "Stolen": "False",
        "KillerName": killer_name,
        "Assisters": [],
    }


def inhibitor_killed_event(
    event_id: int, event_time: float, inhibitor_name: str, killer_name: str
) -> dict[str, JsonValue]:
    return {
        "EventID": event_id,
        "EventName": "InhibKilled",
        "EventTime": event_time,
        "InhibKilled": inhibitor_name,
        "KillerName": killer_name,
        "Assisters": [],
    }


def inhibitor_respawned_event(
    event_id: int, event_time: float, inhibitor_name: str
) -> dict[str, JsonValue]:
    return {
        "EventID": event_id,
        "EventName": "InhibRespawned",
        "EventTime": event_time,
        "InhibRespawned": inhibitor_name,
    }


def turret_killed_event(
    event_id: int,
    event_time: float,
    turret_name: str,
    killer_name: str,
    assisters: list[str] | None = None,
) -> dict[str, JsonValue]:
    return {
        "EventID": event_id,
        "EventName": "TurretKilled",
        "EventTime": event_time,
        "TurretKilled": turret_name,
        "KillerName": killer_name,
        "Assisters": list[JsonValue](assisters or []),
    }
