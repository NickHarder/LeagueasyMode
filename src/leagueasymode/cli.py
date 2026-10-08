"""The `leagueasymode` command: run the overlay's engine; record, replay and anonymize games."""

import argparse
import asyncio
import logging
import signal
import sys
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Final

import aiohttp
from aiohttp import web

from leagueasymode.config import (
    Settings,
    default_patch_data_directory,
    default_recordings_directory,
)
from leagueasymode.data_dragon import (
    DataDragonClient,
    PatchStats,
    PatchStatsStore,
    create_system_tls_context,
    load_patch_stats,
)
from leagueasymode.engine import OverlayEngine, PatchStatsLoader
from leagueasymode.game_api import GameApiClient
from leagueasymode.league_client import (
    DEFAULT_LOCKFILE_PATHS,
    ClientConnector,
    LeagueClient,
    SharedAnswers,
    find_client_credentials,
)
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.patch_data import GAME_VERSION_PATH, game_version_of
from leagueasymode.player_intel import PLAYER_LOOKUP_PATH_PREFIXES
from leagueasymode.recorder import RecorderTimings, record_games
from leagueasymode.recording.anonymize import IdentityLeakError, anonymize_recording
from leagueasymode.recording.file_format import COMPRESSED_SUFFIX, PLAIN_SUFFIX
from leagueasymode.replay import DEFAULT_REPLAY_PORT, RecordingReplay, create_replay_application
from leagueasymode.riot_tls import create_riot_tls_context
from leagueasymode.scoring import read_recorded_game, score_game

EXIT_SUCCESS: Final = 0
EXIT_FAILURE: Final = 1
ANONYMIZED_SUFFIX: Final = "-anonymized"
LOCAL_HOST: Final = "127.0.0.1"
# The line `leagueasymode run` prints for the macOS app, which reads the overlay's address from it.
OVERLAY_URL_ANNOUNCEMENT: Final = "LEAGUEASYMODE_OVERLAY_URL="

logger = logging.getLogger("leagueasymode")


def main(arguments: Sequence[str] | None = None) -> int:
    """Run one command.

    Args:
        arguments: The command line without the program's name; None reads `sys.argv`.

    Returns:
        The exit code.
    """
    parser = _build_parser()
    parsed = parser.parse_args(arguments)
    settings = Settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    if parsed.command == "score":
        return _score(Path(parsed.recording), settings)
    if parsed.command == "anonymize":
        return _anonymize(Path(parsed.recording), Path(parsed.output) if parsed.output else None)
    if parsed.command == "record":
        return asyncio.run(
            _until_interrupted(
                lambda stop_requested: record_until_stopped(settings, stop_requested)
            )
        )
    if parsed.command == "run":
        return asyncio.run(
            _until_interrupted(
                lambda stop_requested: run_overlay(settings, stop_requested, _announce_overlay_url)
            )
        )
    replay = RecordingReplay(Path(parsed.recording), speed=parsed.speed)
    return asyncio.run(
        _until_interrupted(
            lambda stop_requested: _serve_replay(replay, parsed.port, stop_requested)
        )
    )


async def run_overlay(
    settings: Settings, stop_requested: asyncio.Event, announce_url: Callable[[str], None]
) -> None:
    """Run the engine and the overlay's local server, and record games too, until stopped.

    Args:
        settings: Where the game is, which port to serve on, and whether to record.
        stop_requested: Set to stop.
        announce_url: Called once with the overlay page's address, when the server is up.
    """
    # The engine and the recorder both ask about each player; they share the answers.
    shared_answers = SharedAnswers(PLAYER_LOOKUP_PATH_PREFIXES)
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            _game_api(session, settings),
            settings.poll_interval_seconds,
            _client_connector(session, settings, shared_answers),
            _patch_stats_loader(session, settings),
            settings.player_lookup_pause_seconds,
        )
        runner = web.AppRunner(create_overlay_application(engine))
        await runner.setup()
        site = web.TCPSite(runner, LOCAL_HOST, settings.overlay_port)
        await site.start()
        bound_port = runner.addresses[0][1]
        announce_url(f"http://{LOCAL_HOST}:{bound_port}/")

        async def record_in_background() -> None:
            await record_games(
                _game_api(session, settings),
                _client_connector(session, settings, shared_answers),
                settings.recordings_directory or default_recordings_directory(),
                RecorderTimings(
                    poll_interval_seconds=settings.poll_interval_seconds,
                    lookup_pause_seconds=settings.player_lookup_pause_seconds,
                ),
                stop_requested,
            )

        background_tasks = [asyncio.create_task(engine.run(stop_requested))]
        if settings.record_while_running:
            background_tasks.append(asyncio.create_task(record_in_background()))
        try:
            await asyncio.gather(*background_tasks)
        finally:
            await runner.cleanup()


async def record_until_stopped(
    settings: Settings,
    stop_requested: asyncio.Event,
    idle_poll_interval_seconds: float = RecorderTimings.idle_poll_interval_seconds,
) -> list[Path]:
    """Record every game until a stop is requested.

    Args:
        settings: Where the game is, where recordings go and how often to ask.
        stop_requested: Set to stop; a game being recorded is closed with what it has.
        idle_poll_interval_seconds: How often to look for a game while none runs.

    Returns:
        The recordings made.
    """
    recordings_directory = settings.recordings_directory or default_recordings_directory()
    timings = RecorderTimings(
        poll_interval_seconds=settings.poll_interval_seconds,
        idle_poll_interval_seconds=idle_poll_interval_seconds,
        lookup_pause_seconds=settings.player_lookup_pause_seconds,
    )
    async with aiohttp.ClientSession() as session:
        logger.info("waiting for a game; recordings go to %s", recordings_directory)
        return await record_games(
            _game_api(session, settings),
            _client_connector(session, settings),
            recordings_directory,
            timings,
            stop_requested,
        )


def _game_api(session: aiohttp.ClientSession, settings: Settings) -> GameApiClient:
    """Return a client of the game's API, over HTTPS to the game or plain HTTP to a replay.

    Args:
        session: The HTTP session.
        settings: Where the game's API is.

    Returns:
        The client.
    """
    is_https = settings.game_api_base_url.startswith("https")
    return GameApiClient(
        session,
        settings.game_api_base_url,
        tls_context=create_riot_tls_context() if is_https else None,
    )


def _client_connector(
    session: aiohttp.ClientSession,
    settings: Settings,
    shared_answers: SharedAnswers | None = None,
) -> ClientConnector:
    """Return what finds the League client when a game starts.

    With `league_client_base_url` set, the client is that address, such as a replay's, reached
    over plain HTTP without a password; otherwise it is the running client, found by its lockfile.

    Args:
        session: The HTTP session.
        settings: Where the client's lockfile is, or a stand-in's address.
        shared_answers: Answers shared with other clients of the same League client, or None.

    Returns:
        A function returning the client, or None when it is not running.
    """
    stand_in_base_url = settings.league_client_base_url
    if stand_in_base_url:

        async def connect_to_stand_in() -> LeagueClient | None:
            return LeagueClient(
                session,
                stand_in_base_url,
                password="",
                tls_context=None,
                shared_answers=shared_answers,
            )

        return connect_to_stand_in

    lockfile_paths = (
        [settings.league_client_lockfile]
        if settings.league_client_lockfile is not None
        else list(DEFAULT_LOCKFILE_PATHS)
    )

    async def connect_to_client() -> LeagueClient | None:
        credentials = await find_client_credentials(lockfile_paths)
        if credentials is None:
            logger.warning("the League client is not running; going on without its data")
            return None
        return LeagueClient(
            session,
            credentials.base_url,
            credentials.password,
            create_riot_tls_context(),
            shared_answers=shared_answers,
        )

    return connect_to_client


def _patch_stats_loader(session: aiohttp.ClientSession, settings: Settings) -> PatchStatsLoader:
    """Return what loads a patch's stats: from disk, or from Data Dragon when downloads are on.

    Args:
        session: The HTTP session.
        settings: Whether to download, from where, and where patches are kept.

    Returns:
        A function returning the stats of the game's patch, given the game's version.
    """
    store = PatchStatsStore(settings.patch_data_directory or default_patch_data_directory())
    base_url = settings.data_dragon_base_url
    client = (
        DataDragonClient(
            session,
            base_url,
            tls_context=create_system_tls_context() if base_url.startswith("https") else None,
        )
        if settings.download_patch_stats
        else None
    )

    async def load(game_version: str | None) -> PatchStats | None:
        return await load_patch_stats(client, store, game_version)

    return load


def _score(recording_path: Path, settings: Settings) -> int:
    """Print how far each estimator is from the truth on a recorded game.

    Args:
        recording_path: The recording.
        settings: Where the patch's stats are kept, and whether they may be downloaded.

    Returns:
        The exit code.
    """
    game = read_recorded_game(recording_path)
    game_version = game_version_of(game.client_resources.get(GAME_VERSION_PATH))
    patch_stats = asyncio.run(_load_patch_stats_once(settings, game_version))
    for score in score_game(game, patch_stats):
        print(score.describe())  # noqa: T201 - the command's output
    if patch_stats is None:
        print("combat stats (yours): no stats for this game's patch")  # noqa: T201 - as above
    return EXIT_SUCCESS


async def _load_patch_stats_once(settings: Settings, game_version: str | None) -> PatchStats | None:
    """Load the stats of a game's patch, as the engine would.

    Args:
        settings: Where patches are kept, and whether they may be downloaded.
        game_version: The game's version, or None when unknown.

    Returns:
        The stats, or None when they cannot be had.
    """
    async with aiohttp.ClientSession() as session:
        return await _patch_stats_loader(session, settings)(game_version)


async def _serve_replay(replay: RecordingReplay, port: int, stop_requested: asyncio.Event) -> None:
    """Serve a replay as a stand-in for the game's API until stopped.

    Args:
        replay: The replay.
        port: The port on 127.0.0.1.
        stop_requested: Set to stop.
    """
    runner = web.AppRunner(create_replay_application(replay))
    await runner.setup()
    site = web.TCPSite(runner, LOCAL_HOST, port)
    await site.start()
    bound_port = runner.addresses[0][1]
    logger.info(
        "replaying at %sx; point the engine at it with LEAGUEASYMODE_GAME_API_BASE_URL and"
        " LEAGUEASYMODE_LEAGUE_CLIENT_BASE_URL both set to http://%s:%d",
        replay.speed,
        LOCAL_HOST,
        bound_port,
    )
    try:
        await stop_requested.wait()
    finally:
        await runner.cleanup()


async def _until_interrupted(
    command: Callable[[asyncio.Event], Coroutine[object, object, object]],
) -> int:
    """Run a command until Ctrl-C or a termination signal asks it to stop.

    Args:
        command: The command, given the event that asks it to stop.

    Returns:
        The exit code.
    """
    stop_requested = asyncio.Event()
    event_loop = asyncio.get_running_loop()
    for stop_signal in (signal.SIGINT, signal.SIGTERM):
        event_loop.add_signal_handler(stop_signal, stop_requested.set)
    await command(stop_requested)
    logger.info("stopped")
    return EXIT_SUCCESS


def _announce_overlay_url(overlay_url: str) -> None:
    """Print the overlay's address on its own line, for the macOS app to read.

    Args:
        overlay_url: The overlay page's address.
    """
    sys.stdout.write(f"{OVERLAY_URL_ANNOUNCEMENT}{overlay_url}\n")
    sys.stdout.flush()
    logger.info("overlay at %s", overlay_url)


def _anonymize(recording_path: Path, output_path: Path | None) -> int:
    """Write an anonymized copy of a recording.

    Args:
        recording_path: The recording.
        output_path: The copy's path, ending in `.jsonl.xz`; None for `<name>-anonymized.jsonl.xz`
            beside the recording.

    Returns:
        The exit code.
    """
    stem = recording_path.name.removesuffix(COMPRESSED_SUFFIX).removesuffix(PLAIN_SUFFIX)
    destination_path = output_path or recording_path.with_name(
        stem + ANONYMIZED_SUFFIX + COMPRESSED_SUFFIX
    )
    destination_plain_path = destination_path.with_name(destination_path.name.removesuffix(".xz"))
    try:
        written_path = anonymize_recording(recording_path, destination_plain_path)
    except IdentityLeakError as error:
        logger.error("%s", error)
        return EXIT_FAILURE
    logger.info("wrote %s", written_path)
    return EXIT_SUCCESS


def _build_parser() -> argparse.ArgumentParser:
    """Return the command line's parser.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="leagueasymode",
        description="A macOS overlay for League of Legends: what the scoreboard hides.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "run",
        help="run the overlay's engine and local server (the macOS app starts this), recording too",
    )
    commands.add_parser(
        "record",
        help="record every game played until stopped (Ctrl-C), with the match timeline after each",
    )
    replay_command = commands.add_parser(
        "replay", help="serve a recording as if the game were running, for development"
    )
    replay_command.add_argument("recording", help="the recording (.jsonl.xz)")
    replay_command.add_argument(
        "--speed", type=float, default=1.0, help="game seconds per real second (default: 1)"
    )
    replay_command.add_argument(
        "--port",
        type=int,
        default=DEFAULT_REPLAY_PORT,
        help=f"the port on 127.0.0.1 (default: {DEFAULT_REPLAY_PORT})",
    )
    score_command = commands.add_parser(
        "score", help="score each estimator against what a recorded game shows to be true"
    )
    score_command.add_argument("recording", help="the recording (.jsonl.xz)")
    anonymize_command = commands.add_parser(
        "anonymize", help="write a copy of a recording with every player's name and id replaced"
    )
    anonymize_command.add_argument("recording", help="the recording (.jsonl.xz)")
    anonymize_command.add_argument(
        "--output", help="the copy's path (.jsonl.xz); default: <recording>-anonymized.jsonl.xz"
    )
    return parser
