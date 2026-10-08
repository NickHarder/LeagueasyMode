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


class LeagueClient:
    """Asks the League client for one resource at a time. An error is no answer."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        password: str,
        tls_context: ssl.SSLContext | None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """Keep what every request needs.

        Args:
            session: The HTTP session.
            base_url: The client's address (`ClientCredentials.base_url`).
            password: The client's password.
            tls_context: The context for HTTPS (`riot_tls.create_riot_tls_context`); None for a
                stand-in served over plain HTTP.
            request_timeout_seconds: How long one request may take.
        """
        self.session: Final = session
        self.base_url: Final = base_url.rstrip("/")
        encoded_user_and_password = base64.b64encode(f"{CLIENT_USER_NAME}:{password}".encode())
        self.authorization_header: Final = f"Basic {encoded_user_and_password.decode('ascii')}"
        self.tls_context: Final = tls_context
        self.request_timeout: Final = aiohttp.ClientTimeout(total=request_timeout_seconds)

    async def get_json(self, path: str) -> JsonValue | None:
        """Return one resource of the client, or None when it cannot be had.

        Args:
            path: The resource's path, such as `/lol-gameflow/v1/session`.

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
