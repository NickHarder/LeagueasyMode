"""What the engine sees, part by part: the status page's facts, and the report a test sends back.

Each part (the game's API, the League client, the patch's stats, the recording, ...) is in one of
four states, with a sentence that says why. The report never holds a player's name: the game's
part names the mode, the map, the clock and how many play; the feed's events are counted by name;
a field that cannot be read is named by its place in the answer, never by its value; and a path
starts at `~` instead of the home folder, which carries the account's name.

The engine, the recorder and the command that runs them write to one `StatusBoard`; the overlay's
server serves its report at `/status`, which `overlay/web/src/status.ts` shows. The report's JSON
Schema is kept beside that page in `overlay/web/engine_status.schema.json`.
"""

import datetime
import json
import platform
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from leagueasymode import __version__
from leagueasymode.game_api import NoAnswer
from leagueasymode.game_state import GameSnapshot

type PartState = Literal["ok", "waiting", "problem", "off"]
type PartKey = Literal[
    "game", "client", "patch", "players", "recording", "timeline", "scoring", "settings", "models"
]

# Each part, in the order the page shows them, with what it says before anything happens.
PART_TITLES: Final[dict[PartKey, str]] = {
    "game": "The game",
    "client": "The League client",
    "patch": "Patch stats",
    "players": "Player lookups",
    "recording": "Recording",
    "timeline": "Match timeline",
    "scoring": "After the game",
    "settings": "League's settings",
    "models": "Models",
}
FIRST_DETAILS: Final[dict[PartKey, str]] = {
    "game": "No answer yet",
    "client": "Looked for when a game starts",
    "patch": "Loaded when a game starts",
    "players": "Looked up when a game starts",
    "recording": "Waiting for a game",
    "timeline": "Asked for after each recorded game",
    "scoring": "After the first recorded game",
    "settings": "Not read yet",
    "models": "Not loaded yet",
}
# The feed's events some estimator reads; a test holds this to the estimators' own names.
READ_EVENT_NAMES: Final = frozenset(
    {
        "BaronKill",
        "ChampionKill",
        "DragonKill",
        "GameEnd",
        "HeraldKill",
        "HordeKill",
        "InhibKilled",
        "InhibRespawned",
        "TurretKilled",
    }
)
# The fields that could not be read that the report keeps, the latest ones.
KEPT_UNREADABLE_FIELD_COUNT: Final = 20
SECONDS_PER_MINUTE: Final = 60


class StatusPart(BaseModel):
    """One part of what the engine sees."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: PartKey
    title: str
    state: PartState
    detail: str
    # When it last changed, in UTC (ISO 8601); None while it is as the engine started.
    updated_at: str | None


class SeenEvent(BaseModel):
    """One kind of event in the feed of the game being played, or of the last one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    count: int
    # Whether an estimator reads it; one that none reads may be new this patch.
    is_read: bool


class EngineStatus(BaseModel):
    """The report: what runs where, each part's state, and what the game's answers held."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    platform: str
    python_version: str
    started_at: str
    reported_at: str
    parts: list[StatusPart]
    events: list[SeenEvent]
    # Each field of the game's answer that could not be read, as `place.in.answer: problem`.
    unreadable_fields: list[str]


def utc_now() -> datetime.datetime:
    """Return the time now, in UTC.

    Returns:
        The time.
    """
    return datetime.datetime.now(datetime.UTC)


class StatusBoard:
    """Keeps each part's state as the engine, the recorder and the command report it."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime.datetime] = utc_now,
        home_directory: Path | None = None,
    ) -> None:
        """Start with every part waiting.

        Args:
            clock: Returns the time now, in UTC.
            home_directory: The folder a path is shown from as `~`; the user's own by default.
        """
        self.clock: Final = clock
        self.home_directory: Final = home_directory or Path.home()
        self.started_at: Final = clock()
        self._parts: Final[dict[PartKey, StatusPart]] = {
            key: StatusPart(
                key=key, title=title, state="waiting", detail=FIRST_DETAILS[key], updated_at=None
            )
            for key, title in PART_TITLES.items()
        }
        self._event_counts: Counter[str] = Counter()
        self._unreadable_fields: list[str] = []
        self._last_answer_at: datetime.datetime | None = None

    def set_part(self, key: PartKey, state: PartState, detail: str) -> None:
        """Say how one part stands.

        Args:
            key: The part.
            state: How it stands.
            detail: Why, in a sentence that names no player.
        """
        self._parts[key] = self._parts[key].model_copy(
            update={"state": state, "detail": detail, "updated_at": self.clock().isoformat()}
        )

    def note_no_answer(self, no_answer: NoAnswer) -> None:
        """Say why the game's API gave no answer, and when it last gave one.

        Args:
            no_answer: Why.
        """
        last_answer_text = (
            f"; the last answer came at {self._last_answer_at:%H:%M:%S} UTC"
            if self._last_answer_at is not None
            else ""
        )
        self.set_part(
            "game",
            "problem" if no_answer.is_problem else "waiting",
            no_answer.text + last_answer_text,
        )

    def note_game(self, snapshot: GameSnapshot) -> None:
        """Say that the game answers, what it is, and which events its feed holds.

        Args:
            snapshot: The game's answer, read.
        """
        self._last_answer_at = self.clock()
        self._event_counts = Counter(event.event_name for event in snapshot.event_list.events)
        game_data = snapshot.game_data
        whole_seconds = int(game_data.game_time_seconds)
        minutes, seconds = divmod(whole_seconds, SECONDS_PER_MINUTE)
        spectating_text = "" if snapshot.active_player is not None else "; no player of yours"
        self.set_part(
            "game",
            "ok",
            f"Answering: {game_data.game_mode or 'an unnamed mode'} on map "
            f"{game_data.map_number}, {minutes}:{seconds:02d} in, "
            f"{len(snapshot.players)} players{spectating_text}",
        )

    def note_unreadable_answer(self, error: ValidationError) -> None:
        """Say that the game answers in a shape the engine cannot read, and where.

        Args:
            error: What reading the answer found; only the fields' places and the problems'
                kinds are kept, never the values, which can hold names.
        """
        for problem in error.errors(include_url=False, include_input=False, include_context=False):
            field_text = ".".join(str(place) for place in problem["loc"]) + ": " + problem["type"]
            if field_text not in self._unreadable_fields:
                self._unreadable_fields.append(field_text)
        del self._unreadable_fields[:-KEPT_UNREADABLE_FIELD_COUNT]
        self.set_part(
            "game",
            "problem",
            f"Answering, but {error.error_count()} fields could not be read, so the overlay "
            "shows nothing: the fields are listed below",
        )

    def path_text(self, path: Path) -> str:
        """Return a path to show: from `~` when it is in the home folder.

        Args:
            path: The path.

        Returns:
            The path's text.
        """
        if path.is_relative_to(self.home_directory):
            return str(Path("~") / path.relative_to(self.home_directory))
        return str(path)

    def report(self) -> EngineStatus:
        """Return the report as it stands now.

        Returns:
            The report.
        """
        return EngineStatus(
            version=__version__,
            platform=platform.platform(terse=True),
            python_version=platform.python_version(),
            started_at=self.started_at.isoformat(),
            reported_at=self.clock().isoformat(),
            parts=list(self._parts.values()),
            events=[
                SeenEvent(name=name, count=count, is_read=name in READ_EVENT_NAMES)
                for name, count in sorted(self._event_counts.items())
            ],
            unreadable_fields=list(self._unreadable_fields),
        )


def duration_text(seconds: float) -> str:
    """Return a wait as a person says it: in minutes from a minute up, in seconds below.

    Args:
        seconds: The wait.

    Returns:
        The text, such as "10 minutes" or "0.3 s".
    """
    if seconds >= SECONDS_PER_MINUTE:
        return f"{seconds / SECONDS_PER_MINUTE:g} minutes"
    return f"{seconds:g} s"


if __name__ == "__main__":
    sys.stdout.write(json.dumps(EngineStatus.model_json_schema(), indent=2) + "\n")
