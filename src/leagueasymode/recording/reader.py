"""Read a recording back: its lines as records, or its game snapshots whole again."""

import lzma
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

from pydantic import JsonValue, ValidationError

from leagueasymode.recording.delta import apply_patch
from leagueasymode.recording.file_format import (
    COMPRESSED_SUFFIX,
    FORMAT_VERSION,
    RECORDING_LINE_ADAPTER,
    GameFrame,
    RecordingFormatError,
    RecordingLine,
    RecordingStarted,
    SnapshotDelta,
    SnapshotKeyframe,
)


def iter_recording_lines(recording_path: Path) -> Iterator[RecordingLine]:
    """Yield each record of a recording, compressed or not, in the order it was written.

    A last line cut off part way, as a crash leaves it, is skipped; a damaged line anywhere else is
    an error.

    Args:
        recording_path: A `.jsonl` or `.jsonl.xz` recording.

    Yields:
        The records, the header first.

    Raises:
        RecordingFormatError: The file is not a recording, is in a newer format, or has a damaged
            line before its last.
    """
    with _open_text(recording_path) as recording_file:
        is_first_line = True
        for line_number, raw_line in enumerate(recording_file, start=1):
            is_complete_line = raw_line.endswith("\n")
            try:
                record = RECORDING_LINE_ADAPTER.validate_json(raw_line)
            except ValidationError as error:
                if not is_complete_line and not is_first_line:
                    return
                raise RecordingFormatError(
                    f"{recording_path}:{line_number} is not a recording line"
                    + (": a recording starts with recording_started" if is_first_line else "")
                ) from error
            if is_first_line:
                _check_header(record, recording_path)
                is_first_line = False
            yield record
        if is_first_line:
            raise RecordingFormatError(
                f"{recording_path} is empty: a recording starts with recording_started"
            )


def iter_game_frames(recording_path: Path) -> Iterator[GameFrame]:
    """Yield each answer of the game's API in a recording, whole, in the order it arrived.

    Args:
        recording_path: A `.jsonl` or `.jsonl.xz` recording.

    Yields:
        The frames. Each payload is a separate object, which the caller may keep or change.

    Raises:
        RecordingFormatError: A delta comes before any keyframe.
    """
    current_payload: JsonValue = None
    has_keyframe = False
    for record in iter_recording_lines(recording_path):
        if isinstance(record, SnapshotKeyframe):
            current_payload = record.payload
            has_keyframe = True
        elif isinstance(record, SnapshotDelta):
            if not has_keyframe:
                raise RecordingFormatError(f"{recording_path} has a delta before any keyframe")
            current_payload = apply_patch(current_payload, record.operations)
        else:
            continue
        yield GameFrame(received_at_seconds=record.received_at_seconds, payload=current_payload)


def _open_text(recording_path: Path) -> TextIO:
    """Open a recording for reading as text, decompressing it when it ends in `.jsonl.xz`.

    Args:
        recording_path: The recording.

    Returns:
        The open file.
    """
    if recording_path.name.endswith(COMPRESSED_SUFFIX):
        return lzma.open(recording_path, "rt", encoding="utf-8")
    return recording_path.open(encoding="utf-8")


def _check_header(record: RecordingLine, recording_path: Path) -> None:
    """Refuse a first line that is not a header this version can read.

    Args:
        record: The first record of the file.
        recording_path: The file, for the error message.

    Raises:
        RecordingFormatError: The record is not a header, or names a format this version cannot
            read.
    """
    if not isinstance(record, RecordingStarted):
        raise RecordingFormatError(f"{recording_path} does not start with recording_started")
    if record.format_version != FORMAT_VERSION:
        raise RecordingFormatError(
            f"{recording_path} is in recording format version {record.format_version};"
            f" this version reads version {FORMAT_VERSION}"
        )
