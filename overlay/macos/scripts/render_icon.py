"""Renders the app icon's drawing, AppIcon.svg, to AppIcon.png at 1024 by 1024, in Chromium.

    uv run python overlay/macos/scripts/render_icon.py

Run after a change to the drawing; both files are kept. build_app.sh makes the app's
AppIcon.icns from the PNG with macOS's own sips and iconutil, so the build needs no renderer.
"""

import asyncio
import os
from pathlib import Path
from typing import Final

from playwright.async_api import async_playwright

RESOURCES_DIRECTORY: Final = Path(__file__).resolve().parent.parent / "Resources"
ICON_SIZE_PIXELS: Final = 1024


async def render_icon() -> None:
    """Draw AppIcon.svg on a transparent page and keep it as AppIcon.png."""
    drawing = (RESOURCES_DIRECTORY / "AppIcon.svg").read_text()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        )
        page = await browser.new_page(
            viewport={"width": ICON_SIZE_PIXELS, "height": ICON_SIZE_PIXELS}
        )
        await page.set_content(
            f'<html><body style="margin:0;background:transparent">{drawing}</body></html>'
        )
        await page.screenshot(
            path=str(RESOURCES_DIRECTORY / "AppIcon.png"),
            omit_background=True,
            clip={"x": 0, "y": 0, "width": ICON_SIZE_PIXELS, "height": ICON_SIZE_PIXELS},
        )
        await browser.close()


if __name__ == "__main__":
    asyncio.run(render_icon())
