"""Problem reports: one click on the Mac sends what is needed to find what went wrong.

The owner (2026-10-28) asked for "a snap shot way to upload issues for you easily": after the
first tests, each problem took rounds of describing, screenshots and guesses. "Report a problem…"
in the app's menu, or its shortcut, asks the engine for a report, which goes to
`reports/report-<time>/` beside the recordings and is sent to the games' repository at once
(`recording/sender.py`):

- `report.json`: when, the build, the player's note if they wrote one, the app's own lines from
  its menu (the engine, the overlay page, League's window, the keyboard), the status page's report,
  and the names of the crash reports so far;
- `engine-log.txt` and `previous-engine-log.txt`: the end of this run's engine log and of the run
  before, which holds the reason when the engine stopped and the app started it again;
- `game-so-far.jsonl.xz`: the newest recording, anonymized as every sent game is.

Every name the engine has seen in a game's answer, and the player's home folder, are scrubbed from
the note and the logs; the game is anonymized or left out, never sent as it is.
"""

import datetime
import logging
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue

from leagueasymode.build_info import build_label
from leagueasymode.crash_reports import CRASH_REPORTS_FOLDER
from leagueasymode.engine_status import EngineStatus
from leagueasymode.recording.anonymize import IdentityLeakError, anonymize_recording
from leagueasymode.recording.file_format import COMPRESSED_SUFFIX, PLAIN_SUFFIX

REPORTS_FOLDER: Final = "reports"
LOG_TAIL_LINES: Final = 500
SCRUBBED_NAME: Final = "[player]"
# A name this short is a part of too many words to be replaced safely.
SHORTEST_SCRUBBED_NAME: Final = 3
NAME_FIELDS: Final = ("summonerName", "riotId", "riotIdGameName")
RIOT_ID_SEPARATOR: Final = "#"

logger = logging.getLogger(__name__)


class ProblemReport(BaseModel):
    """What a problem report says, beside the logs and the game it carries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    made_at: datetime.datetime
    build: str
    note: str
    app_facts: dict[str, str]
    status: EngineStatus
    crash_reports: list[str]


def player_identities(payload: JsonValue | None) -> set[str]:
    """Return every name a game's answer gives its players.

    Args:
        payload: The game's answer; None when there was none.

    Returns:
        Each summoner name, Riot ID, and Riot ID's game name.
    """
    players = payload.get("allPlayers") if isinstance(payload, dict) else None
    identities: set[str] = set()
    for player in players if isinstance(players, list) else []:
        if not isinstance(player, dict):
            continue
        for field_name in NAME_FIELDS:
            name = player.get(field_name)
            if isinstance(name, str) and name:
                identities.update({name, name.partition(RIOT_ID_SEPARATOR)[0]})
    return identities


def scrub(text: str, identities: Iterable[str], home_directory: Path) -> str:
    """Return a text without the players' names and the player's home folder.

    Args:
        text: The text.
        identities: The names to take out.
        home_directory: The home folder, shown as `~`.

    Returns:
        The text, each name `[player]`.
    """
    scrubbed = text.replace(str(home_directory), "~")
    for identity in sorted(identities, key=len, reverse=True):
        if len(identity) >= SHORTEST_SCRUBBED_NAME:
            scrubbed = scrubbed.replace(identity, SCRUBBED_NAME)
    return scrubbed


def make_problem_report(
    *,
    recordings_directory: Path,
    note: str,
    app_facts: dict[str, str],
    status_report: EngineStatus,
    engine_log: Path | None,
    identities: set[str],
    home_directory: Path,
    now: datetime.datetime,
) -> Path:
    """Write a problem report into its own folder, ready to be sent.

    Args:
        recordings_directory: The recordings' folder; the report goes in its `reports/`.
        note: What the player wrote; empty when nothing.
        app_facts: The app's own lines, by name.
        status_report: The status page's report.
        engine_log: This run's engine log; None when the app keeps none.
        identities: Every name seen in a game's answer this run.
        home_directory: The home folder, scrubbed from every text.
        now: The time.

    Returns:
        The report's folder.
    """
    report_directory = recordings_directory / REPORTS_FOLDER / f"report-{now:%Y-%m-%dT%H-%M-%SZ}"
    report_directory.mkdir(parents=True, exist_ok=True)
    crash_directory = recordings_directory / CRASH_REPORTS_FOLDER
    report = ProblemReport(
        made_at=now,
        build=build_label(),
        note=scrub(note, identities, home_directory),
        app_facts={
            name: scrub(value, identities, home_directory) for name, value in app_facts.items()
        },
        status=status_report,
        crash_reports=sorted(path.name for path in crash_directory.glob("*.json"))
        if crash_directory.is_dir()
        else [],
    )
    (report_directory / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
    if engine_log is not None:
        for log_path, copy_name in (
            (engine_log, "engine-log.txt"),
            (engine_log.with_name("engine.1.log"), "previous-engine-log.txt"),
        ):
            if log_path.is_file():
                (report_directory / copy_name).write_text(
                    scrub(_tail(log_path), identities, home_directory)
                )
    _copy_the_game_so_far(recordings_directory, report_directory)
    return report_directory


def _tail(log_path: Path) -> str:
    """Return the last lines of a log.

    Args:
        log_path: The log.

    Returns:
        Its last `LOG_TAIL_LINES` lines.
    """
    lines = log_path.read_text(errors="replace").splitlines(keepends=True)
    return "".join(lines[-LOG_TAIL_LINES:])


def _copy_the_game_so_far(recordings_directory: Path, report_directory: Path) -> None:
    """Put an anonymized copy of the newest recording into the report, if one can be made safely.

    Args:
        recordings_directory: The recordings' folder.
        report_directory: The report's folder.
    """
    recordings = [
        *recordings_directory.glob(f"*{PLAIN_SUFFIX}"),
        *recordings_directory.glob(f"*{COMPRESSED_SUFFIX}"),
    ]
    games = [path for path in recordings if "-anonymized" not in path.name]
    if not games:
        return
    newest = max(games, key=lambda path: path.stat().st_mtime)
    with tempfile.TemporaryDirectory(prefix="leagueasymode-report-") as temporary_directory:
        try:
            copy = anonymize_recording(newest, Path(temporary_directory) / "game-so-far.jsonl")
        except IdentityLeakError:
            logger.warning("left the game out of the report: a name could not be removed")
            return
        except Exception:
            logger.exception("left the game out of the report: it could not be read")
            return
        (report_directory / "game-so-far.jsonl.xz").write_bytes(copy.read_bytes())
