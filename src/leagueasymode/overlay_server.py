"""The overlay's local web server: the widgets' page, and the engine's state as JSON and a stream.

It listens on 127.0.0.1 only. A request naming any host other than 127.0.0.1 or localhost is
refused, so that a web page elsewhere cannot reach it by pointing its own domain name at
127.0.0.1 (DNS rebinding).
"""

import asyncio
from collections.abc import Awaitable, Callable
from importlib import resources
from typing import Final

from aiohttp import web

from leagueasymode.engine import OverlayEngine
from leagueasymode.overlay_state import OverlayState

ALLOWED_HOST_NAMES: Final = frozenset({"127.0.0.1", "localhost"})
KEEPALIVE_INTERVAL_SECONDS: Final = 15.0
WEB_ASSET_PACKAGE: Final = "leagueasymode.overlay_web"
WEB_ASSETS: Final = {
    "/": ("index.html", "text/html"),
    "/overlay.js": ("overlay.js", "text/javascript"),
    "/state.js": ("state.js", "text/javascript"),
    "/overlay.css": ("overlay.css", "text/css"),
}

type Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def create_overlay_application(engine: OverlayEngine) -> web.Application:
    """Return the overlay's web application.

    Args:
        engine: The engine whose state is served.

    Returns:
        The application.
    """
    application = web.Application(middlewares=[_refuse_other_hosts])

    async def state(_request: web.Request) -> web.Response:
        return web.json_response(text=engine.current_state.model_dump_json())

    async def events(request: web.Request) -> web.StreamResponse:
        return await _stream_states(request, engine)

    application.router.add_get("/state", state)
    application.router.add_get("/events", events)
    for route_path, (file_name, content_type) in WEB_ASSETS.items():
        application.router.add_get(route_path, _asset_handler(file_name, content_type))
    return application


@web.middleware
async def _refuse_other_hosts(request: web.Request, handler: Handler) -> web.StreamResponse:
    """Refuse a request whose Host names anything but this machine.

    Args:
        request: The request.
        handler: The route's handler.

    Returns:
        The handler's response, or 403.
    """
    host_name = (request.host or "").rpartition(":")[0] or request.host
    if host_name not in ALLOWED_HOST_NAMES:
        return web.json_response({"message": "this server answers only 127.0.0.1"}, status=403)
    return await handler(request)


async def _stream_states(request: web.Request, engine: OverlayEngine) -> web.StreamResponse:
    """Send the current state, then each new one, as server-sent events until the reader leaves.

    Args:
        request: The request.
        engine: The engine.

    Returns:
        The stream, once the reader has gone.
    """
    response = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}
    )
    await response.prepare(request)
    updates = engine.subscribe()
    try:
        await response.write(_event_bytes(engine.current_state))
        while True:
            try:
                new_state = await asyncio.wait_for(
                    updates.get(), timeout=KEEPALIVE_INTERVAL_SECONDS
                )
            except TimeoutError:
                await response.write(b": keepalive\n\n")
                continue
            await response.write(_event_bytes(new_state))
    except ConnectionResetError:
        return response
    finally:
        engine.unsubscribe(updates)


def _event_bytes(state: OverlayState) -> bytes:
    """Return one server-sent event carrying a state.

    Args:
        state: The state.

    Returns:
        The event's bytes.
    """
    return b"data: " + state.model_dump_json().encode() + b"\n\n"


def _asset_handler(file_name: str, content_type: str) -> Handler:
    """Return a handler that serves one of the widgets' files from the package.

    Args:
        file_name: The file, in `leagueasymode/overlay_web/`.
        content_type: Its media type.

    Returns:
        The handler.
    """

    async def asset(_request: web.Request) -> web.Response:
        asset_bytes = await asyncio.to_thread(
            resources.files(WEB_ASSET_PACKAGE).joinpath(file_name).read_bytes
        )
        return web.Response(
            body=asset_bytes, content_type=content_type, headers={"Cache-Control": "no-cache"}
        )

    return asset
