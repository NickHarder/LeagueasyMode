"""League's own settings that the overlay follows: where the minimap is, and how big.

League keeps its game settings in `game.cfg`, an INI file, in its `Config` folder. The `[HUD]`
section's `MinimapScale` is the minimap's size slider and `FlipMiniMap` puts it on the left. The
overlay draws its minimap layer where League's minimap is, so it reads both; a file it cannot read
leaves the defaults, a minimap of scale 1 on the right.
"""

import configparser
import logging
from pathlib import Path
from typing import Final

from leagueasymode.overlay_state import MinimapLayout

DEFAULT_GAME_CONFIG_PATH: Final = Path(
    "/Applications/League of Legends.app/Contents/LoL/Config/game.cfg"
)
HUD_SECTION: Final = "HUD"
MINIMAP_SCALE_KEY: Final = "MinimapScale"
FLIP_MINIMAP_KEY: Final = "FlipMiniMap"
DEFAULT_MINIMAP_LAYOUT: Final = MinimapLayout(scale=1.0, is_flipped=False)

logger = logging.getLogger(__name__)


def read_minimap_layout(game_config_path: Path) -> MinimapLayout:
    """Return where League draws its minimap, from its settings file.

    Args:
        game_config_path: League's `game.cfg`.

    Returns:
        The layout; the default for a file that is missing or cannot be read, and for each value
        that is missing or cannot be read.
    """
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]  # League's keys are case-sensitive
    try:
        parser.read_string(game_config_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, configparser.Error):
        logger.info(
            "League's settings file was not read; the minimap layer takes its default place"
        )
        return DEFAULT_MINIMAP_LAYOUT
    hud = parser[HUD_SECTION] if parser.has_section(HUD_SECTION) else {}
    return MinimapLayout(
        scale=_float_or(hud.get(MINIMAP_SCALE_KEY), DEFAULT_MINIMAP_LAYOUT.scale),
        is_flipped=hud.get(FLIP_MINIMAP_KEY, "0").strip() == "1",
    )


def _float_or(value: str | None, default: float) -> float:
    """Return a setting as a number, or a default when it is missing or not a number.

    Args:
        value: The setting's text.
        default: The default.

    Returns:
        The number.
    """
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default
