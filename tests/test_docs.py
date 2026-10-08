import re
from pathlib import Path
from typing import Final

import pytest

from leagueasymode.config import REPOSITORY_ROOT

# The project's documents outside the knowledge bundle. Add a document here when it is created; one
# that does not exist yet is skipped. The bundle itself is held to its rules, links among them, by
# scripts/okf_bundle.py in the gate's lint group.
DOCUMENT_NAMES: Final = [
    "AGENTS.md",
    "HANDOFF.md",
    "README.md",
]

MARKDOWN_LINK: Final = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
EXTERNAL_PREFIXES: Final = ("http://", "https://", "mailto:", "#")


EXISTING_DOCUMENT_NAMES: Final = [
    name for name in DOCUMENT_NAMES if (REPOSITORY_ROOT / name).exists()
]


def relative_link_targets(document_path: Path) -> list[str]:
    link_targets = MARKDOWN_LINK.findall(document_path.read_text())
    return [
        link_target.split("#", 1)[0]
        for link_target in link_targets
        if not link_target.startswith(EXTERNAL_PREFIXES)
    ]


def test_the_agent_instructions_exist() -> None:
    assert "AGENTS.md" in EXISTING_DOCUMENT_NAMES


@pytest.mark.parametrize("document_name", EXISTING_DOCUMENT_NAMES)
def test_relative_links_resolve(document_name: str) -> None:
    document_path = REPOSITORY_ROOT / document_name
    missing_targets = [
        link_target
        for link_target in relative_link_targets(document_path)
        if link_target and not (document_path.parent / link_target).exists()
    ]
    assert not missing_targets, f"{document_name} links to missing files: {missing_targets}"
