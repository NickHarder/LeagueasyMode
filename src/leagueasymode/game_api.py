"""The game's own API, on 127.0.0.1:2999 while a game runs: the whole scoreboard in one call."""

import logging
import ssl
from typing import Final

import aiohttp
from pydantic import JsonValue, TypeAdapter, ValidationError

DEFAULT_GAME_API_BASE_URL: Final = "https://127.0.0.1:2999"
ALL_GAME_DATA_PATH: Final = "/liveclientdata/allgamedata"
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 1.0
JSON_VALUE_ADAPTER: Final = TypeAdapter[JsonValue](JsonValue)

logger = logging.getLogger(__name__)


class GameApiClient:
    """Asks the game for its state. No game running, or a game still loading, is no answer."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        tls_context: ssl.SSLContext | None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """Keep what every request needs.

        Args:
            session: The HTTP session, which keeps the connection open between requests.
            base_url: The game's address, `https://127.0.0.1:2999`, or a replay's.
            tls_context: The context for HTTPS (`riot_tls.create_riot_tls_context`); None for a
                replay served over plain HTTP.
            request_timeout_seconds: How long one request may take before it counts as no answer.
        """
        self.session: Final = session
        self.all_game_data_url: Final = base_url.rstrip("/") + ALL_GAME_DATA_PATH
        self.tls_context: Final = tls_context
        self.request_timeout: Final = aiohttp.ClientTimeout(total=request_timeout_seconds)

    async def fetch_all_game_data(self) -> JsonValue | None:
        """Return the game's whole state, or None when there is no game to answer.

        Returns:
            The answer of `/liveclientdata/allgamedata`, or None when nothing listens, the game is
            loading, the request times out or the answer is not JSON.
        """
        try:
            async with self.session.get(
                self.all_game_data_url,
                ssl=self.tls_context if self.tls_context is not None else True,
                timeout=self.request_timeout,
            ) as response:
                if response.status != 200:
                    logger.debug("game API answered %d", response.status)
                    return None
                response_bytes = await response.read()
        except (aiohttp.ClientError, TimeoutError, ssl.SSLError) as error:
            logger.debug("game API did not answer: %s", type(error).__name__)
            return None
        try:
            return JSON_VALUE_ADAPTER.validate_json(response_bytes)
        except ValidationError:
            logger.warning("game API answered with something that is not JSON")
            return None
