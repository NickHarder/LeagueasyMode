"""The owner's approval of a concept: of one exact text, recorded so that a later change shows.

`approve` writes three things into a concept's frontmatter: `status: stable`, a `verified` check by
a person, and `approved_sha256`, a hash of what was approved. The format knows the first two; the
hash is this project's own key, which the format allows. With it the check can tell, on any later
day, whether the concept is still the one that was approved:

    approval   the concept changed after it was approved and `generated` does not say who changed
               it or when; or a hash stands with no person's check behind it

The hash covers the body and every field of the frontmatter but four: `status`, `verified` and
`approved_sha256`, which an approval writes, and `generated`, which an edit writes. It covers what
the frontmatter says and not how it is laid out, so a comment or a reordering changes nothing.

A change that does say who made it breaks no rule. It is noted until the owner approves again.
A hash catches a careless edit; it does not stop a forger, because there is no key behind it.

An approval is written into the frontmatter as the author laid it out, and only when the result
reads back as the fields that were there plus the three changes. Otherwise nothing is written.
"""

import codecs
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

from okf.documents import (
    TEXT_ENCODING,
    Document,
    FrontmatterError,
    frontmatter_block,
    frontmatter_fields,
    top_level_nodes,
)
from okf.findings import APPROVAL, Finding, Note
from okf.trust import (
    AT_KEY,
    BY_KEY,
    GENERATED_KEY,
    STATUS_KEY,
    VERIFIED_KEY,
    VerificationEvent,
    generated_time,
    time_of,
    verification_events,
    written_checks,
)

APPROVED_HASH_KEY: Final = "approved_sha256"
FIELDS_AN_APPROVAL_DOES_NOT_COVER: Final = frozenset(
    {STATUS_KEY, VERIFIED_KEY, APPROVED_HASH_KEY, GENERATED_KEY}
)
SHA256_PATTERN: Final = re.compile(r"[0-9a-f]{64}")
STABLE: Final = "stable"
DRAFT: Final = "draft"
DEPRECATED: Final = "deprecated"
CHECK_INDENT: Final = "  "
LINE_ENDINGS: Final = "\r\n"
WINDOWS_LINE_ENDING: Final = "\r\n"
COMMENT_START: Final = "#"
BYTE_ORDER_MARK: Final = codecs.BOM_UTF8

NOT_APPROVED: Final = "not approved"
CURRENT: Final = "current"
CHANGED_AND_SAID: Final = "changed, and said by whom"
CHANGED_UNSAID: Final = "changed, by nobody named"
UNBACKED: Final = "unbacked"


class ApprovalError(Exception):
    """An approval cannot be recorded: the message says why, and nothing was written."""


@dataclass(frozen=True)
class Approval:
    """Where a concept stands with the owner: the state, and the approval it refers to, if any."""

    state: str
    last_approval: VerificationEvent | None


def comparable(value: object) -> object:
    """Return a frontmatter value in a form that is written the same way on every run.

    The keys of a mapping become text, a set is put in order, and anything that is not plain data
    becomes its text.
    """
    if isinstance(value, dict):
        return {str(key): comparable(inner_value) for key, inner_value in value.items()}
    if isinstance(value, list | tuple):
        return [comparable(inner_value) for inner_value in value]
    if isinstance(value, set | frozenset):
        return sorted(written_form(inner_value) for inner_value in value)
    if value is None or isinstance(value, str | int | float):
        return value
    return str(value)


def written_form(value: object) -> str:
    """Return a frontmatter value as one text that depends on what it says and on nothing else."""
    return json.dumps(comparable(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def approved_sha256(document: Document) -> str:
    """Return the hash of what an approval covers: the body, and the fields it does not write."""
    covered_fields = {
        key: value
        for key, value in document.fields.items()
        if key not in FIELDS_AN_APPROVAL_DOES_NOT_COVER
    }
    covered_text = written_form({"body": document.body, "frontmatter": covered_fields})
    return hashlib.sha256(covered_text.encode("utf-8")).hexdigest()


def approval_of(document: Document) -> Approval:
    """Return where a concept stands: never approved, approved as it is, or changed since."""
    if APPROVED_HASH_KEY not in document.fields:
        return Approval(state=NOT_APPROVED, last_approval=None)
    approved_hash = document.fields[APPROVED_HASH_KEY]
    approvals = [event for event in verification_events(document) if event.is_by_a_person]
    if (
        not approvals
        or not isinstance(approved_hash, str)
        or not SHA256_PATTERN.fullmatch(approved_hash)
    ):
        return Approval(state=UNBACKED, last_approval=None)
    last_approval = approvals[-1]
    if approved_hash == approved_sha256(document):
        return Approval(state=CURRENT, last_approval=last_approval)
    changed_time = generated_time(document)
    said = changed_time is not None and changed_time > last_approval.time
    return Approval(state=CHANGED_AND_SAID if said else CHANGED_UNSAID, last_approval=last_approval)


def approval_findings(document: Document) -> list[Finding]:
    """Return a finding when an approval no longer covers the concept and nothing says why."""
    if document.frontmatter_problem is not None:
        return []
    approval = approval_of(document)
    line_number = document.line_number_of(APPROVED_HASH_KEY)
    if approval.state == UNBACKED:
        message = (
            f"`{APPROVED_HASH_KEY}` stands with no person's check behind it; only"
            " `make docs-approve` writes an approval, and only on the owner's word"
        )
        return [Finding(document.path, line_number, APPROVAL, message)]
    if approval.state == CHANGED_UNSAID and approval.last_approval is not None:
        message = (
            f"the concept changed after the approval of {approval.last_approval.time_text}, and"
            " `generated` does not say who changed it or when; update `generated`, then ask the"
            " owner to approve it again"
        )
        return [Finding(document.path, line_number, APPROVAL, message)]
    return []


def approval_notes(document: Document) -> list[Note]:
    """Return a note when an approval stands and does not cover the concept as it now is."""
    approval = approval_of(document)
    if approval.last_approval is None:
        return []
    line_number = document.line_number_of(APPROVED_HASH_KEY)
    if approval.state == CHANGED_AND_SAID:
        message = (
            f"changed since the approval of {approval.last_approval.time_text}; it waits for the"
            " owner to approve it again"
        )
        return [Note(document.path, line_number, message)]
    return []


def approval_summary(document: Document) -> str:
    """Return where a concept stands with the owner, in a few words, for the status table."""
    approval = approval_of(document)
    if approval.last_approval is None:
        return (
            NOT_APPROVED if approval.state == NOT_APPROVED else "an approval nobody stands behind"
        )
    approved_at = approval.last_approval.time_text
    if approval.state == CURRENT:
        return f"approved {approved_at}"
    if approval.state == CHANGED_AND_SAID:
        return f"changed since the approval of {approved_at}"
    return f"changed since the approval of {approved_at}, by nobody named"


def file_lines_of(document_file: Path) -> list[str]:
    """Return a file's lines, each with the line ending it has on disk.

    A byte-order mark in front of the first line is left off: `write_frontmatter` puts it back.
    """
    with document_file.open(encoding=TEXT_ENCODING, newline="") as opened_file:
        return opened_file.read().splitlines(keepends=True)


def has_a_byte_order_mark(document_file: Path) -> bool:
    """Return whether a file starts with the byte-order mark of UTF-8."""
    with document_file.open("rb") as opened_file:
        return opened_file.read(len(BYTE_ORDER_MARK)) == BYTE_ORDER_MARK


def line_ending_of(frontmatter_lines: list[str]) -> str:
    """Return the line ending a new line of the frontmatter gets: the one its first line has."""
    is_windows = bool(frontmatter_lines) and frontmatter_lines[0].endswith(WINDOWS_LINE_ENDING)
    return WINDOWS_LINE_ENDING if is_windows else "\n"


def nodes_by_key(frontmatter_lines: list[str]) -> dict[str, tuple[yaml.Node, yaml.Node]]:
    """Return where each top-level key and its value are written; the last one, if one repeats."""
    block_lines = [line.rstrip(LINE_ENDINGS) for line in frontmatter_lines]
    return {
        key: (key_node, value_node) for key, key_node, value_node in top_level_nodes(block_lines)
    }


def end_of_value(frontmatter_lines: list[str], key_line_index: int) -> int:
    """Return the index of the line after the last line that a key's value is written on.

    A key's lines run to the next top-level key. The blank lines and the comments at the end of
    them come before that key and are not part of the value.
    """
    later_key_line_indexes = [
        key_node.start_mark.line
        for key_node, _value_node in nodes_by_key(frontmatter_lines).values()
        if key_node.start_mark.line > key_line_index
    ]
    next_key_line_index = min(later_key_line_indexes, default=len(frontmatter_lines))
    value_line_indexes = [
        line_index
        for line_index in range(key_line_index, next_key_line_index)
        if frontmatter_lines[line_index].strip()
        and not frontmatter_lines[line_index].lstrip().startswith(COMMENT_START)
    ]
    return value_line_indexes[-1] + 1


def with_value(frontmatter_lines: list[str], key: str, value_text: str) -> list[str]:
    """Return the frontmatter with a key set to a short text, and every comment where it was.

    A key that is not there yet is added at the end.

    Raises:
        ApprovalError: If the key's value is not a text on the key's own line.
    """
    written = nodes_by_key(frontmatter_lines).get(key)
    if written is None:
        return [*frontmatter_lines, f"{key}: {value_text}{line_ending_of(frontmatter_lines)}"]
    key_node, value_node = written
    value_start = value_node.start_mark
    value_end = value_node.end_mark
    is_on_the_key_line = key_node.start_mark.line == value_start.line == value_end.line
    if not isinstance(value_node, yaml.ScalarNode) or not is_on_the_key_line:
        message = (
            f"`{key}` is written in a way that cannot be changed safely; write it on one line, as"
            f" `{key}: <value>`"
        )
        raise ApprovalError(message)
    key_line = frontmatter_lines[value_start.line]
    # A key with nothing after its colon has a value of no length, which starts at the colon.
    space_after_the_colon = " " if value_start.column == value_end.column else ""
    new_key_line = (
        f"{key_line[: value_start.column]}{space_after_the_colon}{value_text}"
        f"{key_line[value_end.column :]}"
    )
    return [
        *frontmatter_lines[: value_start.line],
        new_key_line,
        *frontmatter_lines[value_start.line + 1 :],
    ]


def without_key(frontmatter_lines: list[str], key: str) -> list[str]:
    """Return the frontmatter with a key and its value taken out."""
    written = nodes_by_key(frontmatter_lines).get(key)
    if written is None:
        return frontmatter_lines
    key_line_index = written[0].start_mark.line
    return [
        *frontmatter_lines[:key_line_index],
        *frontmatter_lines[end_of_value(frontmatter_lines, key_line_index) :],
    ]


def with_check_added(frontmatter_lines: list[str], actor: str, time_text: str) -> list[str]:
    """Return the frontmatter with one more check at the end of `verified`, the others as written.

    The new check takes the indent of the checks already there.

    Raises:
        ApprovalError: If `verified` is written in a way a line cannot be added to.
    """
    line_ending = line_ending_of(frontmatter_lines)
    new_check = f"- {{ {BY_KEY}: {actor}, {AT_KEY}: {time_text} }}{line_ending}"
    written = nodes_by_key(frontmatter_lines).get(VERIFIED_KEY)
    if written is None:
        return [*frontmatter_lines, f"{VERIFIED_KEY}:{line_ending}", f"{CHECK_INDENT}{new_check}"]
    key_node, value_node = written
    key_line_index = key_node.start_mark.line
    is_a_list_down_the_page = isinstance(value_node, yaml.SequenceNode) and (
        not value_node.flow_style and bool(value_node.value)
    )
    if is_a_list_down_the_page:
        indent_of_the_checks = " " * value_node.start_mark.column
        insert_index = end_of_value(frontmatter_lines, key_line_index)
        return [
            *frontmatter_lines[:insert_index],
            f"{indent_of_the_checks}{new_check}",
            *frontmatter_lines[insert_index:],
        ]
    is_one_check_on_the_key_line = isinstance(value_node, yaml.MappingNode) and (
        bool(value_node.flow_style)
        and key_line_index == value_node.start_mark.line == value_node.end_mark.line
    )
    if is_one_check_on_the_key_line:
        key_line = frontmatter_lines[key_line_index]
        check_column = value_node.start_mark.column
        return [
            *frontmatter_lines[:key_line_index],
            f"{key_line[:check_column].rstrip()}{line_ending}",
            f"{CHECK_INDENT}- {key_line[check_column:]}",
            f"{CHECK_INDENT}{new_check}",
            *frontmatter_lines[key_line_index + 1 :],
        ]
    message = (
        f"`{VERIFIED_KEY}` is written in a way a check cannot be added to; write it as a list,"
        " one `- { by: <actor>, at: <time> }` a line, then approve again"
    )
    raise ApprovalError(message)


def write_frontmatter(
    document: Document,
    file_lines: list[str],
    new_frontmatter_lines: list[str],
    expected_fields: dict[str, object],
) -> None:
    """Write a concept's file with new frontmatter and every other line as it was.

    The new frontmatter is read first, as any reader would read it. It is written only when it
    says exactly what it is meant to say.

    Raises:
        ApprovalError: If the new frontmatter does not read back as the fields expected.
    """
    try:
        read_back_fields: dict[str, object] | None = frontmatter_fields(
            [line.rstrip(LINE_ENDINGS) for line in new_frontmatter_lines]
        )
    except FrontmatterError:
        read_back_fields = None
    if read_back_fields is None or written_form(read_back_fields) != written_form(expected_fields):
        message = (
            f"the frontmatter of {document.path} is written in a way that cannot be changed"
            " safely: with the change made, it no longer reads as the fields it had. Nothing was"
            " written. Write each key on a line of its own and try again"
        )
        raise ApprovalError(message)
    closing_line_index = frontmatter_block(file_lines).closing_line_index
    new_text = "".join([file_lines[0], *new_frontmatter_lines, *file_lines[closing_line_index:]])
    written_encoding = TEXT_ENCODING if has_a_byte_order_mark(document.path) else "utf-8"
    with document.path.open("w", encoding=written_encoding, newline="") as opened_file:
        opened_file.write(new_text)


def frontmatter_lines_in(file_lines: list[str]) -> list[str]:
    """Return the lines of a file's frontmatter, each with its line ending.

    Raises:
        ApprovalError: If a key is written twice. One reader takes the first and another the last,
            so no change to either is safe.
    """
    frontmatter_lines = file_lines[1 : frontmatter_block(file_lines).closing_line_index]
    block_lines = [line.rstrip(LINE_ENDINGS) for line in frontmatter_lines]
    written_keys = [key for key, _key_node, _value_node in top_level_nodes(block_lines)]
    repeated_keys = sorted({key for key in written_keys if written_keys.count(key) > 1})
    if repeated_keys:
        message = (
            f"`{repeated_keys[0]}` is written twice in the frontmatter, and a reader may take"
            " either. Nothing was written. Keep one of the two and try again"
        )
        raise ApprovalError(message)
    return frontmatter_lines


def refuse_an_approval_older_than_the_text(document: Document, time_text: str) -> None:
    """Refuse an approval that is dated before the text it would cover says it was written.

    A later change is told from the approved text by `generated.at` being later than the approval.
    An approval older than its own text would make every later change look like one that says who
    made it.

    Raises:
        ApprovalError: If `generated.at` is later than the time of the approval.
    """
    approval_time = time_of(time_text)
    written_time = generated_time(document)
    generated = document.fields.get(GENERATED_KEY)
    if approval_time is None or written_time is None or not isinstance(generated, dict):
        return
    if written_time > approval_time:
        message = (
            f"`generated` says the text of {document.path} was written at {generated[AT_KEY]},"
            f" which is after this approval, at {time_text}. An approval covers a text that is"
            " already written: correct whichever time is wrong"
        )
        raise ApprovalError(message)


def approve(document: Document, actor: str, time_text: str) -> str:
    """Record the owner's approval of a concept as it now is, in its frontmatter.

    A draft becomes stable. A deprecated concept stays deprecated: status and approval are two
    things, and the owner can stand behind a text that is no longer in use.

    Returns:
        The concept's status after the approval.

    Raises:
        ApprovalError: If the approval is dated before the text, or the frontmatter is written in
            a way the approval cannot be added to safely. Nothing is written then.
    """
    refuse_an_approval_older_than_the_text(document, time_text)
    approved_status = DEPRECATED if document.fields.get(STATUS_KEY) == DEPRECATED else STABLE
    file_lines = file_lines_of(document.path)
    with_status = with_value(frontmatter_lines_in(file_lines), STATUS_KEY, approved_status)
    with_check = with_check_added(with_status, actor, time_text)
    approved_hash = approved_sha256(document)
    with_hash = with_value(with_check, APPROVED_HASH_KEY, approved_hash)
    expected_fields = {
        **document.fields,
        STATUS_KEY: approved_status,
        VERIFIED_KEY: [*(written_checks(document) or []), {BY_KEY: actor, AT_KEY: time_text}],
        APPROVED_HASH_KEY: approved_hash,
    }
    write_frontmatter(document, file_lines, with_hash, expected_fields)
    return approved_status


def reopen(document: Document) -> None:
    """Put a concept back to draft and drop its approval hash; the record of past checks stays.

    Raises:
        ApprovalError: If the frontmatter is written in a way that cannot be changed safely.
    """
    file_lines = file_lines_of(document.path)
    with_status = with_value(frontmatter_lines_in(file_lines), STATUS_KEY, DRAFT)
    without_hash = without_key(with_status, APPROVED_HASH_KEY)
    expected_fields = {
        **{key: value for key, value in document.fields.items() if key != APPROVED_HASH_KEY},
        STATUS_KEY: DRAFT,
    }
    write_frontmatter(document, file_lines, without_hash, expected_fields)
