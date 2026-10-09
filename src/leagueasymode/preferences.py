"""The player's choices of what the overlay shows (phase 7.1) and where (8.3), kept between runs.

The settings page (`/settings.html`) changes the preferences through the overlay's server, which
keeps them in `preferences.json` in the application's directory (`LEAGUEASYMODE_PREFERENCES` moves
it) and sends them to the overlay with its state, so that a change shows at once. A file that is
missing or cannot be read leaves everything showing; a preference added in a later version takes
its default.

The overlay itself, in edit mode, changes the layout the same way, kept in `layout.json`
(`LEAGUEASYMODE_LAYOUT` moves it); a file that cannot be read puts every widget in its usual place.
"""

import logging
from pathlib import Path

from pydantic import ValidationError

from leagueasymode.overlay_state import OverlayLayout, OverlayPreferences

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
    _write_whole(preferences_path, preferences.model_dump_json(indent=2) + "\n")


def load_layout(layout_path: Path) -> OverlayLayout:
    """Return where the player moved the widgets.

    Args:
        layout_path: The layout file.

    Returns:
        The layout; every widget in its usual place when the file is missing or unreadable.
    """
    try:
        return OverlayLayout.model_validate_json(layout_path.read_text())
    except FileNotFoundError:
        return OverlayLayout()
    except (OSError, ValidationError):
        logger.warning("could not read %s; every widget is in its usual place", layout_path)
        return OverlayLayout()


def save_layout(layout_path: Path, layout: OverlayLayout) -> None:
    """Keep where the player moved the widgets, replacing the file whole.

    Args:
        layout_path: The layout file.
        layout: The layout.
    """
    _write_whole(layout_path, layout.model_dump_json(indent=2) + "\n")


def _write_whole(file_path: Path, file_text: str) -> None:
    """Write a file whole: to a partial file first, then into place.

    Args:
        file_path: The file.
        file_text: Its text.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = file_path.with_suffix(".partial")
    partial_path.write_text(file_text)
    partial_path.replace(file_path)
