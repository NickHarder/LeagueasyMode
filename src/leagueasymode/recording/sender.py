"""Sending games: each finished recording, anonymized, to a private GitHub repository.

The owner (2026-10-28) wanted the games played with the overlay to reach the estimators' scoring
without a step of theirs. Once a GitHub token is in the Keychain (on a Mac: `security
add-generic-password -s LeagueasyMode-GitHub -a recordings -w`, which asks for the token) or in
`LEAGUEASYMODE_GITHUB_TOKEN`, `leagueasymode run` sends every finished recording not yet sent when
it starts and after each game, and the status page can ask for a round at any time.

Only an anonymized copy is sent (`anonymize.py`), never the recording itself: a game whose copy
would still hold a name is withheld, and never tried again. The copy goes to
`games/<name>-anonymized.jsonl.xz` in the repository `LEAGUEASYMODE_SEND_GAMES_TO` names, through
GitHub's contents API; empty sends nothing. `sent-games.json` beside the recordings lists what was
sent and what was withheld, so each game is sent once. The token is read from the Keychain for
each round, and is never written anywhere, shown or logged.
"""

import asyncio
import base64
import json
import logging
import os
import ssl
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Final

import aiohttp
from pydantic import BaseModel, ConfigDict, Field

from leagueasymode.engine_status import PartState, StatusBoard
from leagueasymode.recording.anonymize import IdentityLeakError, anonymize_recording
from leagueasymode.recording.file_format import COMPRESSED_SUFFIX, PLAIN_SUFFIX

GITHUB_API_BASE_URL: Final = "https://api.github.com"
# The owner's private repository for the games (2026-10-28).
DEFAULT_SEND_GAMES_TO: Final = "NickHarder/LeagueasyMode-recordings"
# The Keychain item the token is kept in.
KEYCHAIN_SERVICE: Final = "LeagueasyMode-GitHub"
SENT_LOG_NAME: Final = "sent-games.json"
ANONYMIZED_SUFFIX: Final = "-anonymized"
GAMES_FOLDER: Final = "games"
REQUEST_TIMEOUT_SECONDS: Final = 120.0
HTTP_CREATED: Final = 201
HTTP_OK: Final = 200
# The contents API's answer when the file is already there.
HTTP_UNPROCESSABLE: Final = 422
HTTP_UNAUTHORIZED: Final = 401

logger = logging.getLogger(__name__)

type CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class SentLog(BaseModel):
    """Which games were sent, and which withheld, by their recording's name without suffix."""

    model_config = ConfigDict(extra="forbid")

    sent: list[str] = Field(default_factory=list)
    withheld: list[str] = Field(default_factory=list)


def _run_command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command and return what it printed, without raising on failure.

    Args:
        arguments: The command and its arguments.

    Returns:
        The finished command.
    """
    return subprocess.run(arguments, capture_output=True, text=True, check=False)  # noqa: S603


def keychain_token(run: CommandRunner = _run_command, platform: str = sys.platform) -> str | None:
    """Return the GitHub token kept in the macOS Keychain.

    Args:
        run: Runs a command; `security`, macOS's own, reads the Keychain.
        platform: The system; only a Mac has the Keychain.

    Returns:
        The token; None off a Mac, or when the Keychain has none.
    """
    if platform != "darwin":
        return None
    finished = run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"])
    token = finished.stdout.strip()
    return token if finished.returncode == 0 and token else None


def recording_stem(recording_path: Path) -> str:
    """Return a recording's name without its suffix.

    Args:
        recording_path: The recording.

    Returns:
        The name.
    """
    return recording_path.name.removesuffix(COMPRESSED_SUFFIX).removesuffix(PLAIN_SUFFIX)


def finished_recordings(directory: Path) -> list[Path]:
    """Return the finished recordings in a folder, oldest name first, anonymized copies left out.

    A recording is finished once it is compressed; one still being written is plain.

    Args:
        directory: The recordings' folder.

    Returns:
        The recordings.
    """
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.glob(f"*{COMPRESSED_SUFFIX}")
        if not recording_stem(path).endswith(ANONYMIZED_SUFFIX)
    )


class SendRefusedError(Exception):
    """GitHub would not take a game; the round stops, and the next one tries again."""


class GameSender:
    """Sends the finished recordings not yet sent, anonymized, one round at a time."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        recordings_directory: Path,
        repository: str,
        *,
        token_source: Callable[[], str | None],
        api_base_url: str = GITHUB_API_BASE_URL,
        tls_context: ssl.SSLContext | None = None,
        status: StatusBoard | None = None,
    ) -> None:
        """Keep where the games are and where they go.

        Args:
            session: The HTTP session.
            recordings_directory: The recordings' folder, where the sent log is kept too.
            repository: `owner/name` of the repository the games go to; empty sends nothing.
            token_source: Returns the GitHub token, or None while there is none.
            api_base_url: GitHub's API, or a stand-in's.
            tls_context: The context for HTTPS, which trusts the system's certificates; None for
                a stand-in over plain HTTP.
            status: Told how sending stands; None to tell nothing.
        """
        self.session: Final = session
        self.recordings_directory: Final = recordings_directory
        self.repository: Final = repository
        self.token_source: Final = token_source
        self.api_base_url: Final = api_base_url.rstrip("/")
        self.tls_context: Final = tls_context
        self.status: Final = status
        self._round_lock: Final = asyncio.Lock()

    async def send_unsent(self) -> None:
        """Send every finished recording not yet sent or withheld, and say how it went.

        Nothing that goes wrong here stops the overlay: it is logged and shown, and the next round
        tries again.
        """
        async with self._round_lock:
            try:
                await self._send_round()
            except Exception as error:
                logger.exception("could not send the games")
                self._note(
                    "problem", f"Could not send games ({type(error).__name__}): sending again later"
                )

    async def _send_round(self) -> None:
        """Send every finished recording not yet sent or withheld, and say how it went."""
        if not self.repository:
            self._note("off", "Off: LEAGUEASYMODE_SEND_GAMES_TO is empty")
            return
        log_path = self.recordings_directory / SENT_LOG_NAME
        sent_log = await asyncio.to_thread(_read_sent_log, log_path)
        done = {*sent_log.sent, *sent_log.withheld}
        unsent = [
            path
            for path in await asyncio.to_thread(finished_recordings, self.recordings_directory)
            if recording_stem(path) not in done
        ]
        token = await asyncio.to_thread(self.token_source)
        if token is None:
            unsent_text = f" ({len(unsent)} not sent)" if unsent else ""
            self._note(
                "waiting", f"No GitHub token in the Keychain: games stay on this Mac{unsent_text}"
            )
            return
        sent_now: list[str] = []
        withheld_now: list[str] = []
        try:
            for recording_path in unsent:
                stem = recording_stem(recording_path)
                is_sent = await self._send_one(recording_path, token)
                (sent_now if is_sent else withheld_now).append(stem)
                (sent_log.sent if is_sent else sent_log.withheld).append(stem)
                await asyncio.to_thread(_write_sent_log, log_path, sent_log)
        except SendRefusedError as refusal:
            self._note("problem", str(refusal))
            return
        self._note_round(len(sent_now), len(withheld_now), len(sent_log.sent))

    async def _send_one(self, recording_path: Path, token: str) -> bool:
        """Send one game's anonymized copy.

        Args:
            recording_path: The recording.
            token: The GitHub token.

        Returns:
            Whether it was sent, or was there already; False when it is withheld.

        Raises:
            SendRefusedError: GitHub, or the way to it, would not take it.
        """
        copy_name = recording_stem(recording_path) + ANONYMIZED_SUFFIX + COMPRESSED_SUFFIX
        with tempfile.TemporaryDirectory(prefix="leagueasymode-send-") as temporary_directory:
            plain_copy_path = Path(temporary_directory) / (copy_name.removesuffix(".xz"))
            try:
                copy_path = await asyncio.to_thread(
                    anonymize_recording, recording_path, plain_copy_path
                )
            except IdentityLeakError:
                logger.warning("withheld %s: a name could not be removed", recording_path.name)
                return False
            except Exception:
                logger.exception("withheld %s: it could not be read", recording_path.name)
                return False
            copy_bytes = await asyncio.to_thread(copy_path.read_bytes)
        await self._put(f"{GAMES_FOLDER}/{copy_name}", copy_bytes, token)
        return True

    async def _put(self, repository_path: str, file_bytes: bytes, token: str) -> None:
        """Put a file in the repository, unless it is there already.

        Args:
            repository_path: Its path in the repository.
            file_bytes: Its content.
            token: The GitHub token.

        Raises:
            SendRefusedError: GitHub, or the way to it, would not take it.
        """
        url = f"{self.api_base_url}/repos/{self.repository}/contents/{repository_path}"
        body = {
            "message": f"Add {repository_path.rpartition('/')[2]}",
            "content": base64.b64encode(file_bytes).decode("ascii"),
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "LeagueasyMode",
        }
        try:
            async with self.session.put(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
                ssl=self.tls_context if self.tls_context is not None else True,
            ) as response:
                answer_status = response.status
        except (aiohttp.ClientError, TimeoutError) as error:
            raise SendRefusedError(
                f"Could not reach GitHub ({type(error).__name__}): sending again later"
            ) from None
        if answer_status in {HTTP_CREATED, HTTP_OK, HTTP_UNPROCESSABLE}:
            return
        if answer_status == HTTP_UNAUTHORIZED:
            raise SendRefusedError(
                f"GitHub refused the token (401): nothing sent to {self.repository}"
            )
        raise SendRefusedError(
            f"GitHub answered {answer_status}: the token cannot write to {self.repository}, "
            "or it does not exist"
        )

    def _note_round(self, sent_count: int, withheld_count: int, total_sent: int) -> None:
        """Say how a round went.

        Args:
            sent_count: Games sent this round.
            withheld_count: Games withheld this round.
            total_sent: Games sent in all.
        """
        if sent_count == 0 and withheld_count == 0:
            self._note("ok", f"Nothing new to send; {total_sent} sent to {self.repository} in all")
            return
        game_word = "game" if sent_count == 1 else "games"
        withheld_text = (
            f"; {withheld_count} withheld: no safe anonymized copy" if withheld_count else ""
        )
        self._note(
            "problem" if withheld_count else "ok",
            f"Sent {sent_count} {game_word} to {self.repository}; {total_sent} sent in all"
            + withheld_text,
        )

    def _note(self, state: PartState, detail: str) -> None:
        """Say how sending stands on the status page, and in the log.

        Args:
            state: The part's state.
            detail: What to say.
        """
        logger.info("sending games: %s", detail)
        if self.status is not None:
            self.status.set_part("sending", state, detail)


def _read_sent_log(log_path: Path) -> SentLog:
    """Return the sent log, empty when there is none or it cannot be read.

    Args:
        log_path: The log.

    Returns:
        The log.
    """
    try:
        return SentLog.model_validate_json(log_path.read_text())
    except (OSError, ValueError):
        return SentLog()


def _write_sent_log(log_path: Path, sent_log: SentLog) -> None:
    """Write the sent log, whole or not at all.

    Args:
        log_path: The log.
        sent_log: What it holds.
    """
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=log_path.parent, prefix=".sent-games-", suffix=".json"
    )
    with os.fdopen(file_descriptor, "w") as temporary_file:
        temporary_file.write(json.dumps(sent_log.model_dump()) + "\n")
    Path(temporary_name).replace(log_path)
