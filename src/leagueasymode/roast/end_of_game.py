"""A quick case from the end-of-game stats (phase 11.7), before the timeline comes.

Right after a game the League client gives its end-of-game stats
(`/lol-end-of-game/v1/eog-stats-block`); the match timeline and the game's details come a minute
or more later. This reads the stats into the same players and scoreboard exhibits as the details
give (`client_game.py`), so a case can be built at once: scoreboard lines and no lane verdict,
since lanes need the timeline. The full case replaces it when the details and timeline come
(`last_game.py`).

The stats' shape has not been seen in a real game yet (the plan's slice 11.0); it is read as the
client is commonly documented to send it: two teams, each with its players, each player's counters
under `stats` in capitals ("CHAMPIONS_KILLED"). A field it does not hold gives no exhibit, and a
game whose champions cannot be named gives no quick case, rather than lines about an "unknown
champion".
"""

from collections.abc import Sequence
from typing import Final

from pydantic import JsonValue

from leagueasymode.roast.client_game import ClientGame, share_exhibits
from leagueasymode.roast.client_json import as_flag, as_list, as_object, as_text, as_whole_number
from leagueasymode.roast.exhibits import Exhibit, ExhibitLedger, ExhibitSource
from leagueasymode.roast.last_game import PLAYERS_PER_TEAM, LastGameRoast
from leagueasymode.roast.numbers import format_clock, format_count
from leagueasymode.roast.players import RoastPlayer

# The counters a case needs: the exhibit's name, the stats field, and its unit, as `client_game`.
COUNTERS: Final = (
    ("kills", "CHAMPIONS_KILLED", "kills"),
    ("deaths", "NUM_DEATHS", "deaths"),
    ("assists", "ASSISTS", "assists"),
    ("vision_score", "VISION_SCORE", "vision score"),
    ("damage_to_champions", "TOTAL_DAMAGE_DEALT_TO_CHAMPIONS", "damage to champions"),
)
TIME_DEAD_FIELD: Final = "TOTAL_TIME_SPENT_DEAD"
TEAM_IDS: Final = (100, 200)
# The positions the stats may name, as the game names them.
POSITION_BY_NAME: Final = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MIDDLE",
    "MID": "MIDDLE",
    "BOTTOM": "BOTTOM",
    "BOT": "BOTTOM",
    "ADC": "BOTTOM",
    "UTILITY": "UTILITY",
    "SUPPORT": "UTILITY",
}


def quick_game_roast(
    stats_payload: JsonValue | None,
    *,
    names_by_champion_id: dict[int, str] | None = None,
    friend_riot_ids: frozenset[str] = frozenset(),
) -> LastGameRoast | None:
    """Return a quick case's game from the end-of-game stats.

    Args:
        stats_payload: The answer of `/lol-end-of-game/v1/eog-stats-block`.
        names_by_champion_id: Champions' names, by id, for a player the stats do not name.
        friend_riot_ids: The owner's friends' Riot IDs, as "name#tag" in lower case.

    Returns:
        The game, marked quick, with the player on this machine as the defendant; None when the
        stats are not two teams of five, a champion cannot be named, or the player here is not
        found.
    """
    stats = as_object(stats_payload) or {}
    names = names_by_champion_id or {}
    entries = [
        (team_index, team_id, player_index, as_object(entry) or {})
        for team_index, team in enumerate(as_list(stats.get("teams")))
        for team_id in (as_whole_number((as_object(team) or {}).get("teamId")),)
        if team_id in TEAM_IDS
        for player_index, entry in enumerate(as_list((as_object(team) or {}).get("players")))
    ]
    team_sizes = [sum(1 for entry in entries if entry[1] == team_id) for team_id in TEAM_IDS]
    if team_sizes != [PLAYERS_PER_TEAM, PLAYERS_PER_TEAM]:
        return None
    winning_team_ids = {
        as_whole_number(team_object.get("teamId"))
        for team in as_list(stats.get("teams"))
        if (team_object := as_object(team)) is not None
        and as_flag(team_object.get("isWinningTeam"))
    }
    players: list[RoastPlayer] = []
    exhibits: list[Exhibit] = []
    for participant_id, (team_index, team_id, player_index, entry) in enumerate(entries, start=1):
        champion = as_text(entry.get("championName")) or names.get(
            as_whole_number(entry.get("championId")) or 0, ""
        )
        if not champion or team_id is None:
            return None
        player = RoastPlayer(
            participant_id=participant_id,
            team_id=team_id,
            position=POSITION_BY_NAME.get(_position_name(entry), ""),
            champion=champion,
            won=team_id in winning_team_ids,
            is_friend=_riot_id(entry) in friend_riot_ids,
        )
        players.append(player)
        exhibits.extend(
            _counter_exhibits(player, entry, f"teams[{team_index}].players[{player_index}]")
        )
    defendant_id = _local_participant_id(stats, entries)
    if defendant_id is None:
        return None
    scoreboard_by_key = {exhibit.key: exhibit for exhibit in exhibits}
    game_length = _game_length(stats)
    game = ClientGame(
        players=tuple(players),
        ledger=ExhibitLedger(
            game_id=as_whole_number(stats.get("gameId")) or 0,
            exhibits={
                **scoreboard_by_key,
                **share_exhibits(tuple(players), scoreboard_by_key),
                **({game_length.key: game_length} if game_length is not None else {}),
            },
        ),
        remade=False,
    )
    return LastGameRoast(game=game, defendant_participant_id=defendant_id, is_quick=True)


def _position_name(entry: dict[str, JsonValue]) -> str:
    """Return the position a player's stats name, in capitals; empty when none."""
    for field_name in ("detectedTeamPosition", "selectedPosition", "position"):
        name = as_text(entry.get(field_name)).upper()
        if name in POSITION_BY_NAME:
            return name
    return ""


def _riot_id(entry: dict[str, JsonValue]) -> str:
    """Return a player's Riot ID, "name#tag" in lower case; empty when the stats give none."""
    game_name = as_text(entry.get("riotIdGameName"))
    tag_line = as_text(entry.get("riotIdTagLine"))
    if game_name and tag_line:
        return f"{game_name}#{tag_line}".lower()
    summoner_name = as_text(entry.get("summonerName"))
    return summoner_name.lower() if "#" in summoner_name else ""


def _counter_exhibits(
    player: RoastPlayer, entry: dict[str, JsonValue], player_path: str
) -> list[Exhibit]:
    """Return a player's counters and time dead, each citing its path in the stats."""
    counters = as_object(entry.get("stats")) or {}
    exhibits: list[Exhibit] = []
    for exhibit_name, field_name, unit in COUNTERS:
        count = as_whole_number(counters.get(field_name))
        if count is not None:
            exhibits.append(
                Exhibit(
                    key=f"{exhibit_name}/p{player.participant_id}",
                    label=f"{player.champion}'s {unit}",
                    value=count,
                    display=format_count(count),
                    unit=unit,
                    source=ExhibitSource(kind="game", path=f"{player_path}.stats.{field_name}"),
                    participant_id=player.participant_id,
                )
            )
    seconds_dead = as_whole_number(counters.get(TIME_DEAD_FIELD))
    if seconds_dead is not None:
        exhibits.append(
            Exhibit(
                key=f"time_dead/p{player.participant_id}",
                label=f"Time {player.champion} spent dead",
                value=seconds_dead,
                display=format_clock(seconds_dead),
                unit="dead",
                source=ExhibitSource(kind="game", path=f"{player_path}.stats.{TIME_DEAD_FIELD}"),
                participant_id=player.participant_id,
            )
        )
    return exhibits


def _local_participant_id(
    stats: dict[str, JsonValue],
    entries: Sequence[tuple[int, int | None, int, dict[str, JsonValue]]],
) -> int | None:
    """Return the participant id of the player on this machine, by PUUID or by summoner name."""
    local = as_object(stats.get("localPlayer")) or {}
    for field_name in ("puuid", "summonerName"):
        wanted = as_text(local.get(field_name))
        if not wanted:
            continue
        for participant_id, (_, _, _, entry) in enumerate(entries, start=1):
            if as_text(entry.get(field_name)) == wanted:
                return participant_id
    return None


def _game_length(stats: dict[str, JsonValue]) -> Exhibit | None:
    """Return the game's length, when the stats give it."""
    seconds = as_whole_number(stats.get("gameLength"))
    if seconds is None:
        return None
    return Exhibit(
        key="game_length",
        label="How long the game lasted",
        value=seconds,
        display=format_clock(seconds),
        unit="game clock",
        source=ExhibitSource(kind="game", path="gameLength"),
    )
