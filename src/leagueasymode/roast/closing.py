"""The closing statement: one line, ready to paste into chat.

It is never longer than the chat limit, a threshold in `tuning.json`: Riot publishes none, so it
starts at 140 characters until the owner measures it. In the overlay it states its numbers and
nothing else: the exhibit letters ("(A)(B)") point to an evidence list nobody in chat can see, and
the site's signature names a site there is none of. Both can be asked for.
"""

from typing import Final

from pydantic import BaseModel, ConfigDict

from leagueasymode.roast.lines import CitedLine

CHAT_OPENER: Final = "gg. "
SIGNATURE: Final = " \N{EN DASH} nothingsmyfault.lol"


class ClosingLine(BaseModel):
    """The line to paste, and the exhibits it cites."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    exhibit_keys: tuple[str, ...]


def write_closing_line(
    lines: list[CitedLine],
    letter_by_key: dict[str, str],
    *,
    limit_characters: int,
    take: int = 0,
    verdict_title: str = "",
    cite_letters: bool = False,
    signature: bool = False,
) -> ClosingLine | None:
    """Pick the line to close on and write it for chat.

    Args:
        lines: The case's lines, already checked.
        letter_by_key: The letter of each cited exhibit.
        limit_characters: The longest line chat takes.
        take: Which of the lines that fit to use, for a reroll; it wraps around.
        verdict_title: The verdict's stamp, such as "TEAM DIFF", which opens the line when it
            fits.
        cite_letters: End the line with its exhibits' letters, as "(A)(B)".
        signature: End the line with the site's name, when it fits.

    Returns:
        The closing line, or None when no line fits.
    """
    candidates: list[ClosingLine] = []
    for line in lines:
        citation = (
            " " + "".join(f"({letter_by_key[key]})" for key in line.exhibit_keys)
            if cite_letters
            else ""
        )
        verdict_opener = f"{verdict_title}. " if verdict_title else ""
        signed = (
            [f"{CHAT_OPENER}{verdict_opener}{line.text}{citation}{SIGNATURE}"] if signature else []
        )
        longest_first = [
            *signed,
            f"{CHAT_OPENER}{verdict_opener}{line.text}{citation}",
            f"{CHAT_OPENER}{line.text}{citation}",
        ]
        fitting_texts = [text for text in longest_first if len(text) <= limit_characters]
        if fitting_texts:
            candidates.append(ClosingLine(text=fitting_texts[0], exhibit_keys=line.exhibit_keys))
    if not candidates:
        return None
    return candidates[take % len(candidates)]
