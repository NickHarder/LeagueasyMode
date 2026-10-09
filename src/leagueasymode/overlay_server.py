"""The overlay's local web server: the widgets' page, and the engine's state as JSON and a stream.

It listens on 127.0.0.1 only. A request naming any host other than 127.0.0.1 or localhost is
refused, so that a web page elsewhere cannot reach it by pointing its own domain name at
127.0.0.1 (DNS rebinding).
"""

import asyncio
import dataclasses
from collections.abc import Awaitable, Callable
from importlib import resources
from pathlib import Path
from typing import Final, Literal

from aiohttp import web
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from leagueasymode.accuracy_history import read_accuracy_history
from leagueasymode.engine import OverlayEngine
from leagueasymode.overlay_state import OverlayLayout, OverlayPreferences, OverlayState
from leagueasymode.preferences import save_layout, save_preferences

ALLOWED_HOST_NAMES: Final = frozenset({"127.0.0.1", "localhost"})
# The header the macOS app sends with a mark.
MARK_REQUEST_HEADER: Final = "X-LeagueasyMode-Request"
MARK_REQUEST_VALUE: Final = "mark"
# The same header's value for a change of preferences, from the settings page.
PREFERENCES_REQUEST_VALUE: Final = "preferences"
# And for a move of the widgets, from the overlay page in edit mode.
LAYOUT_REQUEST_VALUE: Final = "layout"
ENEMY_SLOT_COUNT: Final = 5


class MarkRequest(BaseModel):
    """A mark from the macOS app: an enemy by their place in role order, and the spell they used."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enemy_slot: int = Field(ge=1, le=ENEMY_SLOT_COUNT)
    spell: Literal["flash", "summoner", "ultimate"]


# Set when the server shuts down, so that open streams end at once instead of at their next
# keep-alive, which would hold the shutdown up for as long as that.
SHUTTING_DOWN_KEY: Final = web.AppKey("shutting_down", asyncio.Event)
KEEPALIVE_INTERVAL_SECONDS: Final = 15.0
WEB_ASSET_PACKAGE: Final = "leagueasymode.overlay_web"
WEB_ASSETS: Final = {
    "/": ("index.html", "text/html"),
    "/overlay.js": ("overlay.js", "text/javascript"),
    "/state.js": ("state.js", "text/javascript"),
    "/layout.js": ("layout.js", "text/javascript"),
    "/speech.js": ("speech.js", "text/javascript"),
    "/overlay.css": ("overlay.css", "text/css"),
    "/summary.html": ("summary.html", "text/html"),
    "/summary.js": ("summary.js", "text/javascript"),
    "/summary_state.js": ("summary_state.js", "text/javascript"),
    "/summary.css": ("summary.css", "text/css"),
    "/settings.html": ("settings.html", "text/html"),
    "/settings.js": ("settings.js", "text/javascript"),
    "/status.html": ("status.html", "text/html"),
    "/status.js": ("status.js", "text/javascript"),
    "/status_state.js": ("status_state.js", "text/javascript"),
}

type Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def create_overlay_application(
    engine: OverlayEngine,
    *,
    summary_path: Path | None = None,
    history_path: Path | None = None,
    preferences_path: Path | None = None,
    layout_path: Path | None = None,
) -> web.Application:
    """Return the overlay's web application.

    Args:
        engine: The engine whose state is served.
        summary_path: The last game's summary, served at `/summary`; None to serve none.
        history_path: The accuracy history, served at `/history`; None to serve none.
        preferences_path: Where a change of preferences is kept; None to keep it for this run.
        layout_path: Where a move of the widgets is kept; None to keep it for this run.

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

    async def mark(request: web.Request) -> web.Response:
        # A page elsewhere cannot send this header without a preflight this server never
        # answers, so only the macOS app, or another program on this machine, can mark.
        if request.headers.get(MARK_REQUEST_HEADER) != MARK_REQUEST_VALUE:
            return web.json_response({"message": "marks come from the app"}, status=403)
        try:
            mark_request = MarkRequest.model_validate_json(await request.read())
        except ValidationError:
            return web.json_response({"message": "not a mark"}, status=400)
        timer = engine.mark_cooldown(mark_request.enemy_slot, mark_request.spell)
        if timer is None:
            return web.json_response(
                {"message": "no game, no such enemy, or no cooldowns for this patch yet"},
                status=409,
            )
        return web.json_response(text=timer.model_dump_json())

    async def summary(_request: web.Request) -> web.Response:
        summary_text = await asyncio.to_thread(_text_or_none, summary_path)
        if summary_text is None:
            return web.json_response({"message": "no game recorded yet"}, status=404)
        return web.json_response(text=summary_text)

    async def history(_request: web.Request) -> web.Response:
        games = (
            await asyncio.to_thread(read_accuracy_history, history_path)
            if history_path is not None
            else []
        )
        return web.json_response({"games": [dataclasses.asdict(game) for game in games]})

    async def status(_request: web.Request) -> web.Response:
        return web.json_response(text=engine.status.report().model_dump_json())

    application.router.add_get("/status", status)
    _add_the_players_choices(
        application, engine, preferences_path=preferences_path, layout_path=layout_path
    )
    application.router.add_get("/summary", summary)
    application.router.add_get("/history", history)
    application.router.add_get("/state", state)
    application.router.add_get("/events", events)
    application.router.add_post("/marks", mark)
    for route_path, (file_name, content_type) in WEB_ASSETS.items():
        application.router.add_get(route_path, _asset_handler(file_name, content_type))
    return application


def _add_the_players_choices(
    application: web.Application,
    engine: OverlayEngine,
    *,
    preferences_path: Path | None,
    layout_path: Path | None,
) -> None:
    """Serve and take the player's choices: what the overlay shows, and where its widgets are.

    Args:
        application: The overlay's web application.
        engine: The engine, which sends the choices with its state.
        preferences_path: Where a change of preferences is kept; None to keep it for this run.
        layout_path: Where a move of the widgets is kept; None to keep it for this run.
    """

    async def preferences(_request: web.Request) -> web.Response:
        return web.json_response(text=engine.preferences.model_dump_json())

    async def change_preferences(request: web.Request) -> web.Response:
        # As with marks: a page elsewhere cannot send this header without a preflight this
        # server never answers, so only the settings page, served from here, can change them.
        if request.headers.get(MARK_REQUEST_HEADER) != PREFERENCES_REQUEST_VALUE:
            return web.json_response(
                {"message": "preferences come from the settings page"}, status=403
            )
        try:
            chosen = OverlayPreferences.model_validate_json(await request.read())
        except ValidationError:
            return web.json_response({"message": "not preferences"}, status=400)
        engine.set_preferences(chosen)
        if preferences_path is not None:
            await asyncio.to_thread(save_preferences, preferences_path, chosen)
        return web.json_response(text=chosen.model_dump_json())

    async def layout(_request: web.Request) -> web.Response:
        return web.json_response(text=engine.layout.model_dump_json())

    async def change_layout(request: web.Request) -> web.Response:
        # As with preferences: only the overlay page, served from here, can send this header.
        if request.headers.get(MARK_REQUEST_HEADER) != LAYOUT_REQUEST_VALUE:
            return web.json_response({"message": "a layout comes from the overlay"}, status=403)
        try:
            moved = OverlayLayout.model_validate_json(await request.read())
        except ValidationError:
            return web.json_response({"message": "not a layout"}, status=400)
        engine.set_layout(moved)
        if layout_path is not None:
            await asyncio.to_thread(save_layout, layout_path, moved)
        return web.json_response(text=moved.model_dump_json())

    application.router.add_get("/layout", layout)
    application.router.add_put("/layout", change_layout)
    application.router.add_get("/preferences", preferences)
    application.router.add_put("/preferences", change_preferences)


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


def _text_or_none(file_path: Path | None) -> str | None:
    """Return a file's text.

    Args:
        file_path: The file; None for none.

    Returns:
        The text; None when there is no file.
    """
    if file_path is None:
        return None
    try:
        return file_path.read_text()
    except FileNotFoundError:
        return None


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
