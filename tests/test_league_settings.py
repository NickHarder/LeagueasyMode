from pathlib import Path
from typing import Final

from game_payloads import all_game_data
from leagueasymode.engine import compute_overlay_state
from leagueasymode.league_settings import DEFAULT_MINIMAP_LAYOUT, read_minimap_layout
from leagueasymode.overlay_state import MinimapLayout

GAME_CONFIG: Final = """[General]
WindowMode=2
Width=1920
Height=1080

[HUD]
ShowTimestamps=1
MinimapScale=1.5000
FlipMiniMap=1
"""


def test_the_minimap_scale_and_side_come_from_leagues_settings(tmp_path: Path) -> None:
    game_config = tmp_path / "game.cfg"
    game_config.write_text(GAME_CONFIG)
    assert read_minimap_layout(game_config) == MinimapLayout(scale=1.5, is_flipped=True)


def test_a_missing_settings_file_leaves_the_default(tmp_path: Path) -> None:
    assert read_minimap_layout(tmp_path / "missing.cfg") == DEFAULT_MINIMAP_LAYOUT


def test_values_that_cannot_be_read_leave_their_defaults(tmp_path: Path) -> None:
    game_config = tmp_path / "game.cfg"
    game_config.write_text("[HUD]\nMinimapScale=big\nMinimapScale=also big\n")
    assert read_minimap_layout(game_config) == DEFAULT_MINIMAP_LAYOUT


def test_a_file_that_is_not_ini_leaves_the_default(tmp_path: Path) -> None:
    game_config = tmp_path / "game.cfg"
    game_config.write_text("MinimapScale=2\n")
    assert read_minimap_layout(game_config) == DEFAULT_MINIMAP_LAYOUT


def test_the_overlay_tells_the_widgets_where_the_minimap_is() -> None:
    layout = MinimapLayout(scale=0.8, is_flipped=True)
    state = compute_overlay_state(all_game_data(600.0), minimap=layout)
    assert state.minimap == layout
