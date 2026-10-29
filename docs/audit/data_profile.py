"""Profile recordings for the data-quality audit: what the game and the client really answered.

Run it on a directory of recordings (`.jsonl` or `.jsonl.xz`, searched recursively):

    uv run python docs/audit/data_profile.py <recordings directory>

or on a recording built from the tests' payloads, written to a directory of your choosing:

    uv run python docs/audit/data_profile.py --build-from-test-payloads <empty directory>

For every recording it prints the duration, the frames, keyframes and deltas, the game mode and
map, whether the game clock ever goes backwards, the gaps between answers longer than 2 s, the
missing and empty rates of the scoreboard fields the engine reads, the kill feed's names and
duplicate event ids, implausible values, and which League-client resources were recorded. It reads
only; it never prints a player's name, only whether a name looks like an anonymizer pseudonym.
"""

import argparse
import re
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from pydantic import JsonValue

from leagueasymode.recording.file_format import (
    ClientResource,
    RecordingEnded,
    RecordingStarted,
    SnapshotDelta,
    SnapshotKeyframe,
)
from leagueasymode.recording.reader import iter_game_frames, iter_recording_lines

ANSWER_GAP_THRESHOLD_SECONDS: Final = 2.0
MAXIMUM_CHAMPION_LEVEL: Final = 18
PSEUDONYM_PATTERN: Final = re.compile(r"^Player \d+$")
# The scoreboard fields the estimators read, as a path into each entry of `allPlayers`.
PLAYER_FIELD_PATHS: Final = (
    ("championName",),
    ("rawChampionName",),
    ("team",),
    ("level",),
    ("scores", "creepScore"),
    ("items",),
    ("respawnTimer",),
    ("position",),
    ("riotIdGameName",),
    ("riotId",),
    ("summonerName",),
    ("summonerSpells",),
)
KILL_FEED_NAME_FIELDS: Final = ("KillerName", "VictimName")
# Each client resource the engine or the scoring reads, by a prefix of its path.
CLIENT_RESOURCE_KINDS: Final = (
    ("gameflow session", "/lol-gameflow/v1/session"),
    ("game version", "/lol-patch/v1/game-version"),
    ("items", "/lol-game-data/assets/v1/items.json"),
    ("champion summary", "/lol-game-data/assets/v1/champion-summary.json"),
    ("champion details", "/lol-game-data/assets/v1/champions/"),
    ("summoner spells", "/lol-game-data/assets/v1/summoner-spells.json"),
    ("runes", "/lol-game-data/assets/v1/perks.json"),
    ("rune styles", "/lol-game-data/assets/v1/perkstyles.json"),
    ("ranked stats", "/lol-ranked/v1/ranked-stats/"),
    ("match history", "/lol-match-history/v1/products/lol/"),
    ("timeline", "/lol-match-history/v1/game-timelines/"),
    ("game details", "/lol-match-history/v1/games/"),
    ("end-of-game stats", "/lol-end-of-game/v1/eog-stats-block"),
)


@dataclass
class FieldTally:
    """How often one scoreboard field was missing, null or empty, over every player row."""

    missing_count: int = 0
    null_count: int = 0
    empty_count: int = 0


@dataclass
class RecordingProfile:
    """What one recording holds, counted as it is read."""

    recording_path: Path
    recorder_version: str = ""
    poll_interval_seconds: float = 0.0
    keyframe_count: int = 0
    delta_count: int = 0
    frame_count: int = 0
    ended_reason: str = "(no recording_ended line)"
    last_received_at_seconds: float = 0.0
    game_modes: Counter[str] = field(default_factory=Counter)
    map_numbers: Counter[str] = field(default_factory=Counter)
    first_game_time_seconds: float | None = None
    last_game_time_seconds: float | None = None
    game_time_backward_steps: list[tuple[float, float]] = field(default_factory=list)
    answer_gaps_seconds: list[tuple[float, float]] = field(default_factory=list)
    frames_without_players: int = 0
    frames_with_active_player_error: int = 0
    player_rows: int = 0
    field_tallies: dict[str, FieldTally] = field(default_factory=dict)
    names_not_pseudonyms: int = 0
    names_pseudonyms: int = 0
    event_names: Counter[str] = field(default_factory=Counter)
    kill_feed_events: int = 0
    kill_feed_names_missing: int = 0
    duplicate_event_ids_in_frame: int = 0
    event_ids_with_changed_content: set[int] = field(default_factory=set)
    negative_gold_frames: int = 0
    level_out_of_range: int = 0
    creep_score_decreases: int = 0
    negative_respawn_timers: int = 0
    # The last creep score seen in each scoreboard slot, to catch one that goes down.
    creep_scores_by_slot: dict[int, int] = field(default_factory=dict)
    client_resources: Counter[str] = field(default_factory=Counter)
    client_resource_errors: Counter[str] = field(default_factory=Counter)


def value_at(container: JsonValue, field_path: tuple[str, ...]) -> tuple[bool, JsonValue]:
    """Return whether a nested field is present, and its value.

    Args:
        container: A JSON object.
        field_path: The keys, outermost first.

    Returns:
        (True, the value) when every key is present, else (False, None).
    """
    current_value: JsonValue = container
    for key in field_path:
        if not isinstance(current_value, dict) or key not in current_value:
            return False, None
        current_value = current_value[key]
    return True, current_value


def classify_client_path(resource_path: str) -> str:
    """Return the kind of a client resource, or "other" for a path the profile does not know.

    Args:
        resource_path: The path the client was asked for.

    Returns:
        The kind's name.
    """
    return next(
        (kind for kind, prefix in CLIENT_RESOURCE_KINDS if resource_path.startswith(prefix)),
        "other",
    )


def profile_players(profile: RecordingProfile, payload: dict[str, JsonValue]) -> None:
    """Count the scoreboard's missing fields and implausible values in one frame.

    Args:
        profile: The profile to add to.
        payload: One whole answer of `/liveclientdata/allgamedata`.
    """
    players = payload.get("allPlayers")
    if not isinstance(players, list) or not players:
        profile.frames_without_players += 1
        return
    for player_index, player in enumerate(players):
        profile.player_rows += 1
        tally_player_fields(profile, player)
        check_player_values(profile, player_index, player)


def tally_player_fields(profile: RecordingProfile, player: JsonValue) -> None:
    """Count which of the fields the engine reads one scoreboard row lacks, holds null or empty.

    Args:
        profile: The profile to add to.
        player: One entry of `allPlayers`.
    """
    for field_path in PLAYER_FIELD_PATHS:
        tally = profile.field_tallies.setdefault(".".join(field_path), FieldTally())
        is_present, field_value = value_at(player, field_path)
        if not is_present:
            tally.missing_count += 1
        elif field_value is None:
            tally.null_count += 1
        elif field_value in ("", [], {}):
            tally.empty_count += 1


def check_player_values(profile: RecordingProfile, player_index: int, player: JsonValue) -> None:
    """Count one scoreboard row's implausible values, and whether its name is a pseudonym.

    Args:
        profile: The profile to add to.
        player_index: The row's place on the scoreboard, to follow its creep score.
        player: One entry of `allPlayers`.
    """
    is_name_present, game_name = value_at(player, ("riotIdGameName",))
    if is_name_present and isinstance(game_name, str) and game_name:
        if PSEUDONYM_PATTERN.match(game_name):
            profile.names_pseudonyms += 1
        else:
            profile.names_not_pseudonyms += 1
    _, level = value_at(player, ("level",))
    if isinstance(level, int) and not 1 <= level <= MAXIMUM_CHAMPION_LEVEL:
        profile.level_out_of_range += 1
    _, respawn_timer = value_at(player, ("respawnTimer",))
    if isinstance(respawn_timer, int | float) and respawn_timer < 0:
        profile.negative_respawn_timers += 1
    _, creep_score = value_at(player, ("scores", "creepScore"))
    if isinstance(creep_score, int):
        previous_creep_score = profile.creep_scores_by_slot.get(player_index)
        if previous_creep_score is not None and creep_score < previous_creep_score:
            profile.creep_score_decreases += 1
        profile.creep_scores_by_slot[player_index] = creep_score


def profile_events(
    profile: RecordingProfile,
    payload: dict[str, JsonValue],
    events_by_id: dict[int, JsonValue],
) -> None:
    """Count the kill feed's missing names and repeated event ids in one frame.

    Args:
        profile: The profile to add to.
        payload: One whole answer of `/liveclientdata/allgamedata`.
        events_by_id: Every event seen so far in this recording, by its id; added to.
    """
    _, events = value_at(payload, ("events", "Events"))
    if not isinstance(events, list):
        return
    event_id_counts = Counter(event.get("EventID") for event in events if isinstance(event, dict))
    profile.duplicate_event_ids_in_frame += sum(
        count - 1 for count in event_id_counts.values() if count > 1
    )
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = event.get("EventID")
        if not isinstance(event_id, int):
            continue
        if event_id in events_by_id:
            if events_by_id[event_id] != event:
                profile.event_ids_with_changed_content.add(event_id)
            continue
        events_by_id[event_id] = event
        event_name = str(event.get("EventName"))
        profile.event_names[event_name] += 1
        if event_name == "ChampionKill":
            profile.kill_feed_events += 1
            profile.kill_feed_names_missing += sum(
                1 for name_field in KILL_FEED_NAME_FIELDS if not event.get(name_field)
            )


def profile_recording(recording_path: Path) -> RecordingProfile:
    """Read one recording and count everything the audit asks about.

    Args:
        recording_path: A `.jsonl` or `.jsonl.xz` recording.

    Returns:
        The profile.
    """
    profile = RecordingProfile(recording_path=recording_path)
    count_records(profile, recording_path)
    previous_received_at_seconds: float | None = None
    events_by_id: dict[int, JsonValue] = {}
    for frame in iter_game_frames(recording_path):
        profile.frame_count += 1
        if previous_received_at_seconds is not None:
            gap_seconds = frame.received_at_seconds - previous_received_at_seconds
            if gap_seconds > ANSWER_GAP_THRESHOLD_SECONDS:
                profile.answer_gaps_seconds.append((previous_received_at_seconds, gap_seconds))
        previous_received_at_seconds = frame.received_at_seconds
        if isinstance(frame.payload, dict):
            profile_frame(profile, frame.payload, events_by_id)
    return profile


def count_records(profile: RecordingProfile, recording_path: Path) -> None:
    """Count a recording's lines by kind, its client resources, and why it ended.

    Args:
        profile: The profile to add to.
        recording_path: The recording.
    """
    for record in iter_recording_lines(recording_path):
        if isinstance(record, RecordingStarted):
            profile.recorder_version = record.recorder_version
            profile.poll_interval_seconds = record.poll_interval_seconds
            continue
        profile.last_received_at_seconds = max(
            profile.last_received_at_seconds, record.received_at_seconds
        )
        if isinstance(record, SnapshotKeyframe):
            profile.keyframe_count += 1
        elif isinstance(record, SnapshotDelta):
            profile.delta_count += 1
        elif isinstance(record, ClientResource):
            resource_kind = classify_client_path(record.path)
            profile.client_resources[resource_kind] += 1
            if isinstance(record.payload, dict) and (
                "errorCode" in record.payload or "httpStatus" in record.payload
            ):
                profile.client_resource_errors[resource_kind] += 1
        elif isinstance(record, RecordingEnded):
            profile.ended_reason = record.reason


def profile_frame(
    profile: RecordingProfile, payload: dict[str, JsonValue], events_by_id: dict[int, JsonValue]
) -> None:
    """Count what one whole answer of the game holds.

    Args:
        profile: The profile to add to.
        payload: One whole answer of `/liveclientdata/allgamedata`.
        events_by_id: Every event seen so far in this recording, by its id; added to.
    """
    _, game_mode = value_at(payload, ("gameData", "gameMode"))
    _, map_number = value_at(payload, ("gameData", "mapNumber"))
    profile.game_modes[str(game_mode)] += 1
    profile.map_numbers[str(map_number)] += 1
    _, game_time = value_at(payload, ("gameData", "gameTime"))
    if isinstance(game_time, int | float):
        if profile.last_game_time_seconds is not None and game_time < (
            profile.last_game_time_seconds
        ):
            profile.game_time_backward_steps.append(
                (profile.last_game_time_seconds, float(game_time))
            )
        if profile.first_game_time_seconds is None:
            profile.first_game_time_seconds = float(game_time)
        profile.last_game_time_seconds = float(game_time)
    active_player = payload.get("activePlayer")
    if isinstance(active_player, dict):
        if "error" in active_player:
            profile.frames_with_active_player_error += 1
        current_gold = active_player.get("currentGold")
        if isinstance(current_gold, int | float) and current_gold < 0:
            profile.negative_gold_frames += 1
    profile_players(profile, payload)
    profile_events(profile, payload, events_by_id)


def percentage(part_count: int, whole_count: int) -> str:
    """Return a share as a percentage, or "n/a" when there is nothing to share.

    Args:
        part_count: The part.
        whole_count: The whole.

    Returns:
        The text.
    """
    return f"{100.0 * part_count / whole_count:.1f}%" if whole_count else "n/a"


def report_lines(profile: RecordingProfile) -> Iterator[str]:
    """Yield the printed report of one recording.

    Args:
        profile: The recording's profile.

    Yields:
        One line at a time.
    """
    yield f"== {profile.recording_path.name}"
    yield (
        f"recorder {profile.recorder_version}, poll {profile.poll_interval_seconds} s;"
        f" ended: {profile.ended_reason}"
    )
    yield (
        f"duration {profile.last_received_at_seconds:.3f} s wall;"
        f" game clock {profile.first_game_time_seconds} -> {profile.last_game_time_seconds} s"
    )
    yield (
        f"frames {profile.frame_count} (keyframes {profile.keyframe_count},"
        f" deltas {profile.delta_count})"
    )
    yield f"game mode {dict(profile.game_modes)}; map {dict(profile.map_numbers)}"
    yield (
        f"gameTime going backwards: {len(profile.game_time_backward_steps)}"
        f" {profile.game_time_backward_steps[:5]}"
    )
    yield (
        f"gaps between answers > {ANSWER_GAP_THRESHOLD_SECONDS} s:"
        f" {len(profile.answer_gaps_seconds)}"
        f" (largest {max((gap for _, gap in profile.answer_gaps_seconds), default=0.0):.1f} s)"
    )
    yield (
        f"frames with no allPlayers: {profile.frames_without_players};"
        f" frames whose activePlayer is an error: {profile.frames_with_active_player_error}"
    )
    yield f"player rows: {profile.player_rows}"
    for field_name, tally in profile.field_tallies.items():
        yield (
            f"  {field_name:<20} missing {percentage(tally.missing_count, profile.player_rows):>6}"
            f"  null {percentage(tally.null_count, profile.player_rows):>6}"
            f"  empty {percentage(tally.empty_count, profile.player_rows):>6}"
        )
    yield (
        f"riotIdGameName: pseudonyms {profile.names_pseudonyms},"
        f" not pseudonyms {profile.names_not_pseudonyms}"
    )
    yield f"events (unique ids): {dict(profile.event_names)}"
    yield (
        f"ChampionKill events {profile.kill_feed_events};"
        f" KillerName/VictimName missing {profile.kill_feed_names_missing}"
    )
    yield (
        f"duplicate event ids within a frame {profile.duplicate_event_ids_in_frame};"
        f" ids whose content changed between frames {len(profile.event_ids_with_changed_content)}"
    )
    yield (
        f"implausible: negative gold {profile.negative_gold_frames},"
        f" level outside 1..{MAXIMUM_CHAMPION_LEVEL} {profile.level_out_of_range},"
        f" creep score decreasing {profile.creep_score_decreases},"
        f" negative respawnTimer {profile.negative_respawn_timers}"
    )
    yield "client resources:"
    for resource_kind, _ in (*CLIENT_RESOURCE_KINDS, ("other", "")):
        resource_count = profile.client_resources.get(resource_kind, 0)
        error_count = profile.client_resource_errors.get(resource_kind, 0)
        error_text = f" ({error_count} error answers)" if error_count else ""
        yield f"  {resource_kind:<18} {resource_count}{error_text}"


def build_recording_from_test_payloads(output_directory: Path) -> Path:
    """Write the recording the scoring tests build, with a kill in its feed, and return its path.

    Args:
        output_directory: An existing directory to write `game.jsonl.xz` into.

    Returns:
        The recording.
    """
    tests_directory = Path(__file__).resolve().parents[2] / "tests"
    sys.path.insert(0, str(tests_directory))
    from game_payloads import champion_kill_event  # type: ignore[import-not-found]  # noqa: PLC0415

    # The tests are not a package, so they are found by path and are untyped here.
    from recorded_games import (  # type: ignore[import-not-found]  # noqa: PLC0415
        game_timeline,
        players_at,
        write_scored_recording,
    )

    recording_path: Path = write_scored_recording(
        output_directory,
        players_at(are_positions_given=True),
        timeline=game_timeline(),
        winning_team_id=100,
        feed_events=[champion_kill_event(1, 300.0, "Shadow Step", "Ahri", [])],
    )
    return recording_path


def main() -> int:
    """Profile every recording in a directory, or one built from the tests' payloads.

    Returns:
        The exit status: 0, or 1 when no recording was found.
    """
    argument_parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argument_parser.add_argument("directory", type=Path)
    argument_parser.add_argument(
        "--build-from-test-payloads",
        action="store_true",
        help="write the tests' built recording into the directory first, and profile it",
    )
    arguments = argument_parser.parse_args()
    if arguments.build_from_test_payloads:
        arguments.directory.mkdir(parents=True, exist_ok=True)
        build_recording_from_test_payloads(arguments.directory)
    recording_paths = sorted(
        path
        for path in arguments.directory.rglob("*")
        if path.name.endswith((".jsonl", ".jsonl.xz"))
    )
    if not recording_paths:
        sys.stdout.write(f"no recordings under {arguments.directory}\n")
        return 1
    sys.stdout.write(f"{len(recording_paths)} recording(s) under {arguments.directory}\n")
    for recording_path in recording_paths:
        for line in report_lines(profile_recording(recording_path)):
            sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
