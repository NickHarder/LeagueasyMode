"""A source that changed after the concept drawn from it: a note, never a finding (OKF 0.2, 5.1).

A concept that describes code names those files in `sources`, by a path from the concept's own
directory, such as `../src/<module>/config.py`. The format records when a source last changed
(`last_modified`); nothing writes it here, because a date written into the file would go stale with
the file. It is read from git instead, each time:

    the last commit of a source is newer than the concept   the code may no longer be what the
                                                            concept says it is
    a source the concept names as a file is not there      what it says of that file has nothing
                                                            behind it

A concept is as new as the latest of three times: `generated.at`, the owner's last approval, and
its own last commit. The third keeps a concept and its code changed in one commit from being
noted. Only files outside the bundle are compared, never a folder, an address or a description of
what was read. A concept drawn from another concept is held by that one's approval, and a source in
the bundle that only grows, such as a list of reasons, would otherwise flag all that cite it.
Outside a git repository, with no git, or for a file git does not track, nothing is compared: a
note that cannot be sure is not given.
"""

import datetime
import functools
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from okf.documents import Bundle, Document
from okf.findings import Note
from okf.policy import EXTERNAL_TARGET_PATTERN, linked_path, resolved_path
from okf.trust import (
    RESOURCE_KEY,
    SOURCES_KEY,
    generated_time,
    time_of,
    verification_events,
)

PATH_SEPARATOR: Final = "/"
WHITESPACE_PATTERN: Final = re.compile(r"\s")
LAST_COMMIT_TIME_COMMAND: Final = ("log", "-1", "--format=%cI", "--")


@dataclass(frozen=True)
class WrittenTime:
    """A time a concept was written, approved or committed at: as an instant, and as said."""

    time: datetime.datetime
    said: str


def is_a_file_path(resource: str) -> bool:
    """Return whether a source's `resource` names a file: a path, not an address or a description.

    A path has a separator and no space. A description of what was read, such as "every order
    placed in September", has spaces, and an address has a scheme.
    """
    return (
        PATH_SEPARATOR in resource
        and WHITESPACE_PATTERN.search(resource) is None
        and EXTERNAL_TARGET_PATTERN.match(resource) is None
    )


@functools.cache
def last_commit_time(file_path: Path) -> datetime.datetime | None:
    """Return when the last commit that changed a file was made, or None when git cannot say."""
    git_executable = shutil.which("git")
    if git_executable is None:
        return None
    done = subprocess.run(  # noqa: S603  fixed arguments, no shell, the executable is resolved
        [git_executable, "-C", str(file_path.parent), *LAST_COMMIT_TIME_COMMAND, file_path.name],
        capture_output=True,
        text=True,
        check=False,
    )
    return time_of(done.stdout.strip()) if done.returncode == 0 else None


def times_written(document: Document) -> list[WrittenTime]:
    """Return when a concept says it was written and approved, and when it was last committed."""
    written_time = generated_time(document)
    commit_time = last_commit_time(document.path.resolve())
    return [
        *(
            [WrittenTime(written_time, f"written {written_time.isoformat()}")]
            if written_time
            else []
        ),
        *(
            WrittenTime(event.time, f"approved {event.time_text}")
            for event in verification_events(document)
            if event.is_by_a_person
        ),
        *(
            [WrittenTime(commit_time, f"committed {commit_time.isoformat()}")]
            if commit_time
            else []
        ),
    ]


def named_files(bundle: Bundle, document: Document) -> list[tuple[str, Path]]:
    """Return each source of a concept that names a file outside the bundle: as written, on disk."""
    sources = document.fields.get(SOURCES_KEY)
    resources = [
        source.get(RESOURCE_KEY)
        for source in (sources if isinstance(sources, list) else [])
        if isinstance(source, dict)
    ]
    bundle_directory = bundle.directory.resolve()
    return [
        (resource, source_path)
        for resource in resources
        if isinstance(resource, str) and is_a_file_path(resource)
        for linked in [linked_path(bundle.directory, document, resource)]
        for source_path in [resolved_path(linked) if linked is not None else None]
        if source_path is not None and not source_path.is_relative_to(bundle_directory)
    ]


def drift_notes(bundle: Bundle, document: Document) -> list[Note]:
    """Return a note for each file a concept is drawn from that changed after it, or is gone."""
    if document.frontmatter_problem is not None:
        return []
    line_number = document.line_number_of(SOURCES_KEY)
    files = named_files(bundle, document)
    gone = [
        Note(
            document.path,
            line_number,
            f"the source `{resource}` is not there; check what this concept says of it",
        )
        for resource, source_path in files
        if not source_path.exists()
    ]
    written = times_written(document)
    if not written:
        return gone
    newest = max(written, key=lambda written_time: written_time.time)
    changed = [
        Note(
            document.path,
            line_number,
            f"the source `{resource}` changed in a commit of {changed_time.isoformat()}, after this"
            f" concept was last {newest.said}; check it still holds",
        )
        for resource, source_path in files
        if source_path.is_file()
        for changed_time in [last_commit_time(source_path)]
        if changed_time is not None and changed_time > newest.time
    ]
    return [*gone, *changed]
