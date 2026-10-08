"""Find the concepts of a bundle by what their frontmatter says: `make docs-find`.

An index lists one directory; this looks across the whole bundle at once, by `type`, `status`, a
tag, or the trust tier that `verified` gives (OKF 0.2, section 5.3), and lists each concept that
matches every filter given in the shape of an index line. It reads the frontmatter alone, with no
model and no network, and writes nothing. With `--json` it answers with the same fields as data,
for a tool to read.
"""

from dataclasses import dataclass
from typing import Final

from okf.documents import Bundle, Document
from okf.index import DESCRIPTION_KEY, TYPE_KEY, destination, title_of
from okf.trust import STATUS_KEY, trust_tier

TAGS_KEY: Final = "tags"


@dataclass(frozen=True)
class ConceptFilter:
    """What a concept must say to be found; a filter left as None lets every concept through."""

    type_name: str | None = None
    status: str | None = None
    tag: str | None = None
    tier: str | None = None


def tags_of(concept: Document) -> list[str]:
    """Return a concept's tags as text, in the order they are written."""
    tags = concept.fields.get(TAGS_KEY)
    return [str(tag) for tag in tags] if isinstance(tags, list) else []


def matches(concept: Document, concept_filter: ConceptFilter) -> bool:
    """Return whether a concept says everything the filter asks for; a type in any case."""
    return (
        (
            concept_filter.type_name is None
            or concept.text_field(TYPE_KEY).casefold() == concept_filter.type_name.casefold()
        )
        and (
            concept_filter.status is None or concept.text_field(STATUS_KEY) == concept_filter.status
        )
        and (concept_filter.tag is None or concept_filter.tag in tags_of(concept))
        and (concept_filter.tier is None or trust_tier(concept) == concept_filter.tier)
    )


def matching_concepts(bundle: Bundle, concept_filter: ConceptFilter) -> list[Document]:
    """Return the concepts of a bundle that the filter lets through, in the order of their paths."""
    return sorted(
        (concept for concept in bundle.concepts if matches(concept, concept_filter)),
        key=lambda concept: concept.path.as_posix(),
    )


def found_line(concept: Document) -> str:
    """Return a concept as an index lists it, with its path from where the command was run."""
    description = " ".join(concept.text_field(DESCRIPTION_KEY).split())
    described = f" - {description}" if description else ""
    return f"* [{title_of(concept)}]({destination(concept.path.as_posix())}){described}"


def found_fields(concept: Document) -> dict[str, object]:
    """Return what a tool reads of a found concept: its path, what it is, how far to trust it."""
    return {
        "path": concept.path.as_posix(),
        "title": title_of(concept),
        "description": " ".join(concept.text_field(DESCRIPTION_KEY).split()),
        "type": concept.text_field(TYPE_KEY),
        "status": concept.text_field(STATUS_KEY),
        "tier": trust_tier(concept),
        "tags": tags_of(concept),
    }
