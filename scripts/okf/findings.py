"""What the bundle check reports: a broken rule, or something worth knowing that breaks none."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final

FRONTMATTER: Final = "frontmatter"
TYPE: Final = "type"
INDEX: Final = "index"
LOG: Final = "log"
TITLE_DESCRIPTION: Final = "title-description"
LINK: Final = "link"
GENERATED: Final = "generated"
STATUS: Final = "status"
VERIFIED: Final = "verified"
SOURCES: Final = "sources"
APPROVAL: Final = "approval"
TRACE: Final = "trace"
COMPUTATION: Final = "computation"
LAYOUT: Final = "layout"


@dataclass(frozen=True)
class Finding:
    """One broken rule at one place in one file."""

    path: Path
    line_number: int
    rule: str
    message: str

    def render(self) -> str:
        """Return the finding as one line a person or an editor can jump to."""
        return f"{self.path}:{self.line_number}: {self.rule} {self.message}"

    def sort_key(self) -> tuple[str, int, str, str]:
        """Return what findings are ordered by: the file, the line, then the rule."""
        return (self.path.as_posix(), self.line_number, self.rule, self.message)


@dataclass(frozen=True)
class Note:
    """Something a reader should know about one concept that breaks no rule and fails no gate."""

    path: Path
    line_number: int
    message: str

    def render(self) -> str:
        """Return the note as one line, set apart from a finding by how it starts."""
        return f"note: {self.path}:{self.line_number}: {self.message}"

    def sort_key(self) -> tuple[str, int, str]:
        """Return what notes are ordered by: the file, then the line."""
        return (self.path.as_posix(), self.line_number, self.message)
