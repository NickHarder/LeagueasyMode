"""The player's choices of what the overlay shows (phase 7.1), kept between runs.

The settings page (`/settings.html`) changes them through the overlay's server, which keeps them
in `preferences.json` in the application's directory (`LEAGUEASYMODE_PREFERENCES` moves it) and
sends them to the overlay with its state, so that a change shows at once. A file that is missing
or cannot be read leaves everything showing; a preference added in a later version takes its
default.
"""

import logging
from pathlib import Path

from pydantic import ValidationError

from leagueasymode.overlay_state import OverlayPreferences

logger = logging.getLogger(__name__)


def load_preferences(preferences_path: Path) -> OverlayPreferences:
    """Return the player's preferences.

    Args:
        preferences_path: The preferences file.

    Returns:
        The preferences; the defaults, everything showing, when the file is missing or unreadable.
    """
    try:
        return OverlayPreferences.model_validate_json(preferences_path.read_text())
    except FileNotFoundError:
        return OverlayPreferences()
    except (OSError, ValidationError):
        logger.warning("could not read %s; everything shows", preferences_path)
        return OverlayPreferences()


def save_preferences(preferences_path: Path, preferences: OverlayPreferences) -> None:
    """Keep the player's preferences, replacing the file whole.

    Args:
        preferences_path: The preferences file.
        preferences: The preferences.
    """
    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = preferences_path.with_suffix(".partial")
    partial_path.write_text(preferences.model_dump_json(indent=2) + "\n")
    partial_path.replace(preferences_path)
