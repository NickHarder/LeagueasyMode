"""Each player's record before the game, from the League client: their rank and recent games.

The client's gameflow session lists every player in the game by PUUID, and the client can look up
any of them: their ranked stats and their recent match history. It asks Riot with its own session,
so no developer key is involved. To stay gentle on the client and on Riot, each player is asked
about once, one request at a time with a pause between, and the answers are kept for the engine's
lifetime, so a player met again in a later game is not asked again. A player the client will not
answer for is left out of this game and asked again at the next.

The shapes read here are the client's as other tools describe them; the recorder keeps each answer
so the first recorded game confirms them.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import Field, JsonValue, TypeAdapter, ValidationError

from leagueasymode.game_state import RiotPayloadModel
from leagueasymode.league_client import GAMEFLOW_SESSION_PATH, LeagueClient
from leagueasymode.overlay_state import RankedStanding
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH

RANKED_STATS_PATH_TEMPLATE: Final = "/lol-ranked/v1/ranked-stats/{puuid}"
RECENT_GAME_COUNT: Final = 20
MATCH_HISTORY_PATH_TEMPLATE: Final = (
    "/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex="
    + str(RECENT_GAME_COUNT)
)
# The questions about players, whose answers the engine and the recorder share.
PLAYER_LOOKUP_PATH_PREFIXES: Final = (
    "/lol-ranked/v1/ranked-stats/",
    "/lol-match-history/v1/products/lol/",
)
DEFAULT_PAUSE_SECONDS: Final = 0.25
# Solo queue first: its rank is the one a player is known by.
RANKED_QUEUES: Final[tuple[tuple[str, Literal["solo", "flex"]], ...]] = (
    ("RANKED_SOLO_5x5", "solo"),
    ("RANKED_FLEX_SR", "flex"),
)
RANKED_TIERS: Final = frozenset(
    {
        "IRON",
        "BRONZE",
        "SILVER",
        "GOLD",
        "PLATINUM",
        "EMERALD",
        "DIAMOND",
        "MASTER",
        "GRANDMASTER",
        "CHALLENGER",
    }
)
SUMMONERS_RIFT_MAP_ID: Final = 11
# A game shorter than this was remade, and says nothing about the player.
SHORTEST_COUNTED_GAME_SECONDS: Final = 300
POSITIONS: Final = frozenset({"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"})
TEAM_ONE: Final = "ORDER"
TEAM_TWO: Final = "CHAOS"

logger = logging.getLogger(__name__)


class RankedEntry(RiotPayloadModel):
    """One queue of the client's ranked stats."""

    queue_type: str = Field(default="", alias="queueType")
    tier: str = ""
    division: str = ""
    league_points: int = Field(default=0, alias="leaguePoints")
    wins: int = 0
    losses: int = 0


class RankedStats(RiotPayloadModel):
    """The client's answer for a player's ranked stats: each queue, as a list and by name."""

    queues: list[RankedEntry] = Field(default_factory=list)
    queue_map: dict[str, RankedEntry] = Field(default_factory=dict, alias="queueMap")


class HistoryStats(RiotPayloadModel):
    """A participant's end-of-game stats: the result and the inventory."""

    win: bool = False
    item0: int = 0
    item1: int = 0
    item2: int = 0
    item3: int = 0
    item4: int = 0
    item5: int = 0
    item6: int = 0

    def item_ids(self) -> tuple[int, ...]:
        """Return the items held at the game's end.

        Returns:
            Their ids, empty slots left out.
        """
        slots = (self.item0, self.item1, self.item2, self.item3, self.item4, self.item5, self.item6)
        return tuple(item_id for item_id in slots if item_id)


class HistoryTimeline(RiotPayloadModel):
    """Where a participant played, as the match history guesses it."""

    lane: str = ""
    role: str = ""


class HistoryParticipant(RiotPayloadModel):
    """One player's line in a past game."""

    participant_id: int = Field(default=0, alias="participantId")
    champion_id: int = Field(default=0, alias="championId")
    team_position: str = Field(default="", alias="teamPosition")
    stats: HistoryStats = Field(default_factory=HistoryStats)
    timeline: HistoryTimeline = Field(default_factory=HistoryTimeline)


class HistoryPlayer(RiotPayloadModel):
    """Who a participant was."""

    puuid: str = ""


class HistoryIdentity(RiotPayloadModel):
    """A participant's id paired with who they were."""

    participant_id: int = Field(default=0, alias="participantId")
    player: HistoryPlayer = Field(default_factory=HistoryPlayer)


class HistoryGame(RiotPayloadModel):
    """One past game."""

    game_creation: int = Field(default=0, alias="gameCreation")
    game_duration_seconds: int = Field(default=0, alias="gameDuration")
    map_id: int = Field(default=0, alias="mapId")
    participants: list[HistoryParticipant] = Field(default_factory=list)
    participant_identities: list[HistoryIdentity] = Field(
        default_factory=list, alias="participantIdentities"
    )

    def line_of(self, puuid: str) -> HistoryParticipant | None:
        """Return the looked-up player's line in this game.

        Args:
            puuid: The player.

        Returns:
            Their line: the participant their identity names, or the only one when the answer
            holds just theirs without naming them; None otherwise.
        """
        participant_id = next(
            (
                identity.participant_id
                for identity in self.participant_identities
                if identity.player.puuid == puuid
            ),
            None,
        )
        if participant_id is not None:
            return next(
                (line for line in self.participants if line.participant_id == participant_id),
                None,
            )
        if not self.participant_identities and len(self.participants) == 1:
            return self.participants[0]
        return None


class HistoryGames(RiotPayloadModel):
    """The list of past games."""

    games: list[HistoryGame] = Field(default_factory=list)


class MatchHistory(RiotPayloadModel):
    """The client's answer for a player's recent games."""

    games: HistoryGames = Field(default_factory=HistoryGames)


class GameflowPlayer(RiotPayloadModel):
    """One player of the game in progress, as the client's gameflow session lists them."""

    puuid: str = ""
    champion_id: int = Field(default=0, alias="championId")


class GameflowGameData(RiotPayloadModel):
    """The game in progress: each team's players."""

    team_one: list[GameflowPlayer] = Field(default_factory=list, alias="teamOne")
    team_two: list[GameflowPlayer] = Field(default_factory=list, alias="teamTwo")


class GameflowSession(RiotPayloadModel):
    """The client's gameflow session."""

    game_data: GameflowGameData = Field(default_factory=GameflowGameData, alias="gameData")


class ChampionSummaryEntry(RiotPayloadModel):
    """One champion of the client's champion summary: its id and the alias the game uses."""

    champion_id: int = Field(alias="id")
    alias: str = ""


CHAMPION_SUMMARY_ADAPTER: Final = TypeAdapter[list[ChampionSummaryEntry]](
    list[ChampionSummaryEntry]
)


@dataclass(frozen=True)
class RecentGame:
    """One of a player's recent games: what they played, where, what they built, and the result."""

    champion_id: int
    position: str
    is_win: bool
    # The items they held at its end.
    item_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class PlayerRecord:
    """A player's rank and recent games, newest first."""

    ranked: RankedStanding | None
    recent_games: tuple[RecentGame, ...]


@dataclass(frozen=True)
class GamePlayerRecord:
    """A player's record, with the champion they play in this game."""

    champion_id: int
    record: PlayerRecord


# Each player's record by their team ("ORDER" or "CHAOS") and their champion's alias in lowercase,
# which is how the game's scoreboard can be matched to the client's list.
type PlayerRecords = dict[tuple[str, str], GamePlayerRecord]


def ranked_standing_of(payload: JsonValue | None) -> RankedStanding | None:
    """Return a player's solo queue rank, or their flex rank when solo has none.

    Args:
        payload: The client's answer for the player's ranked stats, or None.

    Returns:
        The standing, or None when the player is unranked in both or the answer cannot be read.
    """
    try:
        stats = RankedStats.model_validate(payload)
    except ValidationError:
        return None
    entries_by_queue = {
        **stats.queue_map,
        **{entry.queue_type: entry for entry in stats.queues if entry.queue_type},
    }
    for queue_type, queue in RANKED_QUEUES:
        entry = entries_by_queue.get(queue_type)
        if entry is not None and entry.tier.upper() in RANKED_TIERS:
            return RankedStanding(
                queue=queue,
                tier=entry.tier.upper(),
                division=entry.division,
                league_points=entry.league_points,
                wins=entry.wins,
                losses=entry.losses,
            )
    return None


def recent_games_of(payload: JsonValue | None, puuid: str) -> list[RecentGame]:
    """Return a player's recent games on Summoner's Rift, newest first, remakes left out.

    Args:
        payload: The client's answer for the player's match history, or None.
        puuid: The player.

    Returns:
        The games; empty when the answer cannot be read.
    """
    try:
        history = MatchHistory.model_validate(payload)
    except ValidationError:
        return []
    counted_games = [
        (game, line)
        for game in history.games.games
        if game.map_id == SUMMONERS_RIFT_MAP_ID
        and game.game_duration_seconds >= SHORTEST_COUNTED_GAME_SECONDS
        and (line := game.line_of(puuid)) is not None
    ]
    newest_first = sorted(counted_games, key=lambda pair: pair[0].game_creation, reverse=True)
    return [
        RecentGame(
            champion_id=line.champion_id,
            position=history_position(line.timeline.lane, line.timeline.role, line.team_position),
            is_win=line.stats.win,
            item_ids=line.stats.item_ids(),
        )
        for _, line in newest_first
    ]


def history_position(lane: str, role: str, team_position: str) -> str:
    """Return the position a past game was played in, as the game names positions.

    Args:
        lane: The match history's lane ("TOP", "JUNGLE", "MIDDLE", "BOTTOM").
        role: The match history's role ("SOLO", "CARRY", "SUPPORT", ...), which splits bottom.
        team_position: The game's own position, when the answer has one; it wins.

    Returns:
        "TOP", "JUNGLE", "MIDDLE", "BOTTOM" or "UTILITY"; empty when it cannot be told.
    """
    if team_position.upper() in POSITIONS:
        return team_position.upper()
    lane_name = lane.upper()
    role_name = role.upper()
    if lane_name in {"TOP", "JUNGLE"}:
        return lane_name
    if lane_name in {"MIDDLE", "MID"}:
        return "MIDDLE"
    if lane_name in {"BOTTOM", "BOT"} and role_name in {"CARRY", "DUO_CARRY"}:
        return "BOTTOM"
    if lane_name in {"BOTTOM", "BOT"} and role_name in {"SUPPORT", "DUO_SUPPORT"}:
        return "UTILITY"
    return ""


async def load_player_records(
    client: LeagueClient,
    cache: dict[str, PlayerRecord],
    pause_seconds: float = DEFAULT_PAUSE_SECONDS,
) -> PlayerRecords:
    """Return the record of each player in the game in progress, asking only for those not known.

    Args:
        client: The League client.
        cache: Records already known, by PUUID; new ones are added to it.
        pause_seconds: The pause after each request.

    Returns:
        Each player's record by team and champion; empty when the client lists no game.
    """
    session = _gameflow_session_of(await client.get_json(GAMEFLOW_SESSION_PATH))
    teams = (
        (TEAM_ONE, session.game_data.team_one),
        (TEAM_TWO, session.game_data.team_two),
    )
    if not any(players for _, players in teams):
        return {}
    alias_by_champion_id = champion_aliases(await client.get_json(CHAMPION_SUMMARY_PATH))
    records: PlayerRecords = {}
    for team, players in teams:
        for player in players:
            alias = alias_by_champion_id.get(player.champion_id)
            if not player.puuid or alias is None:
                continue
            record = cache.get(player.puuid) or await _look_up(client, player.puuid, pause_seconds)
            if record is None:
                continue
            cache[player.puuid] = record
            records[team, alias.lower()] = GamePlayerRecord(player.champion_id, record)
    return records


async def _look_up(client: LeagueClient, puuid: str, pause_seconds: float) -> PlayerRecord | None:
    """Ask the client for one player's ranked stats and recent games, one request at a time.

    Args:
        client: The League client.
        puuid: The player.
        pause_seconds: The pause after each request.

    Returns:
        The record, or None when the client answered neither question.
    """
    ranked_payload = await client.get_json(RANKED_STATS_PATH_TEMPLATE.format(puuid=puuid))
    await asyncio.sleep(pause_seconds)
    history_payload = await client.get_json(MATCH_HISTORY_PATH_TEMPLATE.format(puuid=puuid))
    await asyncio.sleep(pause_seconds)
    if ranked_payload is None and history_payload is None:
        logger.info("the League client did not answer for one player; asking again next game")
        return None
    return PlayerRecord(
        ranked=ranked_standing_of(ranked_payload),
        recent_games=tuple(recent_games_of(history_payload, puuid)),
    )


def puuids_in_game(session_payload: JsonValue | None) -> list[str]:
    """Return the PUUID of each player in the game in progress, team one first.

    Args:
        session_payload: The client's answer for its gameflow session, or None.

    Returns:
        The PUUIDs; empty when the client lists no game.
    """
    game_data = _gameflow_session_of(session_payload).game_data
    return [player.puuid for player in [*game_data.team_one, *game_data.team_two] if player.puuid]


def _gameflow_session_of(payload: JsonValue | None) -> GameflowSession:
    """Return the client's gameflow session, empty when it cannot be read.

    Args:
        payload: The client's answer, or None.

    Returns:
        The session.
    """
    try:
        return GameflowSession.model_validate(payload)
    except ValidationError:
        return GameflowSession()


def champion_aliases(payload: JsonValue | None) -> dict[int, str]:
    """Return each champion's alias by its id, from the client's champion summary.

    Args:
        payload: The client's answer, or None.

    Returns:
        The aliases; empty when the answer cannot be read.
    """
    try:
        entries = CHAMPION_SUMMARY_ADAPTER.validate_python(payload)
    except ValidationError:
        return {}
    return {entry.champion_id: entry.alias for entry in entries if entry.alias}
