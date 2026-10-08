"""Record games: wait for one, keep every answer of the game's API and what the League client knows.

At the start of a game the League client is asked for the game's id and for this patch's game data
(items, champions, summoner spells, runes), so that a recording can be replayed and scored on its
own later. After the game it is asked for the match timeline, which the client fetches from Riot
some time after the game ends: that is the ground truth every estimator is scored against.
"""

import asyncio
import datetime
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import JsonValue

from leagueasymode import __version__
from leagueasymode.game_api import GameApiClient
from leagueasymode.league_client import LeagueClient
from leagueasymode.recording.file_format import PLAIN_SUFFIX
from leagueasymode.recording.writer import DEFAULT_KEYFRAME_INTERVAL_SECONDS, RecordingWriter

GAMEFLOW_SESSION_PATH: Final = "/lol-gameflow/v1/session"
CHAMPION_SUMMARY_PATH: Final = "/lol-game-data/assets/v1/champion-summary.json"
# This patch's game data, as the client serves it. A path the client does not have is skipped.
STATIC_CLIENT_PATHS: Final = (
    "/lol-patch/v1/game-version",
    "/lol-game-data/assets/v1/items.json",
    CHAMPION_SUMMARY_PATH,
    "/lol-game-data/assets/v1/summoner-spells.json",
    "/lol-game-data/assets/v1/perks.json",
    "/lol-game-data/assets/v1/perkstyles.json",
)
CHAMPION_DETAILS_PATH_TEMPLATE: Final = "/lol-game-data/assets/v1/champions/{champion_id}.json"
TIMELINE_PATH_TEMPLATE: Final = "/lol-match-history/v1/game-timelines/{game_id}"
GAME_DETAILS_PATH_TEMPLATE: Final = "/lol-match-history/v1/games/{game_id}"
END_OF_GAME_STATS_PATH: Final = "/lol-end-of-game/v1/eog-stats-block"
GAME_END_EVENT_NAME: Final = "GameEnd"
RAW_CHAMPION_NAME_PREFIX: Final = "game_character_displayname_"
# The game keeps answering on the victory screen; this is long enough to see it out.
POST_GAME_RECORDING_SECONDS: Final = 30.0

REASON_GAME_ENDED: Final = "game ended"
REASON_GAME_STOPPED_ANSWERING: Final = "the game stopped answering"
REASON_RECORDING_STOPPED: Final = "recording stopped"
REASON_RECORDING_CANCELLED: Final = "recording cancelled"

logger = logging.getLogger(__name__)

type ClientConnector = Callable[[], Awaitable[LeagueClient | None]]


@dataclass(frozen=True)
class RecorderTimings:
    """How often the recorder asks, and how long it waits."""

    poll_interval_seconds: float = 0.5
    idle_poll_interval_seconds: float = 2.0
    game_end_grace_seconds: float = 120.0
    timeline_wait_seconds: float = 600.0
    timeline_retry_seconds: float = 15.0
    keyframe_interval_seconds: float = DEFAULT_KEYFRAME_INTERVAL_SECONDS


class _SharedRecording:
    """One open recording, written from more than one task, one line at a time."""

    def __init__(self, writer: RecordingWriter, client: LeagueClient | None) -> None:
        """Keep the writer and the client of one game.

        Args:
            writer: The recording's writer.
            client: The League client, or None when it is not running.
        """
        self.writer: Final = writer
        self.client: Final = client
        self.started_at_monotonic: Final = time.monotonic()
        self._lock: Final = asyncio.Lock()

    def elapsed_seconds(self) -> float:
        """Return how long ago the recording started.

        Returns:
            Seconds since the recording started.
        """
        return time.monotonic() - self.started_at_monotonic

    async def write_snapshot(self, payload: JsonValue) -> None:
        """Write one answer of the game's API.

        Args:
            payload: The answer.
        """
        async with self._lock:
            await asyncio.to_thread(self.writer.write_snapshot, self.elapsed_seconds(), payload)

    async def write_client_resource(self, path: str, payload: JsonValue) -> None:
        """Write one answer of the League client.

        Args:
            path: The path that was asked for.
            payload: The answer.
        """
        async with self._lock:
            await asyncio.to_thread(
                self.writer.write_client_resource, self.elapsed_seconds(), path, payload
            )

    async def finish(self, reason: str) -> Path:
        """Write the last line, close the file and compress it.

        Args:
            reason: Why the recording stopped.

        Returns:
            The compressed recording's path.
        """
        async with self._lock:
            await asyncio.to_thread(self.writer.write_ended, self.elapsed_seconds(), reason)
            return await asyncio.to_thread(self.writer.close)


@dataclass(frozen=True)
class _GameOver:
    """A recording whose game is over, waiting for what the client gives after a game."""

    recording: _SharedRecording
    reason: str
    game_id: int | None


async def record_one_game(
    game_api: GameApiClient,
    connect_to_client: ClientConnector,
    recordings_directory: Path,
    timings: RecorderTimings,
    stop_requested: asyncio.Event | None = None,
) -> Path | None:
    """Wait for a game, record it, wait for its timeline, and return the recording's path.

    Args:
        game_api: The game's API.
        connect_to_client: Finds the League client, or returns None when it is not running.
        recordings_directory: Where recordings are kept.
        timings: How often to ask and how long to wait.
        stop_requested: Set to stop: a game being recorded is closed with what it has.

    Returns:
        The recording's path, or None when the stop came before any game.
    """
    stop_event = stop_requested if stop_requested is not None else asyncio.Event()
    game_over = await _record_until_game_over(
        game_api, connect_to_client, recordings_directory, timings, stop_event
    )
    if game_over is None:
        return None
    return await _finish_after_game(game_over, timings, stop_event)


async def record_games(
    game_api: GameApiClient,
    connect_to_client: ClientConnector,
    recordings_directory: Path,
    timings: RecorderTimings,
    stop_requested: asyncio.Event,
) -> list[Path]:
    """Record every game until stopped; a game's timeline is waited for while the next is awaited.

    Args:
        game_api: The game's API.
        connect_to_client: Finds the League client, or returns None when it is not running.
        recordings_directory: Where recordings are kept.
        timings: How often to ask and how long to wait.
        stop_requested: Set to stop.

    Returns:
        The paths of the recordings made.
    """
    finishing_tasks: list[asyncio.Task[Path]] = []
    while not stop_requested.is_set():
        game_over = await _record_until_game_over(
            game_api, connect_to_client, recordings_directory, timings, stop_requested
        )
        if game_over is None:
            break
        finishing_tasks.append(
            asyncio.create_task(_finish_after_game(game_over, timings, stop_requested))
        )
    return list(await asyncio.gather(*finishing_tasks))


async def _record_until_game_over(
    game_api: GameApiClient,
    connect_to_client: ClientConnector,
    recordings_directory: Path,
    timings: RecorderTimings,
    stop_requested: asyncio.Event,
) -> _GameOver | None:
    """Wait for a game and record it until it is over or a stop is requested.

    Args:
        game_api: The game's API.
        connect_to_client: Finds the League client.
        recordings_directory: Where recordings are kept.
        timings: How often to ask and how long to wait.
        stop_requested: Set to stop.

    Returns:
        The finished game's recording, still open, or None when the stop came before any game.
    """
    first_payload = await _wait_for_game(game_api, timings, stop_requested)
    if first_payload is None:
        return None
    started_at = datetime.datetime.now(datetime.UTC)
    recording_path = await asyncio.to_thread(_new_recording_path, recordings_directory, started_at)
    writer = RecordingWriter(recording_path, timings.keyframe_interval_seconds)
    await asyncio.to_thread(
        writer.write_started, started_at, __version__, timings.poll_interval_seconds
    )
    recording = _SharedRecording(writer, await connect_to_client())
    logger.info("recording a game to %s", recording_path)
    await recording.write_snapshot(first_payload)
    start_task = asyncio.create_task(_record_client_data_at_start(recording, first_payload))
    try:
        reason = await _record_snapshots(
            game_api, recording, first_payload, timings, stop_requested
        )
        game_id = await start_task
    except asyncio.CancelledError:
        start_task.cancel()
        await recording.finish(REASON_RECORDING_CANCELLED)
        raise
    return _GameOver(recording=recording, reason=reason, game_id=game_id)


async def _wait_for_game(
    game_api: GameApiClient, timings: RecorderTimings, stop_requested: asyncio.Event
) -> JsonValue | None:
    """Ask the game's API until a game answers.

    Args:
        game_api: The game's API.
        timings: How often to ask while no game runs.
        stop_requested: Set to stop waiting.

    Returns:
        The first answer of the game, or None when the stop came first.
    """
    while not stop_requested.is_set():
        payload = await game_api.fetch_all_game_data()
        if isinstance(payload, dict) and isinstance(payload.get("gameData"), dict):
            return payload
        await _sleep_unless_stopped(timings.idle_poll_interval_seconds, stop_requested)
    return None


async def _record_snapshots(
    game_api: GameApiClient,
    recording: _SharedRecording,
    first_payload: JsonValue,
    timings: RecorderTimings,
    stop_requested: asyncio.Event,
) -> str:
    """Write every answer of the game until the game is over or a stop is requested.

    Args:
        game_api: The game's API.
        recording: The open recording.
        first_payload: The answer already written.
        timings: How often to ask, and how long a silent game is waited for.
        stop_requested: Set to stop.

    Returns:
        Why the recording of snapshots stopped.
    """
    last_answer_at_seconds = recording.elapsed_seconds()
    game_end_seen_at_seconds: float | None = (
        last_answer_at_seconds if _has_game_ended(first_payload) else None
    )
    while True:
        await _sleep_unless_stopped(timings.poll_interval_seconds, stop_requested)
        if stop_requested.is_set():
            return REASON_RECORDING_STOPPED
        payload = await game_api.fetch_all_game_data()
        now_seconds = recording.elapsed_seconds()
        if game_end_seen_at_seconds is not None and (
            payload is None or now_seconds - game_end_seen_at_seconds >= POST_GAME_RECORDING_SECONDS
        ):
            return REASON_GAME_ENDED
        if payload is None:
            if now_seconds - last_answer_at_seconds >= timings.game_end_grace_seconds:
                return REASON_GAME_STOPPED_ANSWERING
            continue
        await recording.write_snapshot(payload)
        last_answer_at_seconds = now_seconds
        if game_end_seen_at_seconds is None and _has_game_ended(payload):
            game_end_seen_at_seconds = now_seconds


async def _record_client_data_at_start(
    recording: _SharedRecording, first_payload: JsonValue
) -> int | None:
    """Write what the League client knows at the start of a game, and return the game's id.

    Args:
        recording: The open recording.
        first_payload: The game's first answer, which names the champions in the game.

    Returns:
        The game's id, or None when the client is not running or does not say.
    """
    client = recording.client
    if client is None:
        return None
    session = await _record_client_resource(recording, client, GAMEFLOW_SESSION_PATH)
    static_resources = {
        path: await _record_client_resource(recording, client, path) for path in STATIC_CLIENT_PATHS
    }
    for champion_id in _champion_ids_in_game(
        static_resources[CHAMPION_SUMMARY_PATH], first_payload
    ):
        await _record_client_resource(
            recording, client, CHAMPION_DETAILS_PATH_TEMPLATE.format(champion_id=champion_id)
        )
    return _game_id_of(session)


async def _finish_after_game(
    game_over: _GameOver, timings: RecorderTimings, stop_requested: asyncio.Event
) -> Path:
    """Write what the League client gives after a game, then close the recording.

    Args:
        game_over: The finished game's recording.
        timings: How long to wait for the timeline, and how often to ask.
        stop_requested: Set to stop waiting for the timeline.

    Returns:
        The compressed recording's path.
    """
    recording = game_over.recording
    client = recording.client
    is_worth_waiting = game_over.reason in {REASON_GAME_ENDED, REASON_GAME_STOPPED_ANSWERING}
    if client is not None and game_over.game_id is not None and is_worth_waiting:
        await _record_client_resource(recording, client, END_OF_GAME_STATS_PATH)
        await _wait_for_timeline(recording, client, game_over.game_id, timings, stop_requested)
    recording_path = await recording.finish(game_over.reason)
    logger.info("recorded a game: %s (%s)", recording_path, game_over.reason)
    return recording_path


async def _wait_for_timeline(
    recording: _SharedRecording,
    client: LeagueClient,
    game_id: int,
    timings: RecorderTimings,
    stop_requested: asyncio.Event,
) -> None:
    """Ask the client for the match timeline until it has it, then for the game's details.

    Args:
        recording: The open recording.
        client: The League client.
        game_id: The game's id.
        timings: How long to wait, and how often to ask.
        stop_requested: Set to stop waiting.
    """
    deadline_seconds = recording.elapsed_seconds() + timings.timeline_wait_seconds
    timeline_path = TIMELINE_PATH_TEMPLATE.format(game_id=game_id)
    while not stop_requested.is_set() and recording.elapsed_seconds() < deadline_seconds:
        timeline = await _record_client_resource(recording, client, timeline_path)
        if timeline is not None:
            await _record_client_resource(
                recording, client, GAME_DETAILS_PATH_TEMPLATE.format(game_id=game_id)
            )
            logger.info("saved the match timeline of game %d", game_id)
            return
        await _sleep_unless_stopped(timings.timeline_retry_seconds, stop_requested)
    logger.warning("the match timeline of game %d did not come; recording without it", game_id)


async def _record_client_resource(
    recording: _SharedRecording, client: LeagueClient, path: str
) -> JsonValue | None:
    """Ask the client for one resource and write it when there is one.

    Args:
        recording: The open recording.
        client: The League client.
        path: The resource's path.

    Returns:
        The resource, or None when the client did not give it.
    """
    payload = await client.get_json(path)
    if payload is not None:
        await recording.write_client_resource(path, payload)
    return payload


def _has_game_ended(payload: JsonValue) -> bool:
    """Return whether an answer of the game's API holds the GameEnd event.

    Args:
        payload: The answer.

    Returns:
        Whether the game has ended.
    """
    events = payload.get("events") if isinstance(payload, dict) else None
    event_list = events.get("Events") if isinstance(events, dict) else None
    if not isinstance(event_list, list):
        return False
    return any(
        isinstance(event, dict) and event.get("EventName") == GAME_END_EVENT_NAME
        for event in event_list
    )


def _game_id_of(session: JsonValue | None) -> int | None:
    """Return the game's id from the client's gameflow session.

    Args:
        session: The answer of `/lol-gameflow/v1/session`, or None.

    Returns:
        The id, or None when the session does not hold one.
    """
    game_data = session.get("gameData") if isinstance(session, dict) else None
    game_id = game_data.get("gameId") if isinstance(game_data, dict) else None
    if isinstance(game_id, int) and not isinstance(game_id, bool) and game_id > 0:
        return game_id
    return None


def _champion_ids_in_game(
    champion_summary: JsonValue | None, first_payload: JsonValue
) -> list[int]:
    """Return the client's ids of the champions in a game.

    The game names a champion by its alias inside `rawChampionName`; the client's champion summary
    pairs each alias with an id.

    Args:
        champion_summary: The answer of `champion-summary.json`, or None.
        first_payload: The game's first answer.

    Returns:
        The ids, in the scoreboard's order, without repeats.
    """
    if not isinstance(champion_summary, list) or not isinstance(first_payload, dict):
        return []
    id_by_alias = {
        str(champion.get("alias")).lower(): champion["id"]
        for champion in champion_summary
        if isinstance(champion, dict) and isinstance(champion.get("id"), int)
    }
    players = first_payload.get("allPlayers")
    raw_names = [
        player.get("rawChampionName")
        for player in (players if isinstance(players, list) else [])
        if isinstance(player, dict)
    ]
    aliases = [
        raw_name.removeprefix(RAW_CHAMPION_NAME_PREFIX).lower()
        for raw_name in raw_names
        if isinstance(raw_name, str)
    ]
    champion_ids = [id_by_alias[alias] for alias in aliases if alias in id_by_alias]
    return [
        champion_id
        for position, champion_id in enumerate(champion_ids)
        if isinstance(champion_id, int) and champion_id not in champion_ids[:position]
    ]


def _new_recording_path(recordings_directory: Path, started_at: datetime.datetime) -> Path:
    """Create the directory if needed and return a recording path that is not taken.

    Args:
        recordings_directory: Where recordings are kept.
        started_at: When the recording starts, which names it.

    Returns:
        The path to write the recording to, ending in `.jsonl`.
    """
    recordings_directory.mkdir(parents=True, exist_ok=True)
    stem = f"game-{started_at:%Y-%m-%dT%H-%M-%SZ}"
    candidate_stems = [stem, *(f"{stem}-{number}" for number in range(2, 1000))]
    for candidate_stem in candidate_stems:
        candidate_path = recordings_directory / (candidate_stem + PLAIN_SUFFIX)
        if (
            not candidate_path.exists()
            and not candidate_path.with_name(candidate_path.name + ".xz").exists()
        ):
            return candidate_path
    raise FileExistsError(f"no free recording name for {stem} in {recordings_directory}")


async def _sleep_unless_stopped(seconds: float, stop_requested: asyncio.Event) -> None:
    """Wait for some seconds, or less if a stop is requested meanwhile.

    Args:
        seconds: How long to wait.
        stop_requested: Ends the wait early when set.
    """
    try:
        await asyncio.wait_for(stop_requested.wait(), timeout=seconds)
    except TimeoutError:
        return
