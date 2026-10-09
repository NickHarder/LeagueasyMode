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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import Field, JsonValue, TypeAdapter, ValidationError

from leagueasymode.game_state import RiotPayloadModel
from leagueasymode.jungle_starts import (
    FourMinuteSides,
    JungleStarts,
    four_minute_side,
    start_side,
)
from leagueasymode.league_client import GAMEFLOW_SESSION_PATH, LeagueClient
from leagueasymode.overlay_state import RankedStanding
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH

RANKED_STATS_PATH_TEMPLATE: Final = "/lol-ranked/v1/ranked-stats/{puuid}"
RECENT_GAME_COUNT: Final = 20
MATCH_HISTORY_PATH_TEMPLATE: Final = (
    "/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex="
    + str(RECENT_GAME_COUNT)
)
GAME_TIMELINE_PATH_PREFIX: Final = "/lol-match-history/v1/game-timelines/"
# The questions about players, whose answers the engine and the recorder share.
PLAYER_LOOKUP_PATH_PREFIXES: Final = (
    "/lol-ranked/v1/ranked-stats/",
    "/lol-match-history/v1/products/lol/",
    GAME_TIMELINE_PATH_PREFIX,
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
# A player is a likely jungler when at least half of their newest games, and at least two, were
# in the jungle; those jungle games' timelines say where they start.
JUNGLE_POSITION: Final = "JUNGLE"
JUNGLER_GAMES_READ: Final = 5
FEWEST_JUNGLE_GAMES: Final = 2

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
    """A participant's end-of-game stats: the result, creep score and the inventory."""

    win: bool = False
    total_minions_killed: int = Field(default=0, alias="totalMinionsKilled")
    neutral_minions_killed: int = Field(default=0, alias="neutralMinionsKilled")
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
    team_id: int = Field(default=0, alias="teamId")
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

    game_id: int = Field(default=0, alias="gameId")
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
    # Their creep score, lane and jungle, and the game's length.
    creep_score: int = 0
    duration_seconds: int = 0
    # The game's id, their team's id (100 or 200) and their participant id, which find them in
    # the game's timeline; 0 when the history does not say.
    game_id: int = 0
    team_id: int = 0
    participant_id: int = 0


@dataclass(frozen=True)
class PlayerRecord:
    """A player's rank and recent games, newest first, and where they start in the jungle."""

    ranked: RankedStanding | None
    recent_games: tuple[RecentGame, ...]
    # Counted over their recent jungle games: where they started, and where they were at 4:00;
    # None when they rarely jungle or no game said.
    jungle_starts: JungleStarts | None = None
    four_minute_sides: FourMinuteSides | None = None


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
            creep_score=line.stats.total_minions_killed + line.stats.neutral_minions_killed,
            duration_seconds=game.game_duration_seconds,
            game_id=game.game_id,
            team_id=line.team_id,
            participant_id=line.participant_id,
        )
        for game, line in newest_first
    ]


def jungle_timeline_paths(recent_games: Sequence[RecentGame]) -> list[str]:
    """Return the timelines to read for where a player starts in the jungle.

    Args:
        recent_games: Their recent games, newest first.

    Returns:
        The client's path of each jungle game among the newest few; empty when they are not a
        likely jungler.
    """
    jungle_games = [game for game in _jungle_games_read(recent_games) if game.game_id > 0]
    return [f"{GAME_TIMELINE_PATH_PREFIX}{game.game_id}" for game in jungle_games]


def _jungle_games_read(recent_games: Sequence[RecentGame]) -> list[RecentGame]:
    """Return the jungle games among a likely jungler's newest few.

    Args:
        recent_games: Their recent games, newest first.

    Returns:
        The games; empty when fewer than half of the newest few, or fewer than two, were in the
        jungle.
    """
    newest_games = recent_games[:JUNGLER_GAMES_READ]
    jungle_games = [game for game in newest_games if game.position == JUNGLE_POSITION]
    if len(jungle_games) < FEWEST_JUNGLE_GAMES or 2 * len(jungle_games) < len(newest_games):
        return []
    return jungle_games


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
    session_payload = await client.get_json(GAMEFLOW_SESSION_PATH)
    if not puuids_in_game(session_payload):
        return {}
    players = _players_in_game(session_payload, await client.get_json(CHAMPION_SUMMARY_PATH))
    records: PlayerRecords = {}
    for key, player in players:
        record = cache.get(player.puuid) or await _look_up(client, player.puuid, pause_seconds)
        if record is None:
            continue
        cache[player.puuid] = record
        records[key] = GamePlayerRecord(player.champion_id, record)
    return records


def jungle_starts_of(player_records: PlayerRecords) -> dict[tuple[str, str], JungleStarts]:
    """Return where each player with a record of them started their recent jungle games.

    Args:
        player_records: Each player's record, by team and champion.

    Returns:
        The starts, by the same key; a player without them is left out.
    """
    return {
        key: game_record.record.jungle_starts
        for key, game_record in player_records.items()
        if game_record.record.jungle_starts is not None
    }


def recorded_player_records(client_resources: Mapping[str, JsonValue]) -> PlayerRecords:
    """Return the record of each player in a recorded game, from the client's recorded answers.

    The recorder asks what the engine asks, so the records are those the engine had.

    Args:
        client_resources: The client's latest answer for each path it was asked.

    Returns:
        Each player's record by team and champion; empty when the recording lists no game.
    """
    records: PlayerRecords = {}
    players = _players_in_game(
        client_resources.get(GAMEFLOW_SESSION_PATH), client_resources.get(CHAMPION_SUMMARY_PATH)
    )
    for key, player in players:
        history_payload = client_resources.get(
            MATCH_HISTORY_PATH_TEMPLATE.format(puuid=player.puuid)
        )
        record = player_record(
            player.puuid,
            client_resources.get(RANKED_STATS_PATH_TEMPLATE.format(puuid=player.puuid)),
            history_payload,
            {
                timeline_path: client_resources.get(timeline_path)
                for timeline_path in jungle_timeline_paths(
                    recent_games_of(history_payload, player.puuid)
                )
            },
        )
        if record is not None:
            records[key] = GamePlayerRecord(player.champion_id, record)
    return records


def player_record(
    puuid: str,
    ranked_payload: JsonValue | None,
    history_payload: JsonValue | None,
    timeline_payloads: Mapping[str, JsonValue | None],
) -> PlayerRecord | None:
    """Return a player's record from the client's answers about them.

    Args:
        puuid: The player.
        ranked_payload: The answer for their ranked stats, or None.
        history_payload: The answer for their match history, or None.
        timeline_payloads: The answer for each of their past games' timelines read, by path.

    Returns:
        The record, or None when the client answered neither for their rank nor their history.
    """
    if ranked_payload is None and history_payload is None:
        return None
    recent_games = recent_games_of(history_payload, puuid)
    jungle_starts, four_minute_sides = _jungle_habits(recent_games, timeline_payloads)
    return PlayerRecord(
        ranked=ranked_standing_of(ranked_payload),
        recent_games=tuple(recent_games),
        jungle_starts=jungle_starts,
        four_minute_sides=four_minute_sides,
    )


async def _look_up(client: LeagueClient, puuid: str, pause_seconds: float) -> PlayerRecord | None:
    """Ask the client for one player's rank, recent games and jungle timelines, one at a time.

    Args:
        client: The League client.
        puuid: The player.
        pause_seconds: The pause after each request.

    Returns:
        The record, or None when the client answered neither for their rank nor their history.
    """
    ranked_payload = await client.get_json(RANKED_STATS_PATH_TEMPLATE.format(puuid=puuid))
    await asyncio.sleep(pause_seconds)
    history_payload = await client.get_json(MATCH_HISTORY_PATH_TEMPLATE.format(puuid=puuid))
    await asyncio.sleep(pause_seconds)
    if ranked_payload is None and history_payload is None:
        logger.info("the League client did not answer for one player; asking again next game")
        return None
    timeline_payloads: dict[str, JsonValue | None] = {}
    for timeline_path in jungle_timeline_paths(recent_games_of(history_payload, puuid)):
        timeline_payloads[timeline_path] = await client.get_json(timeline_path)
        await asyncio.sleep(pause_seconds)
    return player_record(puuid, ranked_payload, history_payload, timeline_payloads)


def _jungle_habits(
    recent_games: Sequence[RecentGame], timeline_payloads: Mapping[str, JsonValue | None]
) -> tuple[JungleStarts | None, FourMinuteSides | None]:
    """Count where a likely jungler started, and was at 4:00, in each of their recent jungle games.

    Args:
        recent_games: Their recent games, newest first.
        timeline_payloads: The answer for each of those games' timelines, by path.

    Returns:
        How many started on each side, and how many were on each side at 4:00; each None when
        they are not a likely jungler or no game said.
    """
    starts = []
    four_minute_sides = []
    for game in _jungle_games_read(recent_games):
        timeline_payload = timeline_payloads.get(f"{GAME_TIMELINE_PATH_PREFIX}{game.game_id}")
        starts.append(start_side(timeline_payload, game.participant_id, game.team_id))
        four_minute_sides.append(
            four_minute_side(timeline_payload, game.participant_id, game.team_id)
        )
    return (
        JungleStarts(blue_count=starts.count("blue"), red_count=starts.count("red"))
        if any(starts)
        else None,
        FourMinuteSides(
            blue_count=four_minute_sides.count("blue"),
            red_count=four_minute_sides.count("red"),
            mid_count=four_minute_sides.count("mid"),
        )
        if any(four_minute_sides)
        else None,
    )


def _players_in_game(
    session_payload: JsonValue | None, champion_summary_payload: JsonValue | None
) -> list[tuple[tuple[str, str], GameflowPlayer]]:
    """Return each player of the game in progress with the key their record is known by.

    Args:
        session_payload: The client's answer for its gameflow session, or None.
        champion_summary_payload: The client's champion summary, or None.

    Returns:
        Each player with a PUUID and a champion the summary names, with their team and their
        champion's alias in lowercase; team one first.
    """
    game_data = _gameflow_session_of(session_payload).game_data
    alias_by_champion_id = champion_aliases(champion_summary_payload)
    return [
        ((team, alias_by_champion_id[player.champion_id].lower()), player)
        for team, players in ((TEAM_ONE, game_data.team_one), (TEAM_TWO, game_data.team_two))
        for player in players
        if player.puuid and player.champion_id in alias_by_champion_id
    ]


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
