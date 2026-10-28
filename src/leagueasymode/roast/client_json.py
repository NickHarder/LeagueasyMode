"""Reading the League client's answers as they are, so every value keeps its exact path.

The client's game details and timeline come in an older shape than Riot's web API, and fields come
and go between patches. These readers take whatever is there and never fill in what is not: a
missing or mistyped field reads as None, and gives no exhibit.
"""

from pydantic import JsonValue


def as_object(value: JsonValue | None) -> dict[str, JsonValue] | None:
    """Return a JSON object, or None for anything else.

    Args:
        value: Part of an answer.

    Returns:
        The object, or None.
    """
    return value if isinstance(value, dict) else None


def as_list(value: JsonValue | None) -> list[JsonValue]:
    """Return a JSON array, or an empty list for anything else.

    Args:
        value: Part of an answer.

    Returns:
        The array's items.
    """
    return value if isinstance(value, list) else []


def as_whole_number(value: JsonValue | None) -> int | None:
    """Return a whole number, or None for anything else, a true or false included.

    Args:
        value: Part of an answer.

    Returns:
        The number, or None.
    """
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def as_flag(value: JsonValue | None) -> bool | None:
    """Return a true or false, or None for anything else.

    Args:
        value: Part of an answer.

    Returns:
        The flag, or None.
    """
    return value if isinstance(value, bool) else None


def as_text(value: JsonValue | None) -> str:
    """Return a string, or an empty one for anything else.

    Args:
        value: Part of an answer.

    Returns:
        The text.
    """
    return value if isinstance(value, str) else ""
