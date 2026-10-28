"""A game as the League client tells it after the game: its players and every exhibit (phase 10.2).

The client's game details (`/lol-match-history/v1/games/<id>`) give each player's line of the
scoreboard and each team's objectives; its timeline gives every player's numbers once a minute and
the game's events (`roast/client_timeline.py`). Every exhibit cites the path of its value in the
answer it came from. A field the answer does not hold gives no exhibit and no line, never a zero.

The details' shape is the client's older one: stats nested under each participant, who each player
is in a list of its own, and a team's result as "Win" or "Fail". It has not been seen in a real
game yet (the plan's slice 10.0); the readers take what is there.
"""

from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue

from leagueasymode.roast.client_json import (
    as_flag,
    as_list,
    as_object,
    as_text,
    as_whole_number,
)
from leagueasymode.roast.client_timeline import timeline_exhibits
from leagueasymode.roast.exhibits import Exhibit, ExhibitLedger, ExhibitSource
from leagueasymode.roast.numbers import format_clock, format_count, format_percent
from leagueasymode.roast.players import RoastPlayer
from leagueasymode.roast.rules import LaneRules

UNKNOWN_CHAMPION: Final = "unknown champion"
TEAM_IDS: Final = (100, 200)
# The scoreboard's counts every case needs: the exhibit's name, the stats field, and its unit.
SCOREBOARD_COUNTS: Final = (
    ("kills", "kills", "kills"),
    ("deaths", "deaths", "deaths"),
    ("assists", "assists", "assists"),
    ("vision_score", "visionScore", "vision score"),
    ("control_wards", "detectorWardsPlaced", "control wards"),
    ("enemy_missing_pings", "enemyMissingPings", "pings"),
    ("all_in_pings", "allInPings", "pings"),
    ("damage_to_champions", "totalDamageDealtToChampions", "damage to champions"),
)
# The scoreboard's durations, in seconds, written as a clock.
SCOREBOARD_DURATIONS: Final = (
    ("time_dead", "totalTimeSpentDead", "dead"),
    ("longest_alive", "longestTimeSpentLiving", "alive"),
)
# Each team's objectives: the exhibit's name, the team field, and the objective's plural.
TEAM_OBJECTIVES: Final = (
    ("dragons", "dragonKills", "dragons"),
    ("barons", "baronKills", "Barons"),
    ("towers", "towerKills", "towers"),
    ("heralds", "riftHeraldKills", "Rift Heralds"),
    ("grubs", "hordeKills", "void grubs"),
)
# The position Riot's lane and role name, when a participant has no team position.
POSITION_BY_LANE: Final = {"TOP": "TOP", "JUNGLE": "JUNGLE", "MIDDLE": "MIDDLE", "MID": "MIDDLE"}


class ClientGame(BaseModel):
    """One game, ready for the roast."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    players: tuple[RoastPlayer, ...]
    ledger: ExhibitLedger
    remade: bool


def champion_names(summary_payload: JsonValue | None) -> dict[int, str]:
    """Return each champion's name as people write it, by id, from the client's champion summary.

    Args:
        summary_payload: The answer of `/lol-game-data/assets/v1/champion-summary.json`.

    Returns:
        The names, such as {64: "Lee Sin"}; empty when the answer cannot be read.
    """
    names: dict[int, str] = {}
    for entry in as_list(summary_payload):
        entry_object = as_object(entry) or {}
        champion_id = as_whole_number(entry_object.get("id"))
        name = as_text(entry_object.get("name"))
        if champion_id is not None and champion_id > 0 and name:
            names[champion_id] = name
    return names


def participant_id_of(details_payload: JsonValue | None, puuid: str) -> int | None:
    """Return the participant id of a player in a game, by their PUUID.

    Args:
        details_payload: The game's details.
        puuid: The player.

    Returns:
        Their participant id, or None when the details do not name them.
    """
    details = as_object(details_payload) or {}
    for identity in as_list(details.get("participantIdentities")):
        identity_object = as_object(identity) or {}
        player = as_object(identity_object.get("player")) or {}
        if as_text(player.get("puuid")) == puuid:
            return as_whole_number(identity_object.get("participantId"))
    return None


def read_client_game(
    details_payload: JsonValue | None,
    timeline_payload: JsonValue | None,
    *,
    names_by_champion_id: dict[int, str],
    friend_riot_ids: frozenset[str] = frozenset(),
    lane_rules: LaneRules,
) -> ClientGame:
    """Build a game's players and exhibits from the client's answers.

    Args:
        details_payload: The game's details, from `/lol-match-history/v1/games/<id>`.
        timeline_payload: The game's timeline, or None when it has not come.
        names_by_champion_id: Champions' names, by id (`champion_names`).
        friend_riot_ids: The owner's friends' Riot IDs, as "name#tag" in lower case.
        lane_rules: Our thresholds for a lane's outcome.

    Returns:
        The game.
    """
    details = as_object(details_payload) or {}
    game_id = as_whole_number(details.get("gameId")) or 0
    participants = [as_object(entry) or {} for entry in as_list(details.get("participants"))]
    players = _players(details, participants, names_by_champion_id, friend_riot_ids)
    exhibits = [
        *_scoreboard_exhibits(participants, players),
        *_team_exhibits(details),
        *_game_exhibits(details, participants),
    ]
    scoreboard_by_key = {exhibit.key: exhibit for exhibit in exhibits}
    exhibits_by_key = {**scoreboard_by_key, **_share_exhibits(players, scoreboard_by_key)}
    timeline_exhibit_list = timeline_exhibits(
        timeline_payload, list(players), exhibits_by_key, lane_rules
    )
    remade = any(
        as_flag((as_object(participant.get("stats")) or {}).get("gameEndedInEarlySurrender"))
        for participant in participants
    )
    return ClientGame(
        players=players,
        ledger=ExhibitLedger(
            game_id=game_id,
            exhibits={
                **exhibits_by_key,
                **{exhibit.key: exhibit for exhibit in timeline_exhibit_list},
            },
        ),
        remade=remade,
    )


def _players(
    details: dict[str, JsonValue],
    participants: list[dict[str, JsonValue]],
    names_by_champion_id: dict[int, str],
    friend_riot_ids: frozenset[str],
) -> tuple[RoastPlayer, ...]:
    """Return the game's players, in the details' order.

    Args:
        details: The game's details.
        participants: Its participants.
        names_by_champion_id: Champions' names, by id.
        friend_riot_ids: The owner's friends' Riot IDs, in lower case.

    Returns:
        The players; a participant with no id or team is left out.
    """
    riot_id_by_participant_id = _riot_ids(details)
    winning_team_ids = {
        as_whole_number(team_object.get("teamId"))
        for team in as_list(details.get("teams"))
        if (team_object := as_object(team)) is not None and as_text(team_object.get("win")) == "Win"
    }
    players: list[RoastPlayer] = []
    for participant in participants:
        participant_id = as_whole_number(participant.get("participantId"))
        team_id = as_whole_number(participant.get("teamId"))
        if participant_id is None or team_id is None:
            continue
        stats = as_object(participant.get("stats")) or {}
        stated_win = as_flag(stats.get("win"))
        champion_id = as_whole_number(participant.get("championId")) or 0
        players.append(
            RoastPlayer(
                participant_id=participant_id,
                team_id=team_id,
                position=_position(participant),
                champion=names_by_champion_id.get(champion_id, UNKNOWN_CHAMPION),
                won=stated_win if stated_win is not None else team_id in winning_team_ids,
                is_friend=riot_id_by_participant_id.get(participant_id, "") in friend_riot_ids,
            )
        )
    return tuple(players)


def _riot_ids(details: dict[str, JsonValue]) -> dict[int, str]:
    """Return each participant's Riot ID, "name#tag" in lower case, where the details name one.

    Args:
        details: The game's details.

    Returns:
        The Riot IDs, by participant id.
    """
    riot_ids: dict[int, str] = {}
    for identity in as_list(details.get("participantIdentities")):
        identity_object = as_object(identity) or {}
        player = as_object(identity_object.get("player")) or {}
        participant_id = as_whole_number(identity_object.get("participantId"))
        game_name = as_text(player.get("gameName"))
        tag_line = as_text(player.get("tagLine"))
        if participant_id is not None and game_name and tag_line:
            riot_ids[participant_id] = f"{game_name}#{tag_line}".lower()
    return riot_ids


def _position(participant: dict[str, JsonValue]) -> str:
    """Return a participant's position: the team position, or what their lane and role say.

    Args:
        participant: One participant of the details.

    Returns:
        "TOP", "JUNGLE", "MIDDLE", "BOTTOM" or "UTILITY"; empty when neither says.
    """
    team_position = as_text(participant.get("teamPosition"))
    if team_position:
        return team_position
    timeline = as_object(participant.get("timeline")) or {}
    lane = as_text(timeline.get("lane"))
    role = as_text(timeline.get("role"))
    if lane in POSITION_BY_LANE:
        return POSITION_BY_LANE[lane]
    if lane in ("BOTTOM", "BOT") and "SUPPORT" in role:
        return "UTILITY"
    if lane in ("BOTTOM", "BOT") and "CARRY" in role:
        return "BOTTOM"
    return ""


def _scoreboard_exhibits(
    participants: list[dict[str, JsonValue]], players: tuple[RoastPlayer, ...]
) -> list[Exhibit]:
    """Return each player's counts and durations from their line of the scoreboard.

    Args:
        participants: The details' participants.
        players: The game's players.

    Returns:
        One exhibit per field a player's stats hold.
    """
    champion_by_id = {player.participant_id: player.champion for player in players}
    exhibits: list[Exhibit] = []
    for index, participant in enumerate(participants):
        participant_id = as_whole_number(participant.get("participantId"))
        if participant_id not in champion_by_id or participant_id is None:
            continue
        stats = as_object(participant.get("stats")) or {}
        champion = champion_by_id[participant_id]
        for exhibit_name, field_name, unit in SCOREBOARD_COUNTS:
            count = as_whole_number(stats.get(field_name))
            if count is not None:
                exhibits.append(
                    Exhibit(
                        key=f"{exhibit_name}/p{participant_id}",
                        label=f"{champion}'s {unit}",
                        value=count,
                        display=format_count(count),
                        unit=unit,
                        source=ExhibitSource(
                            kind="game", path=f"participants[{index}].stats.{field_name}"
                        ),
                        participant_id=participant_id,
                    )
                )
        for exhibit_name, field_name, unit in SCOREBOARD_DURATIONS:
            seconds = as_whole_number(stats.get(field_name))
            if seconds is not None:
                exhibits.append(
                    Exhibit(
                        key=f"{exhibit_name}/p{participant_id}",
                        label=f"Time {champion} spent {unit}"
                        if unit == "dead"
                        else f"{champion}'s longest life",
                        value=seconds,
                        display=format_clock(seconds),
                        unit=unit,
                        source=ExhibitSource(
                            kind="game", path=f"participants[{index}].stats.{field_name}"
                        ),
                        participant_id=participant_id,
                    )
                )
    return exhibits


def _share_exhibits(
    players: tuple[RoastPlayer, ...], scoreboard_by_key: dict[str, Exhibit]
) -> dict[str, Exhibit]:
    """Return each team's kills, and each player's share of their team's kills and damage.

    Worked out here from the scoreboard, so each says its formula and inputs. A share needs every
    teammate's count, so a team missing one gets no share at all; nor does a team with none.

    Args:
        players: The game's players.
        scoreboard_by_key: The scoreboard's exhibits, by key.

    Returns:
        The exhibits, by key.
    """
    exhibits: list[Exhibit] = []
    for team_id in TEAM_IDS:
        team = [player for player in players if player.team_id == team_id]
        kill_keys = [f"kills/p{player.participant_id}" for player in team]
        damage_keys = [f"damage_to_champions/p{player.participant_id}" for player in team]
        side = "Blue side" if team_id == TEAM_IDS[0] else "Red side"
        if team and all(key in scoreboard_by_key for key in kill_keys):
            team_kills = sum(_count(scoreboard_by_key[key]) for key in kill_keys)
            team_kills_key = f"team_kills/t{team_id}"
            exhibits.append(
                Exhibit(
                    key=team_kills_key,
                    label=f"Kills {side} got",
                    value=team_kills,
                    display=format_count(team_kills),
                    unit="kills",
                    source=ExhibitSource(
                        kind="computation",
                        formula="the sum of the team's players' kills",
                        input_keys=tuple(kill_keys),
                    ),
                )
            )
            exhibits.extend(
                _share(
                    player,
                    name="kill_participation",
                    label="share of the team's kills",
                    part_keys=(
                        f"kills/p{player.participant_id}",
                        f"assists/p{player.participant_id}",
                    ),
                    whole_key=team_kills_key,
                    whole=team_kills,
                    formula="the player's kills plus assists, divided by the team's kills",
                    scoreboard_by_key=scoreboard_by_key,
                )
                for player in team
                if f"assists/p{player.participant_id}" in scoreboard_by_key and team_kills > 0
            )
        if team and all(key in scoreboard_by_key for key in damage_keys):
            team_damage = sum(_count(scoreboard_by_key[key]) for key in damage_keys)
            exhibits.extend(
                _share(
                    player,
                    name="damage_share",
                    label="share of the team's damage to champions",
                    part_keys=(f"damage_to_champions/p{player.participant_id}",),
                    whole_key=None,
                    whole=team_damage,
                    formula="the player's damage to champions, divided by the sum of their team's: "
                    + ", ".join(damage_keys),
                    scoreboard_by_key=scoreboard_by_key,
                    other_input_keys=tuple(damage_keys),
                )
                for player in team
                if team_damage > 0
            )
    return {exhibit.key: exhibit for exhibit in exhibits}


def _share(
    player: RoastPlayer,
    *,
    name: str,
    label: str,
    part_keys: tuple[str, ...],
    whole_key: str | None,
    whole: int,
    formula: str,
    scoreboard_by_key: dict[str, Exhibit],
    other_input_keys: tuple[str, ...] = (),
) -> Exhibit:
    """Return one player's share of a team's total, as a computation of ours.

    Args:
        player: The player.
        name: The exhibit's name, such as "kill_participation".
        label: What the share is of, for its label.
        part_keys: The player's exhibits that add up to their part.
        whole_key: The team total's exhibit, when there is one.
        whole: The team's total, above zero.
        formula: How it is worked out, in words.
        scoreboard_by_key: The scoreboard's exhibits, by key.
        other_input_keys: Any other exhibit the share was worked out from.

    Returns:
        The share, from 0 to 1, written as a percentage.
    """
    part = sum(_count(scoreboard_by_key[key]) for key in part_keys)
    share = part / whole
    input_keys = tuple(
        dict.fromkeys([*part_keys, *((whole_key,) if whole_key else ()), *other_input_keys])
    )
    return Exhibit(
        key=f"{name}/p{player.participant_id}",
        label=f"{player.champion}'s {label}",
        value=share,
        display=format_percent(share),
        unit=f"of the team's {'kills' if name == 'kill_participation' else 'damage'}",
        source=ExhibitSource(kind="computation", formula=formula, input_keys=input_keys),
        participant_id=player.participant_id,
    )


def _count(exhibit: Exhibit) -> int:
    """Return a scoreboard exhibit's whole number.

    Args:
        exhibit: A count from the scoreboard.

    Returns:
        Its value; 0 only if it is somehow not a whole number, which the readers never make.
    """
    return (
        exhibit.value
        if isinstance(exhibit.value, int) and not isinstance(exhibit.value, bool)
        else 0
    )


def _team_exhibits(details: dict[str, JsonValue]) -> list[Exhibit]:
    """Return each team's objectives.

    Args:
        details: The game's details.

    Returns:
        One exhibit per objective a team's answer counts.
    """
    exhibits: list[Exhibit] = []
    for team_index, team in enumerate(as_list(details.get("teams"))):
        team_object = as_object(team) or {}
        team_id = as_whole_number(team_object.get("teamId"))
        if team_id not in TEAM_IDS:
            continue
        side = "Blue side" if team_id == TEAM_IDS[0] else "Red side"
        for exhibit_name, field_name, plural in TEAM_OBJECTIVES:
            count = as_whole_number(team_object.get(field_name))
            if count is not None:
                exhibits.append(
                    Exhibit(
                        key=f"{exhibit_name}/t{team_id}",
                        label=f"{plural[0].upper()}{plural[1:]} {side} took",
                        value=count,
                        display=format_count(count),
                        unit=plural,
                        source=ExhibitSource(kind="game", path=f"teams[{team_index}].{field_name}"),
                    )
                )
    return exhibits


def _game_exhibits(
    details: dict[str, JsonValue], participants: list[dict[str, JsonValue]]
) -> list[Exhibit]:
    """Return the game's length, and that it ended in a surrender when it did.

    Args:
        details: The game's details.
        participants: Its participants.

    Returns:
        Up to two exhibits.
    """
    duration_seconds = as_whole_number(details.get("gameDuration"))
    length = (
        [
            Exhibit(
                key="game_length",
                label="How long the game lasted",
                value=duration_seconds,
                display=format_clock(duration_seconds),
                unit="game clock",
                source=ExhibitSource(kind="game", path="gameDuration"),
            )
        ]
        if duration_seconds is not None
        else []
    )
    flagged_indexes = [
        index
        for index, participant in enumerate(participants)
        if as_flag((as_object(participant.get("stats")) or {}).get("gameEndedInSurrender"))
    ]
    remade = any(
        as_flag((as_object(participant.get("stats")) or {}).get("gameEndedInEarlySurrender"))
        for participant in participants
    )
    surrender = (
        [
            Exhibit(
                key="surrender",
                label="Whether the game ended in a surrender",
                value=True,
                display="surrendered",
                unit="",
                source=ExhibitSource(
                    kind="game",
                    path=f"participants[{flagged_indexes[0]}].stats.gameEndedInSurrender",
                ),
            )
        ]
        if flagged_indexes and not remade
        else []
    )
    return [*length, *surrender]
