"""Write a recording a line at a time, and compress it when it is closed."""

import datetime
import lzma
from pathlib import Path
from typing import Final, TextIO

from pydantic import BaseModel, JsonValue

from leagueasymode.recording.delta import compute_patch
from leagueasymode.recording.file_format import (
    COMPRESSED_SUFFIX,
    FORMAT_VERSION,
    PLAIN_SUFFIX,
    ClientResource,
    RecordingEnded,
    RecordingFormatError,
    RecordingLine,
    RecordingStarted,
    SnapshotDelta,
    SnapshotKeyframe,
)
from leagueasymode.recording.reader import iter_recording_lines

DEFAULT_KEYFRAME_INTERVAL_SECONDS: Final = 60.0
# xz's preset 6 keeps an 8 MiB dictionary, so a snapshot is compressed against the keyframes and
# snapshots before it, not only against the last 32 KiB as gzip would.
XZ_PRESET: Final = 6


class RecordingWriter:
    """Appends the lines of one recording to `<name>.jsonl`, flushing each one.

    The methods block on the file. Code running in an event loop calls them through
    `asyncio.to_thread`.
    """

    def __init__(
        self, plain_path: Path, keyframe_interval_seconds: float = DEFAULT_KEYFRAME_INTERVAL_SECONDS
    ) -> None:
        """Open `plain_path` for appending.

        Args:
            plain_path: Where the recording is written while it is open; it ends in `.jsonl`.
            keyframe_interval_seconds: How long after one whole snapshot the next is written whole.

        Raises:
            ValueError: The path does not end in `.jsonl`.
        """
        if not plain_path.name.endswith(PLAIN_SUFFIX):
            raise ValueError(f"a recording is written to a {PLAIN_SUFFIX} file: {plain_path}")
        self.plain_path: Final = plain_path
        self.keyframe_interval_seconds: Final = keyframe_interval_seconds
        self._file: Final[TextIO] = plain_path.open("a", encoding="utf-8")
        self._has_started = False
        self._previous_payload: JsonValue = None
        self._last_keyframe_at_seconds: float | None = None

    def write_started(
        self, started_at: datetime.datetime, recorder_version: str, poll_interval_seconds: float
    ) -> None:
        """Write the first line, which every reader checks.

        Args:
            started_at: When the recording started, with a time zone.
            recorder_version: The version of the program that records.
            poll_interval_seconds: How often the game's API is asked.
        """
        self._write_line(
            RecordingStarted(
                format_version=FORMAT_VERSION,
                recorder_version=recorder_version,
                started_at=started_at,
                poll_interval_seconds=poll_interval_seconds,
            )
        )
        self._has_started = True

    def write_snapshot(self, received_at_seconds: float, payload: JsonValue) -> None:
        """Write one answer of the game's API, whole or as what changed since the previous one.

        Args:
            received_at_seconds: When it arrived, in seconds since the recording started.
            payload: The answer.
        """
        self._require_started()
        is_keyframe_due = (
            self._last_keyframe_at_seconds is None
            or received_at_seconds - self._last_keyframe_at_seconds
            >= self.keyframe_interval_seconds
        )
        if is_keyframe_due:
            self._write_line(
                SnapshotKeyframe(received_at_seconds=received_at_seconds, payload=payload)
            )
            self._last_keyframe_at_seconds = received_at_seconds
        else:
            self._write_line(
                SnapshotDelta(
                    received_at_seconds=received_at_seconds,
                    operations=compute_patch(self._previous_payload, payload),
                )
            )
        self._previous_payload = payload

    def write_client_resource(
        self, received_at_seconds: float, path: str, payload: JsonValue
    ) -> None:
        """Write one answer of the League client's local API.

        Args:
            received_at_seconds: When it arrived, in seconds since the recording started.
            path: The path that was asked for.
            payload: The answer.
        """
        self._require_started()
        self._write_line(
            ClientResource(received_at_seconds=received_at_seconds, path=path, payload=payload)
        )

    def write_ended(self, received_at_seconds: float, reason: str) -> None:
        """Write the last line.

        Args:
            received_at_seconds: When the recording stopped, in seconds since it started.
            reason: Why it stopped, in a few words.
        """
        self._require_started()
        self._write_line(RecordingEnded(received_at_seconds=received_at_seconds, reason=reason))

    def close(self) -> Path:
        """Close the file, compress it to `<name>.jsonl.xz`, and remove the plain file.

        The plain file is removed only after the compressed one is complete, so a crash while
        compressing leaves the plain file to read.

        Returns:
            The compressed recording's path.
        """
        self._file.close()
        return compress_recording(self.plain_path)

    def abandon(self) -> None:
        """Close the file and leave it uncompressed, as a crash would."""
        self._file.close()

    def _require_started(self) -> None:
        """Refuse to write a record before the first line.

        Raises:
            RecordingFormatError: `write_started` has not been called.
        """
        if not self._has_started:
            raise RecordingFormatError("call write_started before writing anything else")

    def _write_line(self, record: BaseModel) -> None:
        """Write one record as one line, and flush it.

        Args:
            record: The record.
        """
        self._file.write(record.model_dump_json() + "\n")
        self._file.flush()


def compress_recording(plain_path: Path) -> Path:
    """Compress a closed recording to `<name>.jsonl.xz`, and remove the plain file.

    The plain file is removed only after the compressed one is complete, so a crash while
    compressing leaves the plain file to read.

    Args:
        plain_path: The closed `.jsonl` recording.

    Returns:
        The compressed recording's path.
    """
    stem = plain_path.name.removesuffix(PLAIN_SUFFIX)
    compressed_path = plain_path.with_name(stem + COMPRESSED_SUFFIX)
    partial_path = compressed_path.with_name(compressed_path.name + ".partial")
    with (
        plain_path.open("rb") as plain_file,
        lzma.open(partial_path, "wb", preset=XZ_PRESET) as compressed_file,
    ):
        for chunk in iter(lambda: plain_file.read(1 << 20), b""):
            compressed_file.write(chunk)
    partial_path.replace(compressed_path)
    plain_path.unlink()
    return compressed_path


def close_unfinished_recording(plain_path: Path, reason: str) -> Path:
    """Close a recording an engine left open, as when the app quit before the game's timeline came.

    The recording keeps every whole line; a last line cut part way is dropped. One with no last
    line gets one, at the time of its last record, saying why; then it is compressed like any.

    Args:
        plain_path: The open `.jsonl` recording, which nothing writes any more.
        reason: Why it stopped, for its last line.

    Returns:
        The compressed recording's path.

    Raises:
        RecordingFormatError: The file is not a recording.
    """
    records = list(iter_recording_lines(plain_path))
    written_bytes = plain_path.read_bytes()
    whole_lines = written_bytes[: written_bytes.rfind(b"\n") + 1]
    plain_path.write_bytes(whole_lines + _ending_line(records, reason))
    return compress_recording(plain_path)


def _ending_line(records: list[RecordingLine], reason: str) -> bytes:
    """Return the last line a recording lacks, or nothing when it has one.

    Args:
        records: The recording's records.
        reason: Why it stopped.

    Returns:
        The line, at the time of the last record, or empty bytes.
    """
    if isinstance(records[-1], RecordingEnded):
        return b""
    last_seconds = max(
        (
            record.received_at_seconds
            for record in records
            if not isinstance(record, RecordingStarted)
        ),
        default=0.0,
    )
    ended = RecordingEnded(received_at_seconds=last_seconds, reason=reason)
    return (ended.model_dump_json() + "\n").encode()
