"""Serve a recorded game as if it were running: a stand-in for the game's API, for work and tests.

`leagueasymode replay <recording>` answers `/liveclientdata/allgamedata` (and the narrower routes
cut from it) with the snapshot the recording held at that moment, from the first snapshot on, at
the speed asked for. Once the recording is over it answers as the game does when no game runs. It
serves plain HTTP on 127.0.0.1, so the engine is pointed at it with
`LEAGUEASYMODE_GAME_API_BASE_URL=http://127.0.0.1:<port>`.
"""

import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Final

from aiohttp import web
from pydantic import JsonValue

from leagueasymode.recording.delta import apply_patch
from leagueasymode.recording.file_format import (
    ClientResource,
    RecordingFormatError,
    SnapshotDelta,
    SnapshotKeyframe,
)
from leagueasymode.recording.reader import iter_recording_lines

DEFAULT_REPLAY_PORT: Final = 2998
# How long after its last snapshot a replayed game still answers, as the real one does on the
# victory screen.
LINGER_AFTER_LAST_SNAPSHOT_SECONDS: Final = 5.0
NOT_RUNNING_ANSWER: Final = {
    "errorCode": "RESOURCE_NOT_FOUND",
    "httpStatus": 404,
    "message": "the replayed game is over",
}
# The narrower routes of the game's API, each one part of the whole answer.
PART_ROUTES: Final = {
    "/liveclientdata/activeplayer": "activePlayer",
    "/liveclientdata/playerlist": "allPlayers",
    "/liveclientdata/eventdata": "events",
    "/liveclientdata/gamestats": "gameData",
}


class RecordingReplay:
    """A recording's snapshots, played forward against a clock."""

    def __init__(
        self, recording_path: Path, speed: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Read the recording's snapshots, and start the replay's clock.

        Args:
            recording_path: The recording.
            speed: How many seconds of the game pass for each second of the clock.
            clock: The clock, in seconds; the replay starts at its current reading.

        Raises:
            RecordingFormatError: The recording holds no snapshot.
        """
        recording_lines = list(iter_recording_lines(recording_path))
        self.snapshot_lines: Final = [
            line for line in recording_lines if isinstance(line, SnapshotKeyframe | SnapshotDelta)
        ]
        self.client_resources: Final = [
            line for line in recording_lines if isinstance(line, ClientResource)
        ]
        if not self.snapshot_lines or not isinstance(self.snapshot_lines[0], SnapshotKeyframe):
            raise RecordingFormatError(f"{recording_path} holds no snapshot to replay")
        self.speed: Final = speed
        self.clock: Final = clock
        self.started_at_clock_seconds: Final = clock()
        self.first_received_at_seconds: Final = self.snapshot_lines[0].received_at_seconds
        self.last_received_at_seconds: Final = self.snapshot_lines[-1].received_at_seconds
        self._next_line_index = 0
        self._current_payload: JsonValue = None

    def recording_seconds_now(self) -> float:
        """Return the moment of the recording the replay has reached.

        Returns:
            Seconds since the recording started, as its records count them.
        """
        elapsed_clock_seconds = self.clock() - self.started_at_clock_seconds
        return self.first_received_at_seconds + elapsed_clock_seconds * self.speed

    def client_resource_now(self, path: str) -> JsonValue | None:
        """Return what the League client served for a path, as of this moment of the replay.

        Args:
            path: The resource's path.

        Returns:
            The latest answer recorded for the path up to now, or None when there is none yet.
        """
        recording_seconds = self.recording_seconds_now()
        reached_answers = [
            resource.payload
            for resource in self.client_resources
            if resource.path == path and resource.received_at_seconds <= recording_seconds
        ]
        return reached_answers[-1] if reached_answers else None

    def payload_now(self) -> JsonValue | None:
        """Return the snapshot the recording held at this moment of the replay.

        Returns:
            The snapshot, or None once the replayed game is over.
        """
        recording_seconds = self.recording_seconds_now()
        if recording_seconds > self.last_received_at_seconds + LINGER_AFTER_LAST_SNAPSHOT_SECONDS:
            return None
        while (
            self._next_line_index < len(self.snapshot_lines)
            and self.snapshot_lines[self._next_line_index].received_at_seconds <= recording_seconds
        ):
            self._apply(self.snapshot_lines[self._next_line_index])
            self._next_line_index += 1
        return self._current_payload

    def _apply(self, line: SnapshotKeyframe | SnapshotDelta) -> None:
        """Move the current snapshot on by one line of the recording.

        Args:
            line: The next snapshot line.
        """
        if isinstance(line, SnapshotKeyframe):
            self._current_payload = line.payload
        else:
            self._current_payload = apply_patch(self._current_payload, line.operations)


def create_replay_application(replay: RecordingReplay) -> web.Application:
    """Return a web application that answers like the game's API, from a replay.

    Args:
        replay: The replay to serve.

    Returns:
        The application.
    """
    application = web.Application()

    async def all_game_data(_request: web.Request) -> web.Response:
        payload = replay.payload_now()
        if payload is None:
            return web.json_response(NOT_RUNNING_ANSWER, status=404)
        return web.json_response(payload)

    def part_route(part_key: str) -> Callable[[web.Request], Awaitable[web.Response]]:
        async def part(_request: web.Request) -> web.Response:
            payload = replay.payload_now()
            if not isinstance(payload, dict) or part_key not in payload:
                return web.json_response(NOT_RUNNING_ANSWER, status=404)
            return web.json_response(payload[part_key])

        return part

    async def client_resource(request: web.Request) -> web.Response:
        # With its query, as the recorder kept it: match history is asked for with one.
        payload = replay.client_resource_now(request.path_qs)
        if payload is None:
            return web.json_response({"message": "not in the recording yet"}, status=404)
        return web.json_response(payload)

    application.router.add_get("/liveclientdata/allgamedata", all_game_data)
    # The League client's resources are all under /lol-…; the replay serves them without a
    # password, so the engine is pointed at it with LEAGUEASYMODE_LEAGUE_CLIENT_BASE_URL.
    application.router.add_get("/{client_path:lol-.+}", client_resource)
    for route_path, part_key in PART_ROUTES.items():
        application.router.add_get(route_path, part_route(part_key))
    return application
