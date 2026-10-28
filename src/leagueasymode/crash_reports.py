"""Crash reports: what went wrong in the engine, with nothing of the game in it.

On the first tries on a Mac the engine stopped ("Engine: stopped (exit 1)"), and the app keeps no
log of the engine's, so nothing said why. Now an error in one of the engine's jobs (reading the
game, recording, sending games) is reported and the job started again, and a crash at the start
is reported before the engine stops. A report holds the error's kind, where it happened, and the
lines of code it passed through, shortened so that no folder of the player's shows; never the
error's message, which can hold a player's name or the game's data. Each kind of error is written
once, to `crash-reports/` beside the recordings, and sent with the games
(`recording/sender.py`); the status page's "Errors" counts them all.
"""

import asyncio
import datetime
import logging
import traceback
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from leagueasymode.build_info import build_label
from leagueasymode.engine_status import StatusBoard

CRASH_REPORTS_FOLDER: Final = "crash-reports"
# Of each kind of error, one report; of all, at most this many, so that an error on every answer
# of the game cannot fill the disk.
MOST_REPORTS: Final = 20
# How long a job waits before it is started again, so that one failing at once does not spin.
RESTART_PAUSE_SECONDS: Final = 5.0
# The places a file's path is cut after, from the most telling: this package, an installed one,
# the standard library.
PATH_MARKERS: Final = ("/site-packages/", "/lib/python3.12/", "/lib/python3.13/")
PACKAGE_MARKER: Final = "/leagueasymode/"

logger = logging.getLogger(__name__)


class CrashReport(BaseModel):
    """One error of the engine's: when, in which job, of what kind, through which code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    happened_at: datetime.datetime
    engine_version: str
    where: str
    error_type: str
    # Each as `module/file.py:line in function`, the outermost first.
    frames: list[str]


def code_frames(frames: Sequence[traceback.FrameSummary]) -> list[str]:
    """Return the frames an error passed through, each without the folders it is kept in.

    Args:
        frames: The traceback's frames, the outermost first.

    Returns:
        Each frame as `path:line in function`: from the package's name for this package and an
        installed one, from the module for the standard library, the file's name otherwise.
    """
    return [f"{_short_path(frame.filename)}:{frame.lineno} in {frame.name}" for frame in frames]


def _short_path(file_path: str) -> str:
    """Return a code file's path without the folders it is kept in.

    Args:
        file_path: The file's full path.

    Returns:
        The path from the package or module on, or the file's name.
    """
    normalized = file_path.replace("\\", "/")
    if PACKAGE_MARKER in normalized:
        return "leagueasymode/" + normalized.rpartition(PACKAGE_MARKER)[2]
    for marker in PATH_MARKERS:
        if marker in normalized:
            return normalized.rpartition(marker)[2]
    return normalized.rpartition("/")[2]


def crash_report(where: str, error: BaseException, *, now: datetime.datetime) -> CrashReport:
    """Return the report of an error.

    Args:
        where: The job it happened in, in words: "the engine", "the recorder".
        error: The error.
        now: The time.

    Returns:
        The report, without the error's message.
    """
    return CrashReport(
        happened_at=now,
        engine_version=build_label(),
        where=where,
        error_type=type(error).__name__,
        frames=code_frames(traceback.extract_tb(error.__traceback__)),
    )


def _now() -> datetime.datetime:
    """Return the time now, in UTC.

    Returns:
        The time.
    """
    return datetime.datetime.now(datetime.UTC)


class ErrorReporter:
    """Logs each error, counts them on the status page, and writes each new kind once."""

    def __init__(
        self,
        directory: Path,
        status: StatusBoard | None,
        *,
        clock: Callable[[], datetime.datetime] = _now,
    ) -> None:
        """Keep where reports go and whom to tell.

        Args:
            directory: The crash reports' folder.
            status: The status board; None to tell nothing.
            clock: Returns the time now.
        """
        self.directory: Final = directory
        self.status: Final = status
        self.clock: Final = clock
        self._seen: Final[set[tuple[str, str, tuple[str, ...]]]] = set()
        self._error_count = 0

    def report(self, where: str, error: BaseException) -> None:
        """Report one error.

        Args:
            where: The job it happened in, in words.
            error: The error.
        """
        logger.error("an error in %s", where, exc_info=error)
        self._error_count += 1
        report = crash_report(where, error, now=self.clock())
        last_frame = report.frames[-1] if report.frames else "an unknown place"
        if self.status is not None:
            self.status.set_part(
                "errors",
                "problem",
                f"{self._error_count} so far; the last in {where}: {report.error_type} at "
                f"{last_frame}",
            )
        signature = (where, report.error_type, tuple(report.frames))
        if signature in self._seen or len(self._seen) >= MOST_REPORTS:
            return
        self._seen.add(signature)
        write_crash_report(self.directory, report)


def write_crash_report(directory: Path, report: CrashReport) -> Path:
    """Write a report to its own file in the crash reports' folder.

    Args:
        directory: The folder.
        report: The report.

    Returns:
        The file.
    """
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report.happened_at.strftime("%Y-%m-%dT%H-%M-%SZ")
    same_second_count = len(list(directory.glob(f"crash-{stamp}-*.json")))
    report_path = directory / f"crash-{stamp}-{same_second_count + 1}.json"
    report_path.write_text(report.model_dump_json(indent=2) + "\n")
    return report_path


async def keep_running(
    where: str,
    job: Callable[[], Awaitable[None]],
    reporter: ErrorReporter,
    stop_requested: asyncio.Event,
    *,
    restart_pause_seconds: float = RESTART_PAUSE_SECONDS,
) -> None:
    """Run a job until it ends or a stop is requested, starting it again after each error.

    Args:
        where: The job, in words, for the reports.
        job: Starts the job.
        reporter: Reports each error.
        stop_requested: Set to stop.
        restart_pause_seconds: The wait before the job is started again.
    """
    while not stop_requested.is_set():
        try:
            await job()
        except Exception as error:
            reporter.report(where, error)
            try:
                await asyncio.wait_for(stop_requested.wait(), timeout=restart_pause_seconds)
            except TimeoutError:
                continue
        else:
            return
