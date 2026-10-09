"""Moving the widgets (phase 8.3): where the player put each one, kept between runs."""

import asyncio
from pathlib import Path

import aiohttp
from pydantic import JsonValue, ValidationError

from leagueasymode.config import Settings
from leagueasymode.engine import OverlayEngine
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import LAYOUT_REQUEST_VALUE, create_overlay_application
from leagueasymode.overlay_state import OverlayLayout, WidgetOffset
from leagueasymode.preferences import load_layout, save_layout
from local_servers import serve, unused_local_url


def moved_enemy_strip() -> OverlayLayout:
    return OverlayLayout(offsets={"enemy_strip": WidgetOffset(x_share=-0.25, y_share=0.1)})


def test_without_a_file_every_widget_is_in_its_usual_place(tmp_path: Path) -> None:
    assert load_layout(tmp_path / "layout.json") == OverlayLayout()


def test_a_layout_is_kept_and_read_back(tmp_path: Path) -> None:
    layout_path = tmp_path / "app" / "layout.json"
    save_layout(layout_path, moved_enemy_strip())
    assert load_layout(layout_path) == moved_enemy_strip()


def test_a_file_that_cannot_be_read_puts_every_widget_back(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.json"
    layout_path.write_text('{"offsets": {"minimap": {"x_share": 0.1, "y_share": 0.1}}}')
    assert load_layout(layout_path) == OverlayLayout()


def test_a_widget_moves_at_most_a_whole_screen() -> None:
    for out_of_reach in (1.5, -1.01):
        try:
            WidgetOffset(x_share=out_of_reach, y_share=0.0)
        except ValidationError:
            continue
        raise AssertionError(f"{out_of_reach} was accepted")


async def put_layout(
    session: aiohttp.ClientSession, overlay_url: str, body: JsonValue, *, with_header: bool
) -> int:
    headers = {"X-LeagueasyMode-Request": LAYOUT_REQUEST_VALUE} if with_header else {}
    async with session.put(overlay_url + "/layout", json=body, headers=headers) as response:
        return response.status


async def test_a_move_reaches_the_overlay_and_is_kept(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.json"
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None),
            poll_interval_seconds=1,
            layout=load_layout(layout_path),
        )
        updates = engine.subscribe()
        application = create_overlay_application(engine, layout_path=layout_path)
        async with serve(application) as overlay_url:
            refused = await put_layout(
                session, overlay_url, moved_enemy_strip().model_dump(), with_header=False
            )
            not_a_layout = await put_layout(
                session,
                overlay_url,
                {"offsets": {"minimap": {"x_share": 0.1, "y_share": 0.1}}},
                with_header=True,
            )
            accepted = await put_layout(
                session, overlay_url, moved_enemy_strip().model_dump(), with_header=True
            )
            published = await asyncio.wait_for(updates.get(), timeout=1)
            async with session.get(overlay_url + "/layout") as response:
                served = OverlayLayout.model_validate(await response.json())
    assert (refused, not_a_layout, accepted) == (403, 400, 200)
    assert published.layout == moved_enemy_strip()
    assert served == moved_enemy_strip()
    assert load_layout(layout_path) == moved_enemy_strip()


def test_the_layout_file_is_a_setting(tmp_path: Path) -> None:
    layout_path = tmp_path / "elsewhere" / "layout.json"
    assert Settings(layout=layout_path).layout == layout_path
