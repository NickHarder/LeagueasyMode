"""The last game, kept for its case (phase 11.3): its players, its exhibits and who played here.

After each game, `leagueasymode run` reads the client's details and timeline from the recording
(`roast/client_game.py`) and keeps them beside the last game's summary. The post-game window then
asks `/case` for a case about any target at any spice level, and the case is built from this file
on each ask, so a new target or another take costs nothing to keep.

The file holds no one's name or Riot ID: players are their champions, and a friend is a flag.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue

from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.gold import player_key
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH
from leagueasymode.player_intel import champion_aliases
from leagueasymode.roast.client_game import (
    ClientGame,
    champion_names,
    participant_id_by_riot_id,
    read_client_game,
)
from leagueasymode.roast.client_json import as_list, as_object, as_whole_number
from leagueasymode.roast.rules import LaneRules
from leagueasymode.scoring import (
    GAME_DETAILS_PATH_PREFIX,
    TIMELINE_PATH_PREFIX,
    this_games_resource,
)

TEAM_BY_ID: Final = {100: "ORDER", 200: "CHAOS"}
PLAYERS_PER_TEAM: Final = 5
ROAST_FILE_SUFFIX: Final = "-roast.json"


class LastGameRoast(BaseModel):
    """What the case of the last game is built from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game: ClientGame
    # The player on this machine, whose side is "our team".
    defendant_participant_id: int
    # A quick case from the end-of-game stats (phase 11.7), until the details and timeline come.
    is_quick: bool = False


def roast_path_beside(summary_path: Path) -> Path:
    """Return where the last game's roast is kept: beside its summary.

    Args:
        summary_path: The last game's summary.

    Returns:
        The path, such as `last-game-roast.json` beside `last-game.json`.
    """
    return summary_path.with_name(f"{summary_path.stem}{ROAST_FILE_SUFFIX}")


def last_game_roast(
    client_resources: Mapping[str, JsonValue],
    last_snapshot: GameSnapshot | None,
    *,
    lane_rules: LaneRules,
    friend_riot_ids: frozenset[str] = frozenset(),
) -> LastGameRoast | None:
    """Return what a recorded game's case is built from.

    Args:
        client_resources: The client's latest answer for each path the recording asked.
        last_snapshot: The game's last answer, which says who played on this machine.
        lane_rules: Our thresholds for a lane's outcome.
        friend_riot_ids: The owner's friends' Riot IDs, as "name#tag" in lower case.

    Returns:
        The game and its defendant; None without the game's details, when it was not two teams
        of five (Arena), or when the player on this machine cannot be found in it.
    """
    details = this_games_resource(client_resources, GAME_DETAILS_PATH_PREFIX)
    if as_object(details) is None or last_snapshot is None:
        return None
    game = read_client_game(
        details,
        this_games_resource(client_resources, TIMELINE_PATH_PREFIX),
        names_by_champion_id=champion_names(client_resources.get(CHAMPION_SUMMARY_PATH)),
        friend_riot_ids=friend_riot_ids,
        lane_rules=lane_rules,
    )
    team_sizes = [
        sum(1 for player in game.players if player.team_id == team_id) for team_id in TEAM_BY_ID
    ]
    if team_sizes != [PLAYERS_PER_TEAM, PLAYERS_PER_TEAM]:
        return None
    defendant_id = _defendant_id(
        details, last_snapshot, client_resources.get(CHAMPION_SUMMARY_PATH)
    )
    if defendant_id is None:
        return None
    return LastGameRoast(game=game, defendant_participant_id=defendant_id)


def _defendant_id(
    details: JsonValue, snapshot: GameSnapshot, champion_summary: JsonValue | None
) -> int | None:
    """Return the participant id of the player on this machine.

    By their Riot ID where the details name the players; otherwise by their team and champion,
    which no two players of a team share in a game of two teams of five.

    Args:
        details: The game's details.
        snapshot: An answer of the game's API.
        champion_summary: The client's champion summary, for each champion's alias.

    Returns:
        The participant id, or None when neither way finds them.
    """
    active_player = snapshot.active_player
    if active_player is None:
        return None
    by_riot_id = participant_id_by_riot_id(details, active_player.riot_id)
    if by_riot_id is not None:
        return by_riot_id
    own_keys = [
        player_key(player) for player in snapshot.players if snapshot.is_active_player(player)
    ]
    if not own_keys:
        return None
    alias_by_champion_id = champion_aliases(champion_summary)
    details_object = as_object(details) or {}
    for participant in as_list(details_object.get("participants")):
        participant_object = as_object(participant) or {}
        team = TEAM_BY_ID.get(as_whole_number(participant_object.get("teamId")) or 0)
        alias = alias_by_champion_id.get(as_whole_number(participant_object.get("championId")) or 0)
        if team is not None and alias is not None and (team, alias.lower()) == own_keys[0]:
            return as_whole_number(participant_object.get("participantId"))
    return None
