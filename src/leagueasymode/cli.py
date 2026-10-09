"""The `leagueasymode` command: run the overlay's engine; record, replay and anonymize games."""

import argparse
import asyncio
import datetime
import logging
import signal
import sys
from collections import Counter
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Final

import aiohttp
from aiohttp import web

from leagueasymode.accuracy_history import (
    append_game_accuracy,
    game_accuracy_of,
    history_lines,
    read_accuracy_history,
)
from leagueasymode.accuracy_thresholds import (
    MIN_GAMES_FOR_THRESHOLDS,
    load_thresholds,
    proposed_thresholds,
    save_thresholds,
    stricter_thresholds,
)
from leagueasymode.config import (
    REPOSITORY_ROOT,
    Settings,
    default_accuracy_history_path,
    default_last_game_summary_path,
    default_model_weights_path,
    default_patch_data_directory,
    default_preferences_path,
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
from leagueasymode.game_summary import game_summary
from leagueasymode.league_client import (
    DEFAULT_LOCKFILE_PATHS,
    ClientConnector,
    LeagueClient,
    SharedAnswers,
    find_client_credentials,
)
from leagueasymode.league_settings import DEFAULT_GAME_CONFIG_PATH, read_minimap_layout
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.patch_data import GAME_VERSION_PATH, game_version_of
from leagueasymode.player_intel import PLAYER_LOOKUP_PATH_PREFIXES
from leagueasymode.preferences import load_preferences
from leagueasymode.recorder import RecorderTimings, record_games
from leagueasymode.recording.anonymize import IdentityLeakError, anonymize_recording
from leagueasymode.recording.file_format import COMPRESSED_SUFFIX, PLAIN_SUFFIX
from leagueasymode.refit import (
    MIN_GAMES_TO_FIT,
    ModelWeights,
    load_model_weights,
    refit_fights,
    refit_win_chance,
    save_model_weights,
)
from leagueasymode.replay import DEFAULT_REPLAY_PORT, RecordingReplay, create_replay_application
from leagueasymode.riot_tls import create_riot_tls_context
from leagueasymode.scoring import fight_samples, read_recorded_game, score_game, win_samples

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
    commands: dict[str, Callable[[], int]] = {
        "score": lambda: _score(Path(parsed.recording), settings, should_keep=parsed.keep),
        "history": lambda: _history(settings, parsed.games),
        "thresholds": lambda: _thresholds(
            [Path(recording) for recording in parsed.recordings],
            settings,
            thresholds_path=Path(parsed.file),
            should_write=parsed.write,
        ),
        "fit": lambda: _fit(
            [Path(recording) for recording in parsed.recordings],
            settings,
            should_write=parsed.write,
        ),
        "anonymize": lambda: _anonymize(
            Path(parsed.recording), Path(parsed.output) if parsed.output else None
        ),
        "record": lambda: asyncio.run(
            _until_interrupted(
                lambda stop_requested: record_until_stopped(settings, stop_requested)
            )
        ),
        "run": lambda: asyncio.run(
            _until_interrupted(
                lambda stop_requested: run_overlay(settings, stop_requested, _announce_overlay_url)
            )
        ),
    }
    if parsed.command in commands:
        return commands[parsed.command]()
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
    preferences_path = settings.preferences or default_preferences_path()
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            _game_api(session, settings),
            settings.poll_interval_seconds,
            _client_connector(session, settings, shared_answers),
            _patch_stats_loader(session, settings),
            settings.player_lookup_pause_seconds,
            minimap_layout=await asyncio.to_thread(
                read_minimap_layout, settings.league_game_config or DEFAULT_GAME_CONFIG_PATH
            ),
            model_weights=await asyncio.to_thread(
                load_model_weights, settings.model_weights or default_model_weights_path()
            ),
            preferences=await asyncio.to_thread(load_preferences, preferences_path),
        )
        history_path = settings.accuracy_history or default_accuracy_history_path()
        summary_path = settings.last_game_summary or default_last_game_summary_path()
        runner = web.AppRunner(
            create_overlay_application(
                engine,
                summary_path=summary_path,
                history_path=history_path,
                preferences_path=preferences_path,
            )
        )
        await runner.setup()
        site = web.TCPSite(runner, LOCAL_HOST, settings.overlay_port)
        await site.start()
        bound_port = runner.addresses[0][1]
        announce_url(f"http://{LOCAL_HOST}:{bound_port}/")

        scoring_patch_stats = _patch_stats_loader(session, settings)

        async def score_recorded_game(recording_path: Path) -> None:
            await after_the_game(
                recording_path,
                scoring_patch_stats,
                history_path=history_path,
                summary_path=summary_path,
            )

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
                on_recorded=score_recorded_game,
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


def _score(recording_path: Path, settings: Settings, *, should_keep: bool) -> int:
    """Print how far each estimator is from the truth on a recorded game.

    Args:
        recording_path: The recording.
        settings: Where the patch's stats and the accuracy history are kept.
        should_keep: Whether to add the scores to the accuracy history.

    Returns:
        The exit code.
    """
    game = read_recorded_game(recording_path)
    game_version = game_version_of(game.client_resources.get(GAME_VERSION_PATH))
    patch_stats = asyncio.run(_load_patch_stats_once(settings, game_version))
    scores = score_game(game, patch_stats)
    for score in scores:
        print(score.describe())  # noqa: T201 - the command's output
    if patch_stats is None:
        print("combat stats (yours): no stats for this game's patch")  # noqa: T201 - as above
    if should_keep:
        history_path = settings.accuracy_history or default_accuracy_history_path()
        append_game_accuracy(
            history_path, game_accuracy_of(recording_path, game, scores, _now_text())
        )
        print(f"kept in {history_path}")  # noqa: T201 - as above
    return EXIT_SUCCESS


def _thresholds(
    recording_paths: list[Path], settings: Settings, *, thresholds_path: Path, should_write: bool
) -> int:
    """Propose each estimator's threshold from recorded games, and tighten the file's with it.

    Args:
        recording_paths: The recordings, 20 or more.
        settings: Where the patch's stats are kept.
        thresholds_path: The thresholds file CI holds the recordings to.
        should_write: Whether to write the thresholds, each only ever made stricter.

    Returns:
        The exit code.
    """
    games = [
        (
            game,
            asyncio.run(
                _load_patch_stats_once(
                    settings, game_version_of(game.client_resources.get(GAME_VERSION_PATH))
                )
            ),
        )
        for game in (read_recorded_game(recording_path) for recording_path in recording_paths)
    ]
    scored_games = [score_game(game, patch_stats) for game, patch_stats in games]
    proposed = proposed_thresholds(scored_games)
    if not proposed:
        game_counts = Counter(score.estimator for scores in scored_games for score in scores)
        counts_text = ", ".join(f"{name} has {count}" for name, count in game_counts.items())
        print(  # noqa: T201 - the command's output
            f"no estimator has {MIN_GAMES_FOR_THRESHOLDS} games yet: {counts_text or 'none'}"
        )
        return EXIT_SUCCESS
    measures = {score.estimator: score.measure for scores in scored_games for score in scores}
    thresholds = stricter_thresholds(load_thresholds(thresholds_path), proposed, measures)
    for estimator, threshold in sorted(thresholds.items()):
        print(f"{estimator}: {threshold}")  # noqa: T201 - as above
    if should_write:
        save_thresholds(thresholds_path, thresholds)
        print(f"wrote {thresholds_path}")  # noqa: T201 - as above
    return EXIT_SUCCESS


def _history(settings: Settings, last_games: int) -> int:
    """Print each estimator's accuracy over the latest games scored.

    Args:
        settings: Where the accuracy history is kept.
        last_games: How many of the latest games to take.

    Returns:
        The exit code.
    """
    history = read_accuracy_history(settings.accuracy_history or default_accuracy_history_path())
    lines = history_lines(history, last_games) or [
        "no game scored yet: `leagueasymode run` scores each game it records, and "
        "`leagueasymode score <recording> --keep` one by hand"
    ]
    for line in lines:
        print(line)  # noqa: T201 - the command's output
    return EXIT_SUCCESS


async def after_the_game(
    recording_path: Path,
    load_patch_stats: PatchStatsLoader,
    *,
    history_path: Path,
    summary_path: Path,
) -> None:
    """Score a recorded game, add its scores to the accuracy history, and write its summary.

    Args:
        recording_path: The recording, closed.
        load_patch_stats: Returns the stats of the game's patch.
        history_path: The accuracy history.
        summary_path: The last game's summary, for the post-game window.
    """
    game = await asyncio.to_thread(read_recorded_game, recording_path)
    patch_stats = await load_patch_stats(
        game_version_of(game.client_resources.get(GAME_VERSION_PATH))
    )
    scores = await asyncio.to_thread(score_game, game, patch_stats)
    await asyncio.to_thread(
        append_game_accuracy,
        history_path,
        game_accuracy_of(recording_path, game, scores, _now_text()),
    )
    summary = await asyncio.to_thread(game_summary, recording_path.name, game, scores)
    await asyncio.to_thread(_write_whole, summary_path, summary.model_dump_json())
    logger.info("scored %s: %d estimators", recording_path.name, len(scores))


def _write_whole(file_path: Path, file_text: str) -> None:
    """Write a file whole: to a partial file first, then into place.

    Args:
        file_path: The file.
        file_text: Its text.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = file_path.with_suffix(".partial")
    partial_path.write_text(file_text)
    partial_path.replace(file_path)


def _now_text() -> str:
    """Return the time now, as an ISO time in UTC.

    Returns:
        The time.
    """
    return datetime.datetime.now(tz=datetime.UTC).isoformat(timespec="seconds")


def _fit(recording_paths: list[Path], settings: Settings, *, should_write: bool) -> int:
    """Refit the hand-set models on recorded games, print how each scores, and keep what is better.

    Args:
        recording_paths: The recordings.
        settings: Where the patch's stats and the weights are kept.
        should_write: Whether to write the weights kept, for the engine to read.

    Returns:
        The exit code.
    """
    games = [read_recorded_game(recording_path) for recording_path in recording_paths]
    patch_stats_by_version: dict[str | None, PatchStats | None] = {}
    for game in games:
        game_version = game_version_of(game.client_resources.get(GAME_VERSION_PATH))
        if game_version not in patch_stats_by_version:
            patch_stats_by_version[game_version] = asyncio.run(
                _load_patch_stats_once(settings, game_version)
            )
    win_games = [win_samples(game) for game in games]
    fight_games = [
        fight_samples(
            game,
            patch_stats_by_version[game_version_of(game.client_resources.get(GAME_VERSION_PATH))],
        )
        for game in games
    ]
    win_refit = refit_win_chance(win_games)
    fight_refit = refit_fights(fight_games)
    lines = [
        win_refit.describe()
        if win_refit is not None
        else (
            f"win chance: needs {MIN_GAMES_TO_FIT} recorded games with a result, "
            f"has {sum(1 for game in win_games if game)}"
        ),
        fight_refit.describe()
        if fight_refit is not None
        else (
            f"fights: needs {MIN_GAMES_TO_FIT} recorded games with fights, "
            f"has {sum(1 for game in fight_games if game)}"
        ),
    ]
    kept_weights = ModelWeights(
        win_rules=(
            win_refit.rules
            if win_refit is not None and win_refit.is_kept
            else ModelWeights().win_rules
        ),
        fight_rules=(
            fight_refit.rules
            if fight_refit is not None and fight_refit.is_kept
            else ModelWeights().fight_rules
        ),
    )
    weights_path = settings.model_weights or default_model_weights_path()
    is_any_kept = kept_weights != ModelWeights()
    if should_write and is_any_kept:
        save_model_weights(weights_path, kept_weights)
    written_line = (
        f"wrote {weights_path}"
        if should_write and is_any_kept
        else "nothing written: the hand-set weights stand"
        if should_write
        else "add --write to keep what was kept"
    )
    for line in [*lines, written_line]:
        print(line)  # noqa: T201 - the command's output
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
    score_command.add_argument(
        "--keep", action="store_true", help="add the scores to the accuracy history"
    )
    thresholds_command = commands.add_parser(
        "thresholds",
        help="propose each estimator's threshold from 20 or more recorded games; never loosens",
    )
    thresholds_command.add_argument("recordings", nargs="+", help="the recordings (.jsonl.xz)")
    thresholds_command.add_argument(
        "--file",
        default=str(REPOSITORY_ROOT / "tests" / "accuracy_thresholds.json"),
        help="the thresholds file (default: tests/accuracy_thresholds.json)",
    )
    thresholds_command.add_argument(
        "--write", action="store_true", help="write the thresholds, each only made stricter"
    )
    history_command = commands.add_parser(
        "history", help="print each estimator's accuracy over the latest games scored"
    )
    history_command.add_argument(
        "--games", type=int, default=10, help="how many of the latest games (default: 10)"
    )
    fit_command = commands.add_parser(
        "fit",
        help="refit the win chance and the fights on 20 or more recorded games, if that is better",
    )
    fit_command.add_argument("recordings", nargs="+", help="the recordings (.jsonl.xz)")
    fit_command.add_argument(
        "--write",
        action="store_true",
        help="write the weights kept, which the engine reads at its start",
    )
    anonymize_command = commands.add_parser(
        "anonymize", help="write a copy of a recording with every player's name and id replaced"
    )
    anonymize_command.add_argument("recording", help="the recording (.jsonl.xz)")
    anonymize_command.add_argument(
        "--output", help="the copy's path (.jsonl.xz); default: <recording>-anonymized.jsonl.xz"
    )
    return parser
