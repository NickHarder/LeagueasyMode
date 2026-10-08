"""Make a copy of a recording in which no player, account or match can be identified.

Only an anonymized copy goes into the repository. Every Riot ID, summoner name, PUUID, account or
summoner number and game id is replaced with a pseudonym, the same one wherever it appears: the
player listed first in the game is `Player 1` everywhere, whether in the scoreboard, the kill feed
or the League client's answers. Game content (champion, item, rune and spell names and their
texts) is never touched, so a player who chose a champion's name as their own does not rename the
champion.

The copy fails closed: after replacing, every string is searched again for every identity, and one
found anywhere stops the copy before anything is written. A field this module does not know yet
then has to be added here, rather than slipping through.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from pydantic import JsonValue

from leagueasymode.recording.delta import apply_patch
from leagueasymode.recording.file_format import (
    PLAIN_SUFFIX,
    ClientResource,
    RecordingEnded,
    RecordingStarted,
    SnapshotDelta,
    SnapshotKeyframe,
)
from leagueasymode.recording.reader import iter_recording_lines
from leagueasymode.recording.writer import RecordingWriter

# Fields that hold a player's name, alone or as a Riot ID (`name#tag`).
NAME_FIELDS: Final = frozenset(
    {"summonerName", "riotId", "riotIdGameName", "gameName", "summonerInternalName"}
)
TAG_LINE_FIELDS: Final = frozenset({"riotIdTagLine", "tagLine"})
PUUID_FIELDS: Final = frozenset({"puuid"})
NUMBER_ID_FIELDS: Final = frozenset(
    {"summonerId", "accountId", "currentAccountId", "gameId", "matchId"}
)
# Text that Riot writes about the game itself. It is neither changed nor searched: a champion
# called like a player is still that champion.
GAME_CONTENT_FIELDS: Final = frozenset(
    {
        "championName",
        "rawChampionName",
        "displayName",
        "rawDisplayName",
        "description",
        "rawDescription",
        "name",
        "id",
        "DragonType",
        "TurretKilled",
        "InhibKilled",
    }
)
TAG_LINE_PSEUDONYM: Final = "ANON"
# Shorter names are replaced where they stand alone, but not searched for inside other text, where
# two or three letters would match by chance.
SHORTEST_SEARCHED_NAME_LENGTH: Final = 4
# A number this long is an account, summoner or game id wherever it appears, in a path included.
SHORTEST_SEARCHED_NUMBER_DIGITS: Final = 6
ALL_PLAYERS_KEY: Final = "allPlayers"


class IdentityLeakError(Exception):
    """An identity is still in a recording after anonymizing it, so no copy was written."""


@dataclass
class IdentityMap:
    """Each identity found in a recording, and the pseudonym that replaces it."""

    name_pseudonyms: dict[str, str] = field(default_factory=dict)
    tag_lines: set[str] = field(default_factory=set)
    puuid_pseudonyms: dict[str, str] = field(default_factory=dict)
    number_pseudonyms: dict[int, int] = field(default_factory=dict)

    def add_player_name(self, name_or_riot_id: str) -> None:
        """Give a player's name a pseudonym, the next free one, unless it has one.

        Args:
            name_or_riot_id: A name, or a Riot ID whose tag line is noted as well.
        """
        game_name, separator, tag_line = name_or_riot_id.partition("#")
        if not game_name:
            return
        if game_name not in self.name_pseudonyms:
            self.name_pseudonyms[game_name] = f"Player {len(self.name_pseudonyms) + 1}"
        if separator and tag_line:
            self.tag_lines.add(tag_line)

    def add_puuid(self, puuid: str) -> None:
        """Give a PUUID a pseudonym, unless it has one.

        Args:
            puuid: The PUUID.
        """
        if puuid and puuid not in self.puuid_pseudonyms:
            self.puuid_pseudonyms[puuid] = f"anonymous-puuid-{len(self.puuid_pseudonyms) + 1}"

    def add_number(self, number_id: int) -> None:
        """Give an account, summoner or game number a pseudonym, unless it has one.

        Args:
            number_id: The number.
        """
        if number_id not in self.number_pseudonyms:
            self.number_pseudonyms[number_id] = len(self.number_pseudonyms) + 1

    def replace_text(self, text: str) -> str:
        """Return a string with every identity in it replaced.

        A string that is a whole name, Riot ID, tag line or PUUID is replaced whole. Inside longer
        text, PUUIDs and long numbers are replaced; names are not, so that the leak search catches
        them instead of a guess at where one starts.

        Args:
            text: The string.

        Returns:
            The string with its identities replaced.
        """
        game_name, separator, tag_line = text.partition("#")
        if separator and game_name in self.name_pseudonyms and tag_line in self.tag_lines:
            return f"{self.name_pseudonyms[game_name]}#{TAG_LINE_PSEUDONYM}"
        if text in self.name_pseudonyms:
            return self.name_pseudonyms[text]
        if text in self.tag_lines:
            return TAG_LINE_PSEUDONYM
        replaced_text = text
        for puuid, pseudonym in self.puuid_pseudonyms.items():
            replaced_text = replaced_text.replace(puuid, pseudonym)
        for number_id, pseudonym_number in self._searched_numbers():
            replaced_text = re.sub(
                rf"(?<!\d){number_id}(?!\d)", str(pseudonym_number), replaced_text
            )
        return replaced_text

    def leaks_in(self, text: str) -> list[str]:
        """Return the identities that a string still holds.

        Args:
            text: The string, already replaced.

        Returns:
            The identities found in it, empty when none is.
        """
        searched_names = [
            name for name in self.name_pseudonyms if len(name) >= SHORTEST_SEARCHED_NAME_LENGTH
        ]
        found_names = [name for name in searched_names if name in text]
        found_puuids = [puuid for puuid in self.puuid_pseudonyms if puuid in text]
        found_numbers = [
            str(number_id)
            for number_id, _ in self._searched_numbers()
            if re.search(rf"(?<!\d){number_id}(?!\d)", text)
        ]
        return [*found_names, *found_puuids, *found_numbers]

    def _searched_numbers(self) -> Iterator[tuple[int, int]]:
        """Yield the numbers long enough to be searched for inside text, with their pseudonyms.

        Yields:
            Each long number and its pseudonym.
        """
        for number_id, pseudonym_number in self.number_pseudonyms.items():
            if len(str(number_id)) >= SHORTEST_SEARCHED_NUMBER_DIGITS:
                yield number_id, pseudonym_number


def anonymize_recording(source_path: Path, destination_plain_path: Path) -> Path:
    """Write an anonymized copy of a recording, compressed, and return its path.

    Args:
        source_path: The recording to copy.
        destination_plain_path: Where the copy is written while it is open; it ends in `.jsonl`
            and is compressed to `.jsonl.xz` when complete.

    Returns:
        The compressed copy's path.

    Raises:
        IdentityLeakError: An identity would still be in the copy; nothing is left behind.
        ValueError: The destination does not end in `.jsonl`.
    """
    if not destination_plain_path.name.endswith(PLAIN_SUFFIX):
        raise ValueError(f"the copy is written to a {PLAIN_SUFFIX} file: {destination_plain_path}")
    identity_map = collect_identities(source_path)
    writer = RecordingWriter(destination_plain_path)
    try:
        _write_anonymized_lines(source_path, writer, identity_map)
    except IdentityLeakError:
        writer.abandon()
        destination_plain_path.unlink()
        raise
    return writer.close()


def collect_identities(source_path: Path) -> IdentityMap:
    """Find every identity in a recording and give each its pseudonym.

    The players of the scoreboard are numbered first, in its order, so that `Player 1` is the first
    player listed in the game whatever else names them.

    Args:
        source_path: The recording.

    Returns:
        The identities and their pseudonyms.
    """
    identity_map = IdentityMap()
    for payload in _iter_payloads(source_path):
        all_players = payload.get(ALL_PLAYERS_KEY) if isinstance(payload, dict) else None
        if isinstance(all_players, list):
            _collect_from_value(all_players, None, identity_map)
            break
    for payload in _iter_payloads(source_path):
        _collect_from_value(payload, None, identity_map)
    return identity_map


def anonymize_value(
    value: JsonValue, field_name: str | None, identity_map: IdentityMap
) -> JsonValue:
    """Return a copy of a JSON value with every identity replaced.

    Args:
        value: The value.
        field_name: The key the value sits under, or None at the top.
        identity_map: The identities and their pseudonyms.

    Returns:
        The anonymized copy.
    """
    if isinstance(value, dict):
        return {
            identity_map.replace_text(key): anonymize_value(item, key, identity_map)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [anonymize_value(item, field_name, identity_map) for item in value]
    if isinstance(value, str) and field_name not in GAME_CONTENT_FIELDS:
        return identity_map.replace_text(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return identity_map.number_pseudonyms.get(value, value)
    return value


def find_identity_leaks(value: JsonValue, path: str, identity_map: IdentityMap) -> list[str]:
    """Return where in a JSON value an identity is still found, as JSON Pointers with the identity.

    Args:
        value: The value, already anonymized.
        path: The value's own pointer.
        identity_map: The identities.

    Returns:
        One entry per leak, `<pointer>: <identity>`; empty when there is none.
    """
    if isinstance(value, dict):
        return [
            leak
            for key, item in value.items()
            for leak in (
                [f"{path}/{key} (as a key): {found}" for found in identity_map.leaks_in(key)]
                + (
                    []
                    if key in GAME_CONTENT_FIELDS
                    else find_identity_leaks(item, f"{path}/{key}", identity_map)
                )
            )
        ]
    if isinstance(value, list):
        return [
            leak
            for index, item in enumerate(value)
            for leak in find_identity_leaks(item, f"{path}/{index}", identity_map)
        ]
    if isinstance(value, str):
        return [f"{path}: {found}" for found in identity_map.leaks_in(value)]
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value in identity_map.number_pseudonyms
    ):
        return [f"{path}: {value}"]
    return []


def _collect_from_value(
    value: JsonValue, field_name: str | None, identity_map: IdentityMap
) -> None:
    """Note the identities held by a JSON value and everything inside it.

    Args:
        value: The value.
        field_name: The key it sits under, or None at the top.
        identity_map: Where the identities are noted.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            _collect_from_value(item, key, identity_map)
        return
    if isinstance(value, list):
        for item in value:
            _collect_from_value(item, field_name, identity_map)
        return
    if field_name in NAME_FIELDS and isinstance(value, str):
        identity_map.add_player_name(value)
    elif field_name in TAG_LINE_FIELDS and isinstance(value, str) and value:
        identity_map.tag_lines.add(value)
    elif field_name in PUUID_FIELDS and isinstance(value, str):
        identity_map.add_puuid(value)
    elif field_name in NUMBER_ID_FIELDS and isinstance(value, int) and not isinstance(value, bool):
        identity_map.add_number(value)
    elif field_name in NUMBER_ID_FIELDS and isinstance(value, str) and value.isdigit():
        identity_map.add_number(int(value))


def _iter_payloads(source_path: Path) -> Iterator[JsonValue]:
    """Yield every payload of a recording, game snapshots whole, in file order.

    Args:
        source_path: The recording.

    Yields:
        Each game snapshot and each client answer, and each client answer's path as text.
    """
    current_payload: JsonValue = None
    for record in iter_recording_lines(source_path):
        if isinstance(record, SnapshotKeyframe):
            current_payload = record.payload
            yield current_payload
        elif isinstance(record, SnapshotDelta):
            current_payload = apply_patch(current_payload, record.operations)
            yield current_payload
        elif isinstance(record, ClientResource):
            yield record.payload


def _write_anonymized_lines(
    source_path: Path, writer: RecordingWriter, identity_map: IdentityMap
) -> None:
    """Write each line of the source to the writer, anonymized, checking each for leaks first.

    Args:
        source_path: The recording to copy.
        writer: The copy's writer.
        identity_map: The identities and their pseudonyms.

    Raises:
        IdentityLeakError: A line would still hold an identity.
    """
    current_payload: JsonValue = None
    for record in iter_recording_lines(source_path):
        if isinstance(record, RecordingStarted):
            writer.write_started(
                started_at=record.started_at,
                recorder_version=record.recorder_version,
                poll_interval_seconds=record.poll_interval_seconds,
            )
        elif isinstance(record, SnapshotKeyframe | SnapshotDelta):
            current_payload = (
                record.payload
                if isinstance(record, SnapshotKeyframe)
                else apply_patch(current_payload, record.operations)
            )
            writer.write_snapshot(
                received_at_seconds=record.received_at_seconds,
                payload=_anonymized_and_checked(current_payload, "snapshot", identity_map),
            )
        elif isinstance(record, ClientResource):
            anonymized_path = identity_map.replace_text(record.path)
            _raise_on_leaks(identity_map.leaks_in(anonymized_path), "client resource path")
            writer.write_client_resource(
                received_at_seconds=record.received_at_seconds,
                path=anonymized_path,
                payload=_anonymized_and_checked(record.payload, anonymized_path, identity_map),
            )
        elif isinstance(record, RecordingEnded):
            writer.write_ended(received_at_seconds=record.received_at_seconds, reason=record.reason)


def _anonymized_and_checked(payload: JsonValue, where: str, identity_map: IdentityMap) -> JsonValue:
    """Return a payload anonymized, after checking that no identity is left in it.

    Args:
        payload: The payload.
        where: What the payload is, for the error message.
        identity_map: The identities and their pseudonyms.

    Returns:
        The anonymized payload.
    """
    anonymized_payload = anonymize_value(payload, None, identity_map)
    _raise_on_leaks(find_identity_leaks(anonymized_payload, "", identity_map), where)
    return anonymized_payload


def _raise_on_leaks(leaks: list[str], where: str) -> None:
    """Stop the copy when there is any leak.

    Args:
        leaks: What was found, one entry each.
        where: What was searched, for the error message.

    Raises:
        IdentityLeakError: There is at least one leak.
    """
    if leaks:
        raise IdentityLeakError(
            f"an identity would stay in the copy ({where}): {'; '.join(leaks[:5])}"
        )
