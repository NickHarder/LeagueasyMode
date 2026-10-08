"""What a recording file holds: one JSON object a line, each a record of one kind.

A recording starts with `recording_started`. Each answer of the game's API follows as a
`snapshot_keyframe` (the whole answer) or a `snapshot_delta` (what changed since the previous
answer); a keyframe comes first and then at a fixed interval, so a reader can start from any
keyframe and a damaged line costs at most one interval. What the League client served is kept as
`client_resource` lines, and `recording_ended` says why the recording stopped.

A recording is written as `<name>.jsonl`, a line at a time so that a crash loses at most the line
being written, and compressed to `<name>.jsonl.xz` when it is closed.
"""

import datetime
from dataclasses import dataclass
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from leagueasymode.recording.delta import PatchOperation

FORMAT_VERSION: Final = 1
PLAIN_SUFFIX: Final = ".jsonl"
COMPRESSED_SUFFIX: Final = ".jsonl.xz"


class RecordingFormatError(Exception):
    """A file is not a recording, or is one this version cannot read."""


class RecordingStarted(BaseModel):
    """The first line: which format the file is in, and when and how the recording was made."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["recording_started"] = "recording_started"
    format_version: int
    recorder_version: str
    started_at: datetime.datetime
    poll_interval_seconds: float


class SnapshotKeyframe(BaseModel):
    """One answer of the game's API, whole."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["snapshot_keyframe"] = "snapshot_keyframe"
    received_at_seconds: float
    payload: JsonValue


class SnapshotDelta(BaseModel):
    """One answer of the game's API, as the changes from the answer before it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["snapshot_delta"] = "snapshot_delta"
    received_at_seconds: float
    operations: list[PatchOperation]


class ClientResource(BaseModel):
    """One answer of the League client's local API, with the path it was asked for."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["client_resource"] = "client_resource"
    received_at_seconds: float
    path: str
    payload: JsonValue


class RecordingEnded(BaseModel):
    """The last line: why the recording stopped."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["recording_ended"] = "recording_ended"
    received_at_seconds: float
    reason: str


type RecordingLine = Annotated[
    RecordingStarted | SnapshotKeyframe | SnapshotDelta | ClientResource | RecordingEnded,
    Field(discriminator="kind"),
]

RECORDING_LINE_ADAPTER: Final = TypeAdapter[RecordingLine](RecordingLine)


@dataclass(frozen=True, slots=True)
class GameFrame:
    """One answer of the game's API, whole again, and when it arrived.

    A dataclass and not a model: the payload was validated as JSON when its line was read, and
    validating it again for every frame would cost more than the rest of reading.
    """

    received_at_seconds: float
    payload: JsonValue
