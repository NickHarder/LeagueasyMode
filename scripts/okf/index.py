"""Write each directory's `index.md` from the concepts in it, and check that the ones on disk match.

An index lets a reader see what a directory holds before opening anything (OKF 0.2, section 8): a
heading for each `type`, and under it one line for each concept, with its title and its
description. It has no frontmatter, except that the bundle's own index declares the version of
the format. Because the text comes from the frontmatter alone, it is the same on every run, and
needs no model to write it. A name that a Markdown reader could not follow as written, one with a
space or a bracket in it, goes between angle brackets.

    index   a directory has no `index.md`, or one that is not what `make docs-index` writes
"""

import re
from pathlib import Path
from typing import Final

from okf.documents import (
    INDEX_FILE_NAME,
    LOG_FILE_NAME,
    Bundle,
    Document,
    UnreadableBundleError,
)
from okf.findings import INDEX, Finding

OKF_VERSION: Final = "0.2"
TYPE_KEY: Final = "type"
TITLE_KEY: Final = "title"
DESCRIPTION_KEY: Final = "description"

UNTYPED_HEADING: Final = "Other"
SUBDIRECTORIES_HEADING: Final = "Subdirectories"
HISTORY_HEADING: Final = "History"
FILES_HEADING: Final = "Files"
LOG_DESCRIPTION: Final = "What changed and why, newest first."
# A space ends a link's destination, and a bracket can close the link before the name ends.
ENDS_A_DESTINATION_EARLY_PATTERN: Final = re.compile(r"[\s()<>]")
ANGLE_BRACKET_PATTERN: Final = re.compile(r"[<>]")


def type_of(concept: Document) -> str:
    """Return the heading a concept is listed under: its `type`, or a catch-all without one."""
    return concept.text_field(TYPE_KEY) or UNTYPED_HEADING


def title_of(concept: Document) -> str:
    """Return what a concept is called in an index: its `title`, or its file's name without one."""
    return " ".join(concept.text_field(TITLE_KEY).split()) or concept.path.stem


def destination(path_text: str) -> str:
    """Return a path as the destination of a link, written so that a Markdown reader follows it."""
    if not ENDS_A_DESTINATION_EARLY_PATTERN.search(path_text):
        return path_text
    escaped_path_text = ANGLE_BRACKET_PATTERN.sub(lambda matched: f"\\{matched.group()}", path_text)
    return f"<{escaped_path_text}>"


def in_index_order(type_names: set[str]) -> list[str]:
    """Return the types in the order an index lists them: by the alphabet, whatever their case.

    Two types that differ only in case are put in order by their own text, so that the order
    never depends on how a run happens to hold the set.
    """
    return sorted(type_names, key=lambda type_name: (type_name.casefold(), type_name))


def concept_entry(concept: Document) -> str:
    """Return the line that lists one concept in its directory's index."""
    description = " ".join(concept.text_field(DESCRIPTION_KEY).split())
    described = f" - {description}" if description else ""
    return f"* [{title_of(concept)}]({destination(concept.path.name)}){described}"


def counted(count: int, singular_noun: str) -> str:
    """Return a count with its noun, as `1 file` or `3 files`."""
    return f"{count} {singular_noun}" if count == 1 else f"{count} {singular_noun}s"


def subdirectory_entry(bundle: Bundle, subdirectory: Path) -> str:
    """Return the line that lists one subdirectory: how many concepts it holds, of what types."""
    concepts_below = [
        concept for concept in bundle.concepts if subdirectory in concept.path.parents
    ]
    files_below = [
        file for file in (*bundle.other_files, *bundle.log_files) if subdirectory in file.parents
    ]
    type_names = ", ".join(in_index_order({type_of(concept) for concept in concepts_below}))
    summary = (
        f"{counted(len(concepts_below), 'concept')}: {type_names}."
        if concepts_below
        else f"{counted(len(files_below), 'file')}."
    )
    index_path_text = destination(f"{subdirectory.name}/{INDEX_FILE_NAME}")
    return f"* [{subdirectory.name}]({index_path_text}) - {summary}"


def indexed_directories(bundle: Bundle) -> list[Path]:
    """Return every directory that gets an index: the bundle's own, and each that holds a file."""
    listed_files = [
        *(concept.path for concept in bundle.concepts),
        *bundle.log_files,
        *bundle.other_files,
    ]
    directories_with_files = {
        directory
        for file in listed_files
        for directory in file.parents
        if directory == bundle.directory or bundle.directory in directory.parents
    }
    return sorted({bundle.directory, *directories_with_files}, key=lambda path: path.as_posix())


def type_sections(concepts_here: list[Document]) -> list[tuple[str, list[str]]]:
    """Return one section for each type among a directory's concepts, in the order of the types."""
    type_names = in_index_order({type_of(concept) for concept in concepts_here})
    return [
        (
            type_name,
            [
                concept_entry(concept)
                for concept in sorted(
                    concepts_here,
                    key=lambda concept: (title_of(concept).casefold(), concept.path.name),
                )
                if type_of(concept) == type_name
            ],
        )
        for type_name in type_names
    ]


def index_text(bundle: Bundle, directory: Path) -> str:
    """Return the text of one directory's index, as it follows from what the directory holds."""
    concepts_here = [concept for concept in bundle.concepts if concept.path.parent == directory]
    subdirectories_here = [
        candidate for candidate in indexed_directories(bundle) if candidate.parent == directory
    ]
    other_sections = [
        (
            SUBDIRECTORIES_HEADING,
            [subdirectory_entry(bundle, subdirectory) for subdirectory in subdirectories_here],
        ),
        (
            HISTORY_HEADING,
            [
                f"* [{LOG_FILE_NAME}]({LOG_FILE_NAME}) - {LOG_DESCRIPTION}"
                for log_file in bundle.log_files
                if log_file.parent == directory
            ],
        ),
        (
            FILES_HEADING,
            [
                f"* [{file.name}]({destination(file.name)})"
                for file in bundle.other_files
                if file.parent == directory
            ],
        ),
    ]
    written_sections = [
        f"# {heading}\n\n" + "\n".join(entries) + "\n"
        for heading, entries in (*type_sections(concepts_here), *other_sections)
        if entries
    ]
    version_blocks = (
        [f'---\nokf_version: "{OKF_VERSION}"\n---\n'] if directory == bundle.directory else []
    )
    return "\n".join([*version_blocks, *written_sections])


def first_differing_line_number(existing_text: str, expected_text: str) -> int:
    """Return the first line on which two texts differ, or the line after the shorter one ends."""
    existing_lines = existing_text.splitlines()
    expected_lines = expected_text.splitlines()
    differing_line_numbers = [
        line_index + 1
        for line_index, (existing_line, expected_line) in enumerate(
            zip(existing_lines, expected_lines, strict=False)
        )
        if existing_line != expected_line
    ]
    return (
        differing_line_numbers[0]
        if differing_line_numbers
        else min(len(existing_lines), len(expected_lines)) + 1
    )


def read_bytes_of(index_file: Path) -> bytes:
    """Return an index file's bytes.

    Raises:
        UnreadableBundleError: If the file cannot be read.
    """
    try:
        return index_file.read_bytes()
    except OSError as error:
        message = f"{index_file} could not be read: {error}"
        raise UnreadableBundleError(message) from error


def index_findings(bundle: Bundle) -> list[Finding]:
    """Return a finding for each directory whose index is missing or out of date.

    Raises:
        UnreadableBundleError: If an index file cannot be read.
    """
    findings: list[Finding] = []
    for directory in indexed_directories(bundle):
        index_file = directory / INDEX_FILE_NAME
        expected_text = index_text(bundle, directory)
        if not index_file.is_file():
            message = "this directory has no index; run `make docs-index` to write it"
            findings.append(Finding(index_file, 1, INDEX, message))
            continue
        # An index that is not text at all is one more index that `make docs-index` did not write.
        existing_text = read_bytes_of(index_file).decode("utf-8", errors="replace")
        if existing_text != expected_text:
            message = "from this line on, this is not what `make docs-index` writes; run it"
            line_number = first_differing_line_number(existing_text, expected_text)
            findings.append(Finding(index_file, line_number, INDEX, message))
    return findings


def write_indexes(bundle: Bundle) -> tuple[list[Path], int]:
    """Write every index that is missing or out of date; return those, and the count of all.

    Raises:
        UnreadableBundleError: If an index cannot be read or written, as when a directory has its
            name.
    """
    directories = indexed_directories(bundle)
    written_files: list[Path] = []
    for directory in directories:
        index_file = directory / INDEX_FILE_NAME
        expected_bytes = index_text(bundle, directory).encode("utf-8")
        if index_file.is_file() and read_bytes_of(index_file) == expected_bytes:
            continue
        try:
            index_file.write_bytes(expected_bytes)
        except OSError as error:
            message = f"{index_file} could not be written: {error}"
            raise UnreadableBundleError(message) from error
        written_files.append(index_file)
    return written_files, len(directories)
