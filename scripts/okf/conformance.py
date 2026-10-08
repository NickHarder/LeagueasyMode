"""The rules the format itself sets (OKF 0.2, section 11): what makes a bundle conformant.

A concept breaks one of them when:

    frontmatter   it does not open with a YAML block that can be read
    type          its frontmatter has no `type`, or one that is not a piece of text

Everything else the format describes is optional, and a consumer must not refuse a bundle for it.
"""

from typing import Final

from okf.documents import Document
from okf.findings import FRONTMATTER, TYPE, Finding

TYPE_KEY: Final = "type"


def type_findings(document: Document) -> list[Finding]:
    """Return a finding when a concept does not say, in text, what kind of thing it is."""
    if TYPE_KEY not in document.fields:
        message = "the frontmatter has no `type`; every concept says what kind of thing it is"
        return [Finding(document.path, 1, TYPE, message)]
    declared_type = document.fields[TYPE_KEY]
    if isinstance(declared_type, str) and declared_type.strip():
        return []
    message = "`type` must be a short piece of text, such as `Metric` or `Playbook`"
    return [Finding(document.path, document.line_number_of(TYPE_KEY), TYPE, message)]


def conformance_findings(document: Document) -> list[Finding]:
    """Return what keeps one concept from conforming to the format."""
    if document.frontmatter_problem is not None:
        return [Finding(document.path, 1, FRONTMATTER, document.frontmatter_problem)]
    return type_findings(document)
