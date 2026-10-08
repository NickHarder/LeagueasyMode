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
# Set when the server shuts down, so that open streams end at once instead of at their next
# keep-alive, which would hold the shutdown up for as long as that.
SHUTTING_DOWN_KEY: Final = web.AppKey("shutting_down", asyncio.Event)
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
    shutting_down = asyncio.Event()
    application[SHUTTING_DOWN_KEY] = shutting_down

    async def announce_shutdown(_application: web.Application) -> None:
        shutting_down.set()

    application.on_shutdown.append(announce_shutdown)

    async def state(_request: web.Request) -> web.Response:
        return web.json_response(text=engine.current_state.model_dump_json())

    async def events(request: web.Request) -> web.StreamResponse:
        return await _stream_states(request, engine, shutting_down)

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


async def _stream_states(
    request: web.Request, engine: OverlayEngine, shutting_down: asyncio.Event
) -> web.StreamResponse:
    """Send the current state, then each new one, as server-sent events until the reader leaves.

    Args:
        request: The request.
        engine: The engine.
        shutting_down: Set when the server shuts down, which ends the stream at once.

    Returns:
        The stream, once the reader has gone or the server is shutting down.
    """
    response = web.StreamResponse(
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}
    )
    await response.prepare(request)
    updates = engine.subscribe()
    try:
        await response.write(_event_bytes(engine.current_state))
        while not shutting_down.is_set():
            new_state = await _next_state_or_none(updates, shutting_down)
            if new_state is not None:
                await response.write(_event_bytes(new_state))
            elif not shutting_down.is_set():
                await response.write(b": keepalive\n\n")
        return response
    except ConnectionResetError:
        return response
    finally:
        engine.unsubscribe(updates)


async def _next_state_or_none(
    updates: asyncio.Queue[OverlayState], shutting_down: asyncio.Event
) -> OverlayState | None:
    """Wait for the next state, the shutdown, or the keep-alive interval, whichever comes first.

    Args:
        updates: The subscriber's queue.
        shutting_down: Set when the server shuts down.

    Returns:
        The next state, or None when the shutdown or the keep-alive interval came first.
    """
    next_state_task = asyncio.ensure_future(updates.get())
    shutdown_task = asyncio.ensure_future(shutting_down.wait())
    finished_tasks, pending_tasks = await asyncio.wait(
        {next_state_task, shutdown_task},
        timeout=KEEPALIVE_INTERVAL_SECONDS,
        return_when=asyncio.FIRST_COMPLETED,
    )
    for pending_task in pending_tasks:
        pending_task.cancel()
    if next_state_task in finished_tasks:
        return next_state_task.result()
    return None


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
