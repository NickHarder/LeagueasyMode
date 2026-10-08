"""The rules this project adds to the format: stricter than a consumer may be, for what it writes.

The format lets a concept go without a title, and lets a link lead nowhere, so that a reader never
refuses a bundle. A writer can do better:

    title-description   a concept has no `title`, or no `description` that is one sentence on
                        one line
    link                a link leads to a file that does not exist
"""

import re
from pathlib import Path
from typing import Final
from urllib.parse import unquote

from okf.documents import Bundle, Document
from okf.findings import LINK, TITLE_DESCRIPTION, Finding
from okf.markdown import links_in, prose_lines

TITLE_KEY: Final = "title"
DESCRIPTION_KEY: Final = "description"
# A target with a scheme (https:, mailto:) or a host (//example.com) leads out of the repository.
EXTERNAL_TARGET_PATTERN: Final = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:|//")
FRAGMENT_SEPARATOR: Final = "#"
BUNDLE_ROOT_PREFIX: Final = "/"


def title_findings(document: Document) -> list[Finding]:
    """Return a finding when a concept has no title that is text."""
    if TITLE_KEY not in document.fields:
        message = "the frontmatter has no `title`; an index shows it before the concept is opened"
        return [Finding(document.path, 1, TITLE_DESCRIPTION, message)]
    if document.text_field(TITLE_KEY):
        return []
    message = "`title` must be a short piece of text"
    return [Finding(document.path, document.line_number_of(TITLE_KEY), TITLE_DESCRIPTION, message)]


def description_findings(document: Document) -> list[Finding]:
    """Return a finding when a concept has no description that is one sentence on one line."""
    if DESCRIPTION_KEY not in document.fields:
        message = "the frontmatter has no `description`: one sentence on what the concept is about"
        return [Finding(document.path, 1, TITLE_DESCRIPTION, message)]
    description = document.text_field(DESCRIPTION_KEY)
    if description and "\n" not in description:
        return []
    message = "`description` must be one sentence, on one line"
    line_number = document.line_number_of(DESCRIPTION_KEY)
    return [Finding(document.path, line_number, TITLE_DESCRIPTION, message)]


def linked_path(bundle_directory: Path, document: Document, target: str) -> Path | None:
    """Return the file a link leads to, or None when it leads out of the repository or nowhere new.

    A target that starts with `/` is read from the bundle's own directory; any other is read from
    the directory of the document that holds the link.
    """
    if EXTERNAL_TARGET_PATTERN.match(target):
        return None
    path_text = unquote(target.split(FRAGMENT_SEPARATOR, 1)[0])
    if not path_text:
        return None
    if path_text.startswith(BUNDLE_ROOT_PREFIX):
        return bundle_directory / path_text.lstrip(BUNDLE_ROOT_PREFIX)
    return document.path.parent / path_text


def resolved_path(path: Path) -> Path | None:
    """Return a path with its symbolic links followed, or None when it can name no file.

    A link can spell a character no file name holds, such as the `%00` of a null character.
    """
    try:
        return path.resolve()
    except (OSError, ValueError):
        return None


def link_findings(bundle: Bundle, document: Document) -> list[Finding]:
    """Return a finding for each link in a concept's body that leads to no file."""
    links = links_in(prose_lines(document.body, document.body_line_number))
    linked_paths = [(link, linked_path(bundle.directory, document, link.target)) for link in links]
    return [
        Finding(
            document.path,
            link.line_number,
            LINK,
            f"the link to `{link.target}` leads nowhere: there is no such file",
        )
        for link, target_path in linked_paths
        if target_path is not None and not target_path.exists()
    ]


def policy_findings(bundle: Bundle, document: Document) -> list[Finding]:
    """Return what one concept breaks of the rules this project adds to the format."""
    if document.frontmatter_problem is not None:
        return []
    return [
        *title_findings(document),
        *description_findings(document),
        *link_findings(bundle, document),
    ]
