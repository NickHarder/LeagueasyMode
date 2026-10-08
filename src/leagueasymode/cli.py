"""The `leagueasymode` command: record games, and make anonymized copies of recordings."""

import argparse
import asyncio
import logging
import signal
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import aiohttp

from leagueasymode.config import Settings, default_recordings_directory
from leagueasymode.game_api import GameApiClient
from leagueasymode.league_client import (
    DEFAULT_LOCKFILE_PATHS,
    LeagueClient,
    find_client_credentials,
)
from leagueasymode.recorder import RecorderTimings, record_games
from leagueasymode.recording.anonymize import IdentityLeakError, anonymize_recording
from leagueasymode.recording.file_format import COMPRESSED_SUFFIX, PLAIN_SUFFIX
from leagueasymode.riot_tls import create_riot_tls_context

EXIT_SUCCESS: Final = 0
EXIT_FAILURE: Final = 1
ANONYMIZED_SUFFIX: Final = "-anonymized"

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
    if parsed.command == "record":
        return asyncio.run(_record_until_interrupted(settings))
    return _anonymize(Path(parsed.recording), Path(parsed.output) if parsed.output else None)


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
    tls_context = create_riot_tls_context()
    recordings_directory = settings.recordings_directory or default_recordings_directory()
    lockfile_paths = (
        [settings.league_client_lockfile]
        if settings.league_client_lockfile is not None
        else list(DEFAULT_LOCKFILE_PATHS)
    )
    timings = RecorderTimings(
        poll_interval_seconds=settings.poll_interval_seconds,
        idle_poll_interval_seconds=idle_poll_interval_seconds,
    )
    async with aiohttp.ClientSession() as session:
        game_api = GameApiClient(
            session,
            settings.game_api_base_url,
            tls_context=tls_context if settings.game_api_base_url.startswith("https") else None,
        )

        async def connect_to_client() -> LeagueClient | None:
            credentials = await find_client_credentials(lockfile_paths)
            if credentials is None:
                logger.warning("the League client is not running; recording the game alone")
                return None
            return LeagueClient(session, credentials.base_url, credentials.password, tls_context)

        logger.info("waiting for a game; recordings go to %s", recordings_directory)
        return await record_games(
            game_api, connect_to_client, recordings_directory, timings, stop_requested
        )


async def _record_until_interrupted(settings: Settings) -> int:
    """Record until Ctrl-C or a termination signal.

    Args:
        settings: The settings.

    Returns:
        The exit code.
    """
    stop_requested = asyncio.Event()
    event_loop = asyncio.get_running_loop()
    for stop_signal in (signal.SIGINT, signal.SIGTERM):
        event_loop.add_signal_handler(stop_signal, stop_requested.set)
    recording_paths = await record_until_stopped(settings, stop_requested)
    logger.info("stopped after %d recording(s)", len(recording_paths))
    return EXIT_SUCCESS


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
        "record",
        help="record every game played until stopped (Ctrl-C), with the match timeline after each",
    )
    anonymize_command = commands.add_parser(
        "anonymize", help="write a copy of a recording with every player's name and id replaced"
    )
    anonymize_command.add_argument("recording", help="the recording (.jsonl.xz)")
    anonymize_command.add_argument(
        "--output", help="the copy's path (.jsonl.xz); default: <recording>-anonymized.jsonl.xz"
    )
    return parser
