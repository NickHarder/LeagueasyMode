"""The How to use page: every shortcut the app registers, in Mac and Windows-keyboard names."""

import re
from typing import Final

import aiohttp

from leagueasymode.config import REPOSITORY_ROOT
from leagueasymode.engine import OverlayEngine
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from local_servers import serve, unused_local_url

APP_DELEGATE: Final = REPOSITORY_ROOT / "overlay/macos/Sources/LeagueasyOverlay/AppDelegate.swift"


async def page_text() -> str:
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        async with (
            serve(create_overlay_application(engine)) as url,
            session.get(url + "/how-to-use.html") as response,
        ):
            assert response.status == 200
            assert response.content_type == "text/html"
            return await response.text()


async def test_the_page_names_each_shortcut_for_a_windows_keyboard() -> None:
    text = await page_text()
    for windows_keys in (
        "Ctrl + Alt + Windows + L",
        "Ctrl + Alt + Windows + R",
        "Ctrl + Alt + 1",
        "Ctrl + Alt + 5",
        "Ctrl + Alt + F",
        "Ctrl + Alt + D",
        "Ctrl + Alt + R",
    ):
        assert f"<kbd>{windows_keys}</kbd>" in text


async def test_every_key_the_app_registers_is_on_the_page() -> None:
    # A shortcut added to the app without a line here fails this test.
    text = await page_text()
    registered_keys = set(re.findall(r"kVK_ANSI_(\w)\b", APP_DELEGATE.read_text()))
    assert registered_keys == {"L", "R", "1", "2", "3", "4", "5", "F", "D"}
    shown_keys = set(re.findall(r"<kbd>Ctrl \+ Alt \+ (?:Windows \+ )?(\w)</kbd>", text))
    assert registered_keys - {"2", "3", "4"} <= shown_keys
