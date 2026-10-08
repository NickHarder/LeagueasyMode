"""Small HTTP and HTTPS servers on 127.0.0.1, standing in for the game and the League client."""

import contextlib
import ssl
from collections.abc import AsyncIterator

from aiohttp import web


@contextlib.asynccontextmanager
async def serve(
    application: web.Application, server_tls_context: ssl.SSLContext | None = None
) -> AsyncIterator[str]:
    runner = web.AppRunner(application)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=server_tls_context)
    await site.start()
    host, port = runner.addresses[0][:2]
    scheme = "https" if server_tls_context is not None else "http"
    try:
        yield f"{scheme}://{host}:{port}"
    finally:
        await runner.cleanup()


def unused_local_url() -> str:
    # Port 9 (discard) is never served on a test machine, so a connection there is refused.
    return "http://127.0.0.1:9"
