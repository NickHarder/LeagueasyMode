"""The League client's local API: patch data, the game's id, and the match timeline after a game.

The client listens on 127.0.0.1 on a port it picks at start, behind HTTP Basic authentication with
a password it also picks at start. Both are in its `lockfile`, and in the arguments of its
`LeagueClientUx` process; this module reads the first that is there.
"""

import asyncio
import base64
import logging
import re
import ssl
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import aiohttp
from pydantic import JsonValue, ValidationError

from leagueasymode.game_api import JSON_VALUE_ADAPTER

# Where the League client writes its lockfile on a Mac, and on Windows for completeness.
DEFAULT_LOCKFILE_PATHS: Final = (
    Path("/Applications/League of Legends.app/Contents/LoL/lockfile"),
    Path("C:/Riot Games/League of Legends/lockfile"),
)
CLIENT_USER_NAME: Final = "riot"
LOCKFILE_FIELD_COUNT: Final = 5
PROCESS_LIST_COMMAND: Final = ("/bin/ps", "-A", "-o", "args=")
APP_PORT_PATTERN: Final = re.compile(r"--app-port=(\d+)")
AUTH_TOKEN_PATTERN: Final = re.compile(r"--remoting-auth-token=([\w-]+)")
CLIENT_PROCESS_NAME: Final = "LeagueClientUx"
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final = 5.0
# The game the client is in: its id and each team's players.
GAMEFLOW_SESSION_PATH: Final = "/lol-gameflow/v1/session"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClientCredentials:
    """Where the League client listens, and the password it expects."""

    port: int
    password: str = field(repr=False)

    @property
    def base_url(self) -> str:
        """The client's address."""
        return f"https://127.0.0.1:{self.port}"


def parse_lockfile(lockfile_text: str) -> ClientCredentials | None:
    """Read the port and the password from a lockfile.

    Args:
        lockfile_text: The lockfile's content: `name:process id:port:password:protocol`.

    Returns:
        The credentials, or None when the text is not a lockfile.
    """
    lockfile_fields = lockfile_text.strip().split(":")
    if len(lockfile_fields) != LOCKFILE_FIELD_COUNT or not lockfile_fields[2].isdigit():
        return None
    return ClientCredentials(port=int(lockfile_fields[2]), password=lockfile_fields[3])


def parse_process_arguments(process_list_text: str) -> ClientCredentials | None:
    """Read the port and the password from the `LeagueClientUx` process's arguments.

    Args:
        process_list_text: The output of `ps -A -o args=`, one process a line.

    Returns:
        The credentials, or None when no client process is listed.
    """
    for process_line in process_list_text.splitlines():
        if CLIENT_PROCESS_NAME not in process_line:
            continue
        port_match = APP_PORT_PATTERN.search(process_line)
        token_match = AUTH_TOKEN_PATTERN.search(process_line)
        if port_match is not None and token_match is not None:
            return ClientCredentials(port=int(port_match.group(1)), password=token_match.group(1))
    return None


async def list_processes() -> str:
    """Return the command line of every running process, one a line.

    Returns:
        The output of `ps -A -o args=`.
    """
    process = await asyncio.create_subprocess_exec(
        *PROCESS_LIST_COMMAND,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    process_output, _ = await process.communicate()
    return process_output.decode(errors="replace")


async def find_client_credentials(
    lockfile_paths: Sequence[Path],
    process_lister: Callable[[], Awaitable[str]] = list_processes,
) -> ClientCredentials | None:
    """Find the running League client's port and password.

    Args:
        lockfile_paths: Where to look for a lockfile, in order.
        process_lister: Lists the running processes, when no lockfile has the credentials.

    Returns:
        The credentials, or None when the client is not running.
    """
    for lockfile_path in lockfile_paths:
        try:
            lockfile_text = await asyncio.to_thread(lockfile_path.read_text, encoding="utf-8")
        except OSError:
            continue
        credentials = parse_lockfile(lockfile_text)
        if credentials is not None:
            return credentials
    try:
        process_list_text = await process_lister()
    except OSError:
        logger.debug("could not list processes to find the League client")
        return None
    return parse_process_arguments(process_list_text)


class SharedAnswers:
    """The client's answers to some questions, shared by everyone who asks them.

    The engine and the recorder both ask about each player in a game; sharing the answers means
    the client, and Riot behind it, is asked once. Only the questions under the given path
    prefixes are shared, and an answer that did not come is not kept, so it is asked again.
    """

    def __init__(self, shared_path_prefixes: tuple[str, ...]) -> None:
        """Keep which questions are shared.

        Args:
            shared_path_prefixes: The paths whose answers are shared start with one of these.
        """
        self.shared_path_prefixes: Final = shared_path_prefixes
        self._answers: Final[dict[str, asyncio.Task[JsonValue | None]]] = {}

    def is_shared(self, path: str) -> bool:
        """Return whether a question's answer is shared.

        Args:
            path: The resource's path.

        Returns:
            Whether it is.
        """
        return path.startswith(self.shared_path_prefixes)

    async def answer(
        self, path: str, ask: Callable[[], Awaitable[JsonValue | None]]
    ) -> JsonValue | None:
        """Return the shared answer to a question, asking only when nobody has yet.

        Two who ask at once wait for the same request.

        Args:
            path: The resource's path.
            ask: Asks the client, when the answer is not known.

        Returns:
            The answer, or None when the client gave none.
        """
        if path not in self._answers:
            self._answers[path] = asyncio.ensure_future(ask())
        answer = await self._answers[path]
        if answer is None:
            self._answers.pop(path, None)
        return answer


class LeagueClient:
    """Asks the League client for one resource at a time. An error is no answer."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        password: str,
        tls_context: ssl.SSLContext | None,
        *,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        shared_answers: SharedAnswers | None = None,
    ) -> None:
        """Keep what every request needs.

        Args:
            session: The HTTP session.
            base_url: The client's address (`ClientCredentials.base_url`).
            password: The client's password.
            tls_context: The context for HTTPS (`riot_tls.create_riot_tls_context`); None for a
                stand-in served over plain HTTP.
            request_timeout_seconds: How long one request may take.
            shared_answers: Answers shared with other clients of the same League client, or None.
        """
        self.session: Final = session
        self.base_url: Final = base_url.rstrip("/")
        encoded_user_and_password = base64.b64encode(f"{CLIENT_USER_NAME}:{password}".encode())
        self.authorization_header: Final = f"Basic {encoded_user_and_password.decode('ascii')}"
        self.tls_context: Final = tls_context
        self.request_timeout: Final = aiohttp.ClientTimeout(total=request_timeout_seconds)
        self.shared_answers: Final = shared_answers

    async def get_json(self, path: str) -> JsonValue | None:
        """Return one resource of the client, or None when it cannot be had.

        Args:
            path: The resource's path, such as `/lol-gameflow/v1/session`.

        Returns:
            The resource, or None on any error status, a timeout or an answer that is not JSON.
        """
        shared_answers = self.shared_answers
        if shared_answers is not None and shared_answers.is_shared(path):
            return await shared_answers.answer(path, lambda: self._ask(path))
        return await self._ask(path)

    async def _ask(self, path: str) -> JsonValue | None:
        """Ask the client for one resource.

        Args:
            path: The resource's path.

        Returns:
            The resource, or None on any error status, a timeout or an answer that is not JSON.
        """
        try:
            async with self.session.get(
                self.base_url + path,
                headers={"Authorization": self.authorization_header},
                ssl=self.tls_context if self.tls_context is not None else True,
                timeout=self.request_timeout,
            ) as response:
                if response.status != 200:
                    logger.debug("League client answered %d for %s", response.status, path)
                    return None
                response_bytes = await response.read()
        except (aiohttp.ClientError, TimeoutError, ssl.SSLError) as error:
            logger.debug("League client did not answer %s: %s", path, type(error).__name__)
            return None
        try:
            return JSON_VALUE_ADAPTER.validate_json(response_bytes)
        except ValidationError:
            logger.warning("League client answered %s with something that is not JSON", path)
            return None


# Finds the running League client and returns a client of its API, or None when it is not running.
type ClientConnector = Callable[[], Awaitable[LeagueClient | None]]
