"""Check each `log.md`: the history of its part of the bundle, in dated entries, newest first.

A log says what changed and why, which the diff of a commit does not (OKF 0.2, section 9). Its
second-level headings are the dates of its entries:

    log   a `##` heading is not a date written as `## 2026-10-04`, or the dates do not run
          newest first

A heading is read as Markdown has it: indented by up to three spaces, or closed with a run of `#`,
it is still a heading; inside a code block or a comment it is not one.
"""

import datetime
import itertools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from okf.documents import Bundle, read_text_file
from okf.findings import LOG, Finding
from okf.markdown import heading_of, prose_lines

ENTRY_HEADING_LEVEL: Final = 2
ISO_DATE_PATTERN: Final = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class DatedHeading:
    """One entry heading of a log: the line it is on, and its date when it has a real one."""

    line_number: int
    entry_date: datetime.date | None


def date_in(heading: str) -> datetime.date | None:
    """Return the date a heading states, or None when it is not a real date as year-month-day."""
    if not ISO_DATE_PATTERN.fullmatch(heading):
        return None
    try:
        return datetime.date.fromisoformat(heading)
    except ValueError:
        return None


def dated_headings(log_text: str) -> list[DatedHeading]:
    """Return the second-level headings of a log, in the order they are written."""
    headings = [(line.line_number, heading_of(line.text)) for line in prose_lines(log_text)]
    return [
        DatedHeading(line_number=line_number, entry_date=date_in(heading.text))
        for line_number, heading in headings
        if heading is not None and heading.level == ENTRY_HEADING_LEVEL
    ]


def log_file_findings(log_file: Path, log_text: str) -> list[Finding]:
    """Return what is wrong with the entry headings of one log."""
    headings = dated_headings(log_text)
    not_a_date = "a log's `##` headings are the dates of its entries, written as `## 2026-10-04`"
    undated_findings = [
        Finding(log_file, heading.line_number, LOG, not_a_date)
        for heading in headings
        if heading.entry_date is None
    ]
    dated = [heading for heading in headings if heading.entry_date is not None]
    out_of_order = "this entry is not older than the one above it; a log runs newest first"
    order_findings = [
        Finding(log_file, later_heading.line_number, LOG, out_of_order)
        for earlier_heading, later_heading in itertools.pairwise(dated)
        if earlier_heading.entry_date is not None
        and later_heading.entry_date is not None
        and later_heading.entry_date >= earlier_heading.entry_date
    ]
    return [*undated_findings, *order_findings]


def log_findings(bundle: Bundle) -> list[Finding]:
    """Return what is wrong with every log of the bundle.

    Raises:
        UnreadableBundleError: If a log cannot be read.
    """
    return [
        finding
        for log_file in bundle.log_files
        for finding in log_file_findings(log_file, read_text_file(log_file))
    ]
