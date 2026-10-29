"""The safety floor: what no line says at any spice level.

Only gameplay is flamed. A line never tells anyone to hurt themselves, never brings in their family,
never mocks how they look, and never uses who they are as an insult. Riot penalises the player who
pastes such a line.

Matching is on words after normalising: case is ignored, common letter swaps are undone ("m0m" is
"mom"), and single letters spaced apart are joined ("k y s" is "kys"), but a term inside a longer
word does not match ("skyscraper" is not "kys").

The approved lines come from templates the owner signed off, so this list guards against a
template slip. A line a model writes (Claude's take, phase 11.8) must also pass an established
moderation list: LDNOOBW's English list, kept as the SHA-256 of each normalised term in
`moderation_terms.sha256` (`scripts/make_moderation_list.py`), so no term is spelled out here.
"""

import functools
import hashlib
import re
from importlib import resources
from typing import Final

LETTER_SWAPS: Final = str.maketrans(
    {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)
WORD_PATTERN: Final = re.compile(r"[a-z]+")
SELF_HARM_TERMS: Final = (
    "kys",
    "kill yourself",
    "kill urself",
    "kill ur self",
    "neck yourself",
    "hang yourself",
    "end yourself",
    "end your life",
    "die irl",
    "go die",
    "uninstall life",
)
FAMILY_TERMS: Final = (
    "your mom",
    "ur mom",
    "your mother",
    "ur mother",
    "your dad",
    "ur dad",
    "your father",
    "your family",
    "your parents",
    "your sister",
)
LOOKS_TERMS: Final = ("ugly", "fat", "fatty", "fatso")
IDENTITY_TERMS: Final = (
    "retard",
    "retarded",
    "autist",
    "autistic",
    "cancer",
    "aids",
    "incel",
    "virgin",
)
FLOOR_TERMS: Final = (*SELF_HARM_TERMS, *FAMILY_TERMS, *LOOKS_TERMS, *IDENTITY_TERMS)
# The longest term on the moderation list, in words; every run of words up to this long is checked.
MODERATION_LONGEST_TERM_WORDS: Final = 6


def normalized_words(text: str) -> list[str]:
    """Return a text's words, lowercased, with letter swaps undone and spaced letters joined.

    Args:
        text: Any text.

    Returns:
        The words; a run of single letters ("k y s") becomes one word ("kys").
    """
    words = WORD_PATTERN.findall(text.lower().translate(LETTER_SWAPS))
    joined_words: list[str] = []
    letter_run: list[str] = []
    for word in [*words, ""]:
        if len(word) == 1:
            letter_run.append(word)
            continue
        if letter_run:
            joined_words.append("".join(letter_run))
            letter_run.clear()
        if word:
            joined_words.append(word)
    return joined_words


def floor_problems(text: str) -> list[str]:
    """Return each floor term a text holds; an empty list means it may be shown.

    Args:
        text: A line, or any text the site would show or offer for chat.

    Returns:
        A description of each term found.
    """
    padded_text = " " + " ".join(normalized_words(text)) + " "
    return [
        f"the line holds {term!r}, which the safety floor forbids"
        for term in FLOOR_TERMS
        if " " + " ".join(normalized_words(term)) + " " in padded_text
    ]


def moderation_key(term: str) -> str:
    """Return a term as the moderation list keeps it: its normalised words, joined by spaces.

    Args:
        term: A term, or a run of a line's words.

    Returns:
        The key; empty for a term with no words.
    """
    return " ".join(normalized_words(term))


@functools.cache
def _moderation_hashes() -> frozenset[str]:
    """Return the moderation list's hashes, read once.

    Returns:
        The SHA-256 of each normalised term.
    """
    list_text = resources.files(__package__).joinpath("moderation_terms.sha256").read_text("utf-8")
    return frozenset(
        line.strip() for line in list_text.splitlines() if line.strip() and not line.startswith("#")
    )


def moderation_problems(text: str) -> list[str]:
    """Return a problem when a text holds a term on the moderation list; empty when it holds none.

    Every run of up to `MODERATION_LONGEST_TERM_WORDS` normalised words is checked, so a term of
    several words matches as a whole and a term inside a longer word does not.

    Args:
        text: A line a model wrote.

    Returns:
        One description, which does not repeat the term, or none.
    """
    words = normalized_words(text)
    hashes = _moderation_hashes()
    runs = (
        " ".join(words[start : start + length])
        for length in range(1, MODERATION_LONGEST_TERM_WORDS + 1)
        for start in range(len(words) - length + 1)
    )
    if any(hashlib.sha256(run.encode()).hexdigest() in hashes for run in runs):
        return ["the line holds a term on the moderation list"]
    return []
