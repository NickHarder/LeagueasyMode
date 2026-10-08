"""Where a document may be, and what it is called.

The format says nothing on either. It reserves two file names and leaves the rest to whoever writes
the bundle. This project decides both, so that a reader knows where to look and a writer knows
where a thing goes:

    layout   a concept at the root of the bundle that is not named in capitals; a concept or a
             directory below the root that is not named in lowercase words joined by hyphens (a
             concept may also be named for its id); a Markdown file outside the bundle that no
             concept lists with who reads it there

**Names.** The root of the bundle holds the few documents a reader starts from, named in capitals:
`PLAN.md`, `KEY_METRICS.md`. Every other concept sits in a directory for its kind, `metrics/` or
`references/`, under a name such as `eval-pass-rate.md` or `NS-01.md`. A file that is not Markdown
keeps whatever name its own tool gives it.

**The boundary.** What a project knows is in the bundle. A Markdown file anywhere else in the
repository is there because a tool reads it at that place, and one concept of the bundle says so,
in an `outside` list in its frontmatter:

    outside:
      - { path: AGENTS.md, read_by: "Claude Code and Cursor, at the start of every session" }
      - { path: vendor/docs/, read_by: "The upstream project, which keeps its own documents" }
      - { path: "**/README.md", read_by: "The code host, when a directory is browsed" }

A `path` is a file from the repository's root, a directory (it ends in `/`), or a name in any
directory (it starts with `**/`). Every entry says who reads the file there: an exception gives its
reason. A directory whose name starts with a dot belongs to a tool, and so do `node_modules` and
`__pycache__`; nothing inside them is looked at. The list is one text for the reader and for the
gate, so the two cannot drift apart.

The rule runs when the check is told where the repository is (`--repository .`), as the gate and
CI tell it. A bundle that is checked by itself is held to the bundle's own rules alone.
"""

import os
import re
from pathlib import Path
from typing import Final

from okf.documents import (
    HIDDEN_NAME_PREFIX,
    INDEX_FILE_NAME,
    MARKDOWN_SUFFIX,
    SKIPPED_DIRECTORY_NAMES,
    Bundle,
    UnreadableBundleError,
)
from okf.findings import LAYOUT, Finding
from okf.index import indexed_directories
from okf.trace import WHOLE_ID_PATTERN

ROOT_NAME_PATTERN: Final = re.compile(r"[A-Z][A-Z0-9_]*")
LOWER_NAME_PATTERN: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

OUTSIDE_KEY: Final = "outside"
PATH_KEY: Final = "path"
READ_BY_KEY: Final = "read_by"
ANY_DIRECTORY_PREFIX: Final = "**/"
DIRECTORY_SUFFIX: Final = "/"
USUAL_MAP_PATH: Final = Path("references") / "outside-the-bundle.md"


def concept_name_findings(bundle: Bundle) -> list[Finding]:
    """Return a finding for each concept whose file name does not follow the convention."""
    root_message = (
        "a concept at the root of the bundle is one a reader starts from, and is named in"
        " capitals, such as `PLAN.md`; a concept of any other kind goes in a directory for its"
        " kind, such as `references/`"
    )
    lower_message = (
        "below the root of the bundle a concept is named in lowercase words joined by hyphens,"
        " such as `eval-pass-rate.md`, or for its id, such as `NS-01.md`"
    )
    at_the_root = [
        Finding(concept.path, 1, LAYOUT, root_message)
        for concept in bundle.concepts
        if len(concept.relative_path.parts) == 1
        and not ROOT_NAME_PATTERN.fullmatch(concept.path.stem)
    ]
    below_the_root = [
        Finding(concept.path, 1, LAYOUT, lower_message)
        for concept in bundle.concepts
        if len(concept.relative_path.parts) > 1
        and not LOWER_NAME_PATTERN.fullmatch(concept.path.stem)
        and not WHOLE_ID_PATTERN.fullmatch(concept.path.stem)
    ]
    return [*at_the_root, *below_the_root]


def directory_name_findings(bundle: Bundle) -> list[Finding]:
    """Return a finding for each directory of the bundle whose name does not follow the convention.

    A directory has no line to point at, so the finding is on its index.
    """
    return [
        Finding(
            directory / INDEX_FILE_NAME,
            1,
            LAYOUT,
            f"the directory `{directory.name}` must be named in lowercase words joined by hyphens,"
            " such as `references`",
        )
        for directory in indexed_directories(bundle)
        if directory != bundle.directory and not LOWER_NAME_PATTERN.fullmatch(directory.name)
    ]


def is_an_entry(entry: object) -> bool:
    """Return whether an entry of `outside` names a path and says who reads it there."""
    return (
        isinstance(entry, dict)
        and isinstance(entry.get(PATH_KEY), str)
        and bool(entry[PATH_KEY].strip())
        and isinstance(entry.get(READ_BY_KEY), str)
        and bool(entry[READ_BY_KEY].strip())
    )


def listed_paths(bundle: Bundle) -> list[str]:
    """Return every path that a concept of the bundle lists as living outside it, for a reason."""
    return [
        str(entry[PATH_KEY]).strip()
        for concept in bundle.concepts
        for entries in [concept.fields.get(OUTSIDE_KEY)]
        if isinstance(entries, list)
        for entry in entries
        if is_an_entry(entry)
    ]


def list_findings(bundle: Bundle) -> list[Finding]:
    """Return what is wrong with how a concept lists what lives outside the bundle."""
    not_a_list = (
        f"`{OUTSIDE_KEY}` must be a list, one"
        f" `{{ {PATH_KEY}: <path>, {READ_BY_KEY}: <who reads it there> }}` for each file or"
        " directory"
    )
    listing_concepts = [concept for concept in bundle.concepts if OUTSIDE_KEY in concept.fields]
    shape_findings = [
        Finding(concept.path, concept.line_number_of(OUTSIDE_KEY), LAYOUT, not_a_list)
        for concept in listing_concepts
        if not isinstance(concept.fields[OUTSIDE_KEY], list)
    ]
    entry_findings = [
        Finding(
            concept.path,
            concept.line_number_of(OUTSIDE_KEY),
            LAYOUT,
            f"entry {entry_index + 1} of `{OUTSIDE_KEY}` must be"
            f" `{{ {PATH_KEY}: <path>, {READ_BY_KEY}: <who reads it there> }}`: a file that lives"
            " outside the bundle says which tool needs it there",
        )
        for concept in listing_concepts
        for entries in [concept.fields[OUTSIDE_KEY]]
        if isinstance(entries, list)
        for entry_index, entry in enumerate(entries)
        if not is_an_entry(entry)
    ]
    return [*shape_findings, *entry_findings]


def is_listed(relative_path: Path, paths: list[str]) -> bool:
    """Return whether a file's path from the repository's root is covered by a listed path."""
    path_text = relative_path.as_posix()
    return any(
        relative_path.name == listed_path.removeprefix(ANY_DIRECTORY_PREFIX)
        if listed_path.startswith(ANY_DIRECTORY_PREFIX)
        else path_text.startswith(listed_path)
        if listed_path.endswith(DIRECTORY_SUFFIX)
        else path_text == listed_path
        for listed_path in paths
    )


def markdown_files_outside(bundle: Bundle, repository_directory: Path) -> list[Path]:
    """Return each Markdown file of the repository outside the bundle, by its path from the root.

    A directory whose name starts with a dot, and one that a package manager or an interpreter
    fills, belongs to a tool: nothing inside it is returned.

    Raises:
        UnreadableBundleError: If the repository's directory is not there.
    """
    if not repository_directory.is_dir():
        message = f"{repository_directory} does not exist, or is not a directory"
        raise UnreadableBundleError(message)
    bundle_directory = bundle.directory.resolve()
    found_files: list[Path] = []
    for directory_text, directory_names, file_names in os.walk(repository_directory):
        directory = Path(directory_text)
        # Assigning to the slice tells os.walk which directories not to go down into.
        directory_names[:] = sorted(
            name
            for name in directory_names
            if not name.startswith(HIDDEN_NAME_PREFIX)
            and name not in SKIPPED_DIRECTORY_NAMES
            and (directory / name).resolve() != bundle_directory
        )
        found_files.extend(
            (directory / name).relative_to(repository_directory)
            for name in sorted(file_names)
            if name.endswith(MARKDOWN_SUFFIX)
        )
    return found_files


def boundary_findings(bundle: Bundle, repository_directory: Path) -> list[Finding]:
    """Return a finding for each Markdown file outside the bundle that no concept lists.

    Raises:
        UnreadableBundleError: If the repository's directory is not there.
    """
    paths = listed_paths(bundle)
    listing_concepts = [
        concept.path for concept in bundle.concepts if OUTSIDE_KEY in concept.fields
    ]
    the_list = listing_concepts[0] if listing_concepts else bundle.directory / USUAL_MAP_PATH
    message = (
        "this Markdown file is outside the bundle, and no concept lists it: make it a concept"
        f" under `{bundle.directory}/`, or add it to the `{OUTSIDE_KEY}` list of `{the_list}`"
        " with who reads it here"
    )
    return [
        Finding(repository_directory / relative_path, 1, LAYOUT, message)
        for relative_path in markdown_files_outside(bundle, repository_directory)
        if not is_listed(relative_path, paths)
    ]


def layout_findings(bundle: Bundle, repository_directory: Path) -> list[Finding]:
    """Return everything that is not where, or named as, the layout has it.

    Raises:
        UnreadableBundleError: If the repository's directory is not there.
    """
    return [
        *concept_name_findings(bundle),
        *directory_name_findings(bundle),
        *list_findings(bundle),
        *boundary_findings(bundle, repository_directory),
    ]
