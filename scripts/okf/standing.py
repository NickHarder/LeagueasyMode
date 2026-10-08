"""Where each concept of a bundle stands: its status, how far it has been checked, and its approval.

This is what a reader works out from the frontmatter before trusting a concept (OKF 0.2, section 5):
the status as written, the trust tier that follows from `verified`, whether the owner's approval
still covers the text, and whether the concept is past the time it says it goes stale.
"""

import datetime
from typing import Final

from okf.approval import approval_summary
from okf.documents import Bundle, Document
from okf.trust import STATUS_KEY, stale_since, trust_tier

NO_STATUS: Final = "-"
COLUMN_GAP: Final = "  "


def standing_cells(document: Document, now: datetime.datetime) -> list[str]:
    """Return what one row of the table says about one concept."""
    passed_time = stale_since(document, now)
    return [
        str(document.path),
        document.text_field(STATUS_KEY) or NO_STATUS,
        trust_tier(document),
        approval_summary(document),
        *([f"stale since {passed_time}"] if passed_time else []),
    ]


def standing_rows(bundle: Bundle, now: datetime.datetime) -> list[str]:
    """Return one line for each concept of the bundle, its columns lined up."""
    rows = [standing_cells(concept, now) for concept in bundle.concepts]
    column_count = max((len(cells) for cells in rows), default=0)
    column_widths = [
        max(len(cells[column_index]) for cells in rows if column_index < len(cells))
        for column_index in range(column_count)
    ]
    return [
        COLUMN_GAP.join(
            cell.ljust(column_widths[column_index]) for column_index, cell in enumerate(cells)
        ).rstrip()
        for cells in rows
    ]
