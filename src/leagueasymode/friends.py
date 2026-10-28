"""The owner's friends (phase 11.5): their Riot IDs, which the settings page changes.

The overlay marks the players in a game whose Riot ID is on the list, from the IDs the game's API
already sends, and after the game the case marks them too. The list is kept in `friends.json` in
the application's directory (`LEAGUEASYMODE_FRIENDS` moves it), apart from the preferences: the
preferences go to the overlay with every state, and these are real people's names, so only the
flag `is_friend` leaves the engine. A file that is missing or cannot be read is an empty list.
"""

import logging
import re
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

logger = logging.getLogger(__name__)

MOST_FRIENDS: Final = 50
# A Riot ID as Riot allows it: a game name of 3 to 16 characters, "#", and a tag of 3 to 5.
RIOT_ID_PATTERN: Final = re.compile(r"[^#]{3,16}#[^#\s]{3,5}")


class FriendsList(BaseModel):
    """The friends' Riot IDs, as the owner wrote them, each once."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    riot_ids: tuple[str, ...] = ()

    @field_validator("riot_ids")
    @classmethod
    def _each_a_riot_id(cls, riot_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Trim each Riot ID, refuse any that is not one, and drop repeats in any case.

        Args:
            riot_ids: The Riot IDs as sent.

        Returns:
            The Riot IDs, trimmed, the first spelling of each kept.

        Raises:
            ValueError: If one is not a Riot ID, or there are more than `MOST_FRIENDS`.
        """
        trimmed_ids = [riot_id.strip() for riot_id in riot_ids]
        refused = [riot_id for riot_id in trimmed_ids if not RIOT_ID_PATTERN.fullmatch(riot_id)]
        if refused:
            message = f"not a Riot ID (name#tag): {', '.join(repr(riot_id) for riot_id in refused)}"
            raise ValueError(message)
        first_spelling_by_key: dict[str, str] = {}
        for riot_id in trimmed_ids:
            first_spelling_by_key.setdefault(riot_id.lower(), riot_id)
        first_spellings = tuple(first_spelling_by_key.values())
        if len(first_spellings) > MOST_FRIENDS:
            message = f"at most {MOST_FRIENDS} friends"
            raise ValueError(message)
        return first_spellings

    @property
    def riot_id_keys(self) -> frozenset[str]:
        """The Riot IDs in lower case, as players are matched against them."""
        return frozenset(riot_id.lower() for riot_id in self.riot_ids)


def load_friends(friends_path: Path) -> FriendsList:
    """Return the friends list.

    Args:
        friends_path: The friends file.

    Returns:
        The list; empty when the file is missing or cannot be read.
    """
    try:
        return FriendsList.model_validate_json(friends_path.read_text())
    except FileNotFoundError:
        return FriendsList()
    except (OSError, ValidationError):
        logger.warning("could not read the friends list; no one is marked as a friend")
        return FriendsList()


def save_friends(friends_path: Path, friends: FriendsList) -> None:
    """Keep the friends list, replacing the file whole.

    Args:
        friends_path: The friends file.
        friends: The list.
    """
    friends_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = friends_path.with_suffix(".partial")
    partial_path.write_text(friends.model_dump_json(indent=2) + "\n")
    partial_path.replace(friends_path)
