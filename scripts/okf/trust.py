"""The fields that say how far a concept can be trusted (OKF 0.2, sections 5 and 7).

When most of a bundle is written by agents, a reader needs to know who wrote a concept, who has
checked it, where it is in its life, and what it was drawn from. The format leaves all of these
optional; this project requires the first and the third of every concept:

    generated   no `generated`, a writer that follows no naming convention, or no time, or a time
                with no offset
    status      no `status`, one that is not `draft`, `stable` or `deprecated`, or a `stale_after`
                that is not a time
    verified    a check that does not name who made it and when
    sources     a source with no `resource`, two with one `id`, a source in the bundle that is not
                there, or a footnote that names no source

An actor is `<producer>/<version>` for an agent or a tool, `human:<id>` for a person, and
`process:<id>` for a job that runs on its own. A time is ISO 8601 with an offset, such as
`2026-10-04T12:00:00Z`: a date alone names a different instant in every time zone.
"""

import datetime
import re
from dataclasses import dataclass
from typing import Final

from okf.documents import Bundle, Document
from okf.findings import GENERATED, SOURCES, STATUS, VERIFIED, Finding, Note
from okf.markdown import prose_lines
from okf.policy import linked_path

GENERATED_KEY: Final = "generated"
VERIFIED_KEY: Final = "verified"
STATUS_KEY: Final = "status"
STALE_AFTER_KEY: Final = "stale_after"
SOURCES_KEY: Final = "sources"
BY_KEY: Final = "by"
AT_KEY: Final = "at"
RESOURCE_KEY: Final = "resource"
ID_KEY: Final = "id"

ACTOR_PATTERN: Final = re.compile(r"(?:human|process):[^\s:]+|[^\s/:]+/\S+")
HUMAN_PREFIX: Final = "human:"
# What the kit renders into a new project was written when the kit was, not when it was rendered.
KIT_PRODUCER_PREFIX: Final = "ai-kit/"
STATUSES: Final = ("draft", "stable", "deprecated")
TIME_SEPARATOR: Final = "T"
BUNDLE_ROOT_PREFIX: Final = "/"
FOOTNOTE_PATTERN: Final = re.compile(r"\[\^(?P<label>[^\]\s]+)\]")

UNVERIFIED: Final = "unverified"
MACHINE_CONFIRMED: Final = "machine-confirmed"
HUMAN_REVIEWED: Final = "human-reviewed"

ACTOR_FORMS: Final = (
    "`<producer>/<version>` for an agent or a tool, `human:<id>` for a person, `process:<id>` for"
    " a job"
)
TIME_FORM: Final = "a time with an offset, such as `2026-10-04T12:00:00Z`"


@dataclass(frozen=True)
class VerificationEvent:
    """One check of a concept: who made it, and when, as written and as an instant."""

    actor: str
    time_text: str
    time: datetime.datetime

    @property
    def is_by_a_person(self) -> bool:
        """Return whether a person, and not a tool or a job, made this check."""
        return self.actor.startswith(HUMAN_PREFIX)


def is_actor(value: object) -> bool:
    """Return whether a value names an actor in one of the three forms."""
    return isinstance(value, str) and ACTOR_PATTERN.fullmatch(value) is not None


def time_of(value: object) -> datetime.datetime | None:
    """Return the instant a value states, or None when it is not a time with an offset."""
    if not isinstance(value, str) or TIME_SEPARATOR not in value:
        return None
    try:
        parsed_time = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed_time if parsed_time.tzinfo is not None else None


def generated_time(document: Document) -> datetime.datetime | None:
    """Return when a concept's text was last changed, when its frontmatter says so."""
    generated = document.fields.get(GENERATED_KEY)
    return time_of(generated.get(AT_KEY)) if isinstance(generated, dict) else None


def generated_findings(document: Document) -> list[Finding]:
    """Return what is wrong with how a concept says who wrote it, and when."""
    if GENERATED_KEY not in document.fields:
        message = (
            "the frontmatter has no `generated`: who wrote this text and when, as"
            " `generated: { by: <actor>, at: <time> }`"
        )
        return [Finding(document.path, 1, GENERATED, message)]
    line_number = document.line_number_of(GENERATED_KEY)
    generated = document.fields[GENERATED_KEY]
    if not isinstance(generated, dict):
        message = "`generated` must be two fields: `by`, who wrote this text, and `at`, when"
        return [Finding(document.path, line_number, GENERATED, message)]
    writer = generated.get(BY_KEY)
    time_is_given = AT_KEY in generated
    problems = [
        *([f"`generated.by` must name the writer: {ACTOR_FORMS}"] if not is_actor(writer) else []),
        *(
            [f"`generated.at` must be {TIME_FORM}"]
            if time_is_given and time_of(generated[AT_KEY]) is None
            else []
        ),
        *(
            [f"`generated.at` is missing: when this text was last changed, as {TIME_FORM}"]
            if not time_is_given
            and is_actor(writer)
            and not str(writer).startswith(KIT_PRODUCER_PREFIX)
            else []
        ),
    ]
    return [Finding(document.path, line_number, GENERATED, problem) for problem in problems]


def status_findings(document: Document) -> list[Finding]:
    """Return what is wrong with where a concept says it is in its life."""
    allowed = ", ".join(f"`{status}`" for status in STATUSES)
    missing = (
        [Finding(document.path, 1, STATUS, f"the frontmatter has no `status`: one of {allowed}")]
        if STATUS_KEY not in document.fields
        else []
    )
    unknown = (
        [
            Finding(
                document.path,
                document.line_number_of(STATUS_KEY),
                STATUS,
                f"`status` must be one of {allowed}",
            )
        ]
        if STATUS_KEY in document.fields and document.fields[STATUS_KEY] not in STATUSES
        else []
    )
    not_a_time = (
        [
            Finding(
                document.path,
                document.line_number_of(STALE_AFTER_KEY),
                STATUS,
                f"`stale_after` must be {TIME_FORM}",
            )
        ]
        if STALE_AFTER_KEY in document.fields and time_of(document.fields[STALE_AFTER_KEY]) is None
        else []
    )
    return [*missing, *unknown, *not_a_time]


def written_checks(document: Document) -> list[object] | None:
    """Return the entries of `verified` as a list, or None when it is neither one check nor a list.

    A single check may be written as one mapping, without the list dash; a reader must take it as
    a list of one.
    """
    verified = document.fields.get(VERIFIED_KEY)
    if isinstance(verified, dict):
        return [verified]
    if isinstance(verified, list):
        return list(verified)
    return None


def is_a_check(entry: object) -> bool:
    """Return whether an entry of `verified` names who made the check and when."""
    return (
        isinstance(entry, dict)
        and is_actor(entry.get(BY_KEY))
        and time_of(entry.get(AT_KEY)) is not None
    )


def verified_findings(document: Document) -> list[Finding]:
    """Return what is wrong with how a concept records who has checked it."""
    if VERIFIED_KEY not in document.fields:
        return []
    line_number = document.line_number_of(VERIFIED_KEY)
    entries = written_checks(document)
    check_form = f"`{{ by: <actor>, at: <time> }}`: {ACTOR_FORMS}; {TIME_FORM}"
    if entries is None:
        message = f"`verified` must be one check or a list of checks, each {check_form}"
        return [Finding(document.path, line_number, VERIFIED, message)]
    return [
        Finding(
            document.path,
            line_number,
            VERIFIED,
            f"check {entry_index + 1} of `verified` must be {check_form}",
        )
        for entry_index, entry in enumerate(entries)
        if not is_a_check(entry)
    ]


def verification_events(document: Document) -> list[VerificationEvent]:
    """Return the well-formed checks of a concept, oldest first."""
    events = [
        VerificationEvent(actor=str(entry[BY_KEY]), time_text=str(entry[AT_KEY]), time=checked_time)
        for entry in written_checks(document) or []
        if isinstance(entry, dict) and is_actor(entry.get(BY_KEY))
        for checked_time in [time_of(entry.get(AT_KEY))]
        if checked_time is not None
    ]
    return sorted(events, key=lambda event: event.time)


def trust_tier(document: Document) -> str:
    """Return how far the checks on a concept go: none, by a tool or a job only, or by a person."""
    events = verification_events(document)
    if any(event.is_by_a_person for event in events):
        return HUMAN_REVIEWED
    return MACHINE_CONFIRMED if events else UNVERIFIED


def source_ids(sources: list[object]) -> list[str]:
    """Return the ids the sources of a concept give, in the order they are written."""
    return [
        str(source[ID_KEY]) for source in sources if isinstance(source, dict) and ID_KEY in source
    ]


def footnote_findings(document: Document, known_ids: list[str]) -> list[Finding]:
    """Return a finding for each footnote label that is no source's id, where it first appears."""
    labels_by_line = [
        (line.line_number, matched.group("label"))
        for line in prose_lines(document.body, document.body_line_number)
        for matched in FOOTNOTE_PATTERN.finditer(line.text)
    ]
    first_line_by_label = {label: line_number for line_number, label in reversed(labels_by_line)}
    return [
        Finding(
            document.path,
            line_number,
            SOURCES,
            f"the footnote `[^{label}]` names no source: `sources` has no entry with that `id`",
        )
        for label, line_number in sorted(first_line_by_label.items(), key=lambda item: item[1])
        # `id: 01` is the number 1 to YAML, so a label of digits is compared as a number.
        if label not in known_ids and not (label.isdigit() and str(int(label)) in known_ids)
    ]


def sources_findings(bundle: Bundle, document: Document) -> list[Finding]:
    """Return what is wrong with how a concept records what it was drawn from."""
    if SOURCES_KEY not in document.fields:
        return []
    line_number = document.line_number_of(SOURCES_KEY)
    sources = document.fields[SOURCES_KEY]
    if not isinstance(sources, list):
        message = "`sources` must be a list, each entry with a `resource`: where the facts are from"
        return [Finding(document.path, line_number, SOURCES, message)]
    resources = [
        source.get(RESOURCE_KEY) if isinstance(source, dict) else None for source in sources
    ]
    without_resource = [
        f"source {source_index + 1} has no `resource`: an address, a path, or what was read"
        for source_index, resource in enumerate(resources)
        if not isinstance(resource, str) or not resource.strip()
    ]
    missing_in_bundle = [
        f"the source `{resource}` is not in the bundle: a `resource` that starts with `/` is a"
        " path from the bundle's own directory"
        for resource in resources
        if isinstance(resource, str)
        and resource.startswith(BUNDLE_ROOT_PREFIX)
        and not (linked_path(bundle.directory, document, resource) or bundle.directory).exists()
    ]
    known_ids = source_ids(sources)
    repeated_ids = sorted({known_id for known_id in known_ids if known_ids.count(known_id) > 1})
    repeated = [
        f"two sources share the id `{repeated_id}`; a footnote could mean either"
        for repeated_id in repeated_ids
    ]
    return [
        *(
            Finding(document.path, line_number, SOURCES, problem)
            for problem in (*without_resource, *missing_in_bundle, *repeated)
        ),
        *footnote_findings(document, known_ids),
    ]


def trust_findings(bundle: Bundle, document: Document) -> list[Finding]:
    """Return what one concept breaks of the rules on who wrote it, checked it and fed it."""
    if document.frontmatter_problem is not None:
        return []
    return [
        *generated_findings(document),
        *status_findings(document),
        *verified_findings(document),
        *sources_findings(bundle, document),
    ]


def stale_since(document: Document, now: datetime.datetime) -> str:
    """Return the `stale_after` of a concept that has passed it, as written, or an empty string."""
    stale_after = document.fields.get(STALE_AFTER_KEY)
    stale_time = time_of(stale_after)
    return str(stale_after) if stale_time is not None and now >= stale_time else ""


def stale_notes(document: Document, now: datetime.datetime) -> list[Note]:
    """Return a note when a concept is past the time it says it goes stale.

    A note and not a finding: a gate that turns red with the calendar says nothing about the change
    it is checking.
    """
    passed_time = stale_since(document, now)
    if not passed_time:
        return []
    line_number = document.line_number_of(STALE_AFTER_KEY)
    return [Note(document.path, line_number, f"stale since {passed_time}; check it still holds")]
