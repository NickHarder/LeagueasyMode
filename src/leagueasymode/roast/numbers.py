"""How numbers are written, in one place: the exhibits, the lines and the validator all use it.

The validator compares the numbers in a line with the numbers in the exhibits the line cites, as
text, so every number a roast writes must come from these functions.
"""

import re
from typing import Final

# A number as a roast writes one: digits, with thousands commas, a decimal point, a sign, a clock's
# colon or a percent sign.
NUMBER_PATTERN: Final = re.compile(r"[-+]?\d[\d,]*(?:[.:]\d+)?%?")
SECONDS_PER_MINUTE: Final = 60


def format_count(count: int) -> str:
    """Write a whole number, with thousands commas.

    Args:
        count: The number.

    Returns:
        The text, such as "1,661".
    """
    return f"{count:,}"


def format_signed(count: int) -> str:
    """Write a whole number with its sign, for a difference.

    Args:
        count: The difference.

    Returns:
        The text, such as "+1,013", "-1,661" or "0".
    """
    return f"{count:+,}" if count else "0"


def format_percent(share: float) -> str:
    """Write a share as a whole percentage.

    Args:
        share: The share, from 0 to 1.

    Returns:
        The text, such as "38%".
    """
    return f"{round(share * 100)}%"


def format_clock(total_seconds: int) -> str:
    """Write a duration as a game clock.

    Args:
        total_seconds: The duration, in seconds.

    Returns:
        The text, such as "31:42".
    """
    minutes, seconds = divmod(total_seconds, SECONDS_PER_MINUTE)
    return f"{minutes}:{seconds:02d}"


def number_tokens(text: str) -> list[str]:
    """Return every number written in a text, as written.

    Args:
        text: The text.

    Returns:
        The numbers, in order, such as ["9", "1,661"].
    """
    return NUMBER_PATTERN.findall(text)
