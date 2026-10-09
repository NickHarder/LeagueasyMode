"""The game's own API, on 127.0.0.1:2999 while a game runs: the whole scoreboard in one call."""

import logging
import ssl
from dataclasses import dataclass
from typing import Final

import aiohttp
from pydantic import JsonValue, TypeAdapter, ValidationError

DEFAULT_GAME_API_BASE_URL: Final = "https://127.0.0.1:2999"
ALL_GAME_DATA_PATH: Final = "/liveclientdata/allgamedata"
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 1.0
JSON_VALUE_ADAPTER: Final = TypeAdapter[JsonValue](JsonValue)
# The game answers this while it loads, and for a moment after it ends.
LOADING_STATUS: Final = 404

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NoAnswer:
    """Why the game's API gave no answer: waiting for a game, or a problem to fix."""

    text: str
    is_problem: bool


def no_answer_of(error: BaseException) -> NoAnswer:
    """Say why a request to the game failed.

    Args:
        error: What the request raised.

    Returns:
        Why there is no answer. A refused certificate names the reason the check gave, since it
        means Riot's root certificate (`riot_tls.py`) does not verify the game's.
    """
    if isinstance(error, ssl.SSLCertVerificationError):
        certificate_error = getattr(error, "certificate_error", error)
        reason = getattr(certificate_error, "verify_message", None) or str(certificate_error)
        return NoAnswer(
            f"The game's certificate was refused ({reason}): Riot's root certificate in "
            "riot_tls.py does not verify it",
            is_problem=True,
        )
    if isinstance(error, (ssl.SSLError, aiohttp.ClientSSLError)):
        return NoAnswer(
            f"The secure connection to the game failed ({type(error).__name__})", is_problem=True
        )
    if isinstance(error, aiohttp.ClientConnectorError):
        return NoAnswer("Nothing answers on the game's port: no game is running", is_problem=False)
    if isinstance(error, TimeoutError):
        return NoAnswer("The game did not answer in time: it may be loading", is_problem=False)
    return NoAnswer(f"The request to the game failed ({type(error).__name__})", is_problem=True)


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
        # Why the last request had no answer; None after an answer.
        self.last_no_answer: NoAnswer | None = None

    async def fetch_all_game_data(self) -> JsonValue | None:
        """Return the game's whole state, or None when there is no game to answer.

        Returns:
            The answer of `/liveclientdata/allgamedata`, or None when nothing listens, the game is
            loading, the request times out or the answer is not JSON; `last_no_answer` then says
            which.
        """
        try:
            async with self.session.get(
                self.all_game_data_url,
                ssl=self.tls_context if self.tls_context is not None else True,
                timeout=self.request_timeout,
            ) as response:
                if response.status != 200:
                    logger.debug("game API answered %d", response.status)
                    self.last_no_answer = (
                        NoAnswer(
                            f"The game is loading, or has ended (it answered {LOADING_STATUS})",
                            is_problem=False,
                        )
                        if response.status == LOADING_STATUS
                        else NoAnswer(f"The game answered HTTP {response.status}", is_problem=True)
                    )
                    return None
                response_bytes = await response.read()
        except (aiohttp.ClientError, TimeoutError, ssl.SSLError) as error:
            logger.debug("game API did not answer: %s", type(error).__name__)
            self.last_no_answer = no_answer_of(error)
            return None
        try:
            game_data = JSON_VALUE_ADAPTER.validate_json(response_bytes)
        except ValidationError:
            logger.warning("game API answered with something that is not JSON")
            self.last_no_answer = NoAnswer(
                "The game answered with something that is not JSON", is_problem=True
            )
            return None
        self.last_no_answer = None
        return game_data
