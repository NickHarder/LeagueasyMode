"""Sending games: each finished recording, anonymized, to a private GitHub repository."""

import asyncio
import base64
import json
import lzma
import os
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import aiohttp
from aiohttp import web

from leagueasymode.engine import OverlayEngine
from leagueasymode.engine_status import StatusBoard
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from leagueasymode.recording.sender import (
    SENT_LOG_NAME,
    GameSender,
    keychain_token,
)
from local_servers import serve, unused_local_url
from test_anonymize import identity_strings, write_source_recording

TOKEN: Final = "github-token-for-tests"  # noqa: S105 (a stand-in, not a secret)
REPOSITORY: Final = "owner/games"


class FakeGitHub:
    """A stand-in for GitHub's contents API: what was put where, and how to answer."""

    def __init__(self, *, refused: bool = False, already_there: frozenset[str] = frozenset()):
        self.refused = refused
        self.already_there = already_there
        self.puts: dict[str, bytes] = {}
        self.authorizations: list[str] = []

    def application(self) -> web.Application:
        application = web.Application()

        async def put_contents(request: web.Request) -> web.Response:
            self.authorizations.append(request.headers.get("Authorization", ""))
            if self.refused:
                return web.json_response({"message": "Bad credentials"}, status=401)
            path = request.match_info["path"]
            if path in self.already_there:
                return web.json_response({"message": "sha wasn't supplied"}, status=422)
            body = await request.json()
            self.puts[path] = base64.b64decode(body["content"])
            return web.json_response({"content": {"path": path}}, status=201)

        application.router.add_put("/repos/owner/games/contents/{path:.*}", put_contents)
        return application


def write_games(directory: Path, names: Sequence[str]) -> list[Path]:
    """Finished recordings under the given names, as the recorder leaves them."""
    directory.mkdir(parents=True, exist_ok=True)
    games = []
    for name in names:
        source_directory = directory.parent / "sources" / name
        source_directory.mkdir(parents=True)
        written = write_source_recording(source_directory)
        games.append(written.rename(directory / f"{name}.jsonl.xz"))
    return games


async def send_with(
    github: FakeGitHub,
    recordings: Path,
    token: str | None,
    board: StatusBoard,
    *,
    build: str = "0.1.0 (build 1, abc1234)",
) -> None:
    async with serve(github.application()) as github_url, aiohttp.ClientSession() as session:
        sender = GameSender(
            session,
            recordings,
            REPOSITORY,
            token_source=lambda: token,
            api_base_url=github_url,
            status=board,
            build=build,
        )
        await sender.send_unsent()


def sending_part(board: StatusBoard) -> tuple[str, str]:
    part = next(part for part in board.report().parts if part.key == "sending")
    return part.state, part.detail


async def test_each_finished_game_is_sent_once_and_only_anonymized(tmp_path: Path) -> None:
    recordings = tmp_path / "recordings"
    write_games(recordings, ["2026-10-27-game-1", "2026-10-27-game-2"])
    # An anonymized copy is never sent again, nor a game still being written.
    (recordings / "2026-10-27-game-1-anonymized.jsonl.xz").write_bytes(b"")
    (recordings / "2026-10-28-game-3.jsonl").write_text("{}\n")
    github = FakeGitHub()
    board = StatusBoard(home_directory=tmp_path)
    await send_with(github, recordings, TOKEN, board)
    assert set(github.puts) == {
        "games/2026-10-27-game-1-anonymized.jsonl.xz",
        "games/2026-10-27-game-2-anonymized.jsonl.xz",
    }
    assert github.authorizations == [f"Bearer {TOKEN}"] * 2
    for sent_bytes in github.puts.values():
        sent_text = lzma.decompress(sent_bytes).decode("utf-8")
        assert not [identity for identity in identity_strings() if identity in sent_text]
    assert sending_part(board) == ("ok", f"Sent 2 games to {REPOSITORY}; 2 sent in all")
    sent_log = json.loads((recordings / SENT_LOG_NAME).read_text())
    assert sorted(sent_log["sent"]) == ["2026-10-27-game-1", "2026-10-27-game-2"]
    # The next time, nothing new: nothing is asked of GitHub, and no copy is left behind.
    github.puts.clear()
    await send_with(github, recordings, TOKEN, board)
    assert github.puts == {}
    assert sending_part(board) == ("ok", f"Nothing new to send; 2 sent to {REPOSITORY} in all")
    assert sorted(path.name for path in recordings.iterdir()) == sorted(
        [
            "2026-10-27-game-1.jsonl.xz",
            "2026-10-27-game-1-anonymized.jsonl.xz",
            "2026-10-27-game-2.jsonl.xz",
            "2026-10-28-game-3.jsonl",
            SENT_LOG_NAME,
        ]
    )


async def test_a_game_already_in_the_repository_counts_as_sent(tmp_path: Path) -> None:
    recordings = tmp_path / "recordings"
    write_games(recordings, ["game-1"])
    github = FakeGitHub(already_there=frozenset({"games/game-1-anonymized.jsonl.xz"}))
    board = StatusBoard(home_directory=tmp_path)
    await send_with(github, recordings, TOKEN, board)
    assert json.loads((recordings / SENT_LOG_NAME).read_text())["sent"] == ["game-1"]
    assert sending_part(board)[0] == "ok"


async def test_without_a_token_games_stay_on_this_mac(tmp_path: Path) -> None:
    recordings = tmp_path / "recordings"
    write_games(recordings, ["game-1"])
    github = FakeGitHub()
    board = StatusBoard(home_directory=tmp_path)
    await send_with(github, recordings, None, board)
    assert github.authorizations == []
    assert sending_part(board) == (
        "waiting",
        "No GitHub token in the Keychain: games stay on this Mac (1 not sent)",
    )


async def test_a_refused_token_stops_sending_and_is_never_shown(tmp_path: Path) -> None:
    recordings = tmp_path / "recordings"
    write_games(recordings, ["game-1", "game-2"])
    github = FakeGitHub(refused=True)
    board = StatusBoard(home_directory=tmp_path)
    await send_with(github, recordings, TOKEN, board)
    # The first refusal stops the round; the next one tries again.
    assert len(github.authorizations) == 1
    assert sending_part(board) == (
        "problem",
        f"GitHub refused the token (401): nothing sent to {REPOSITORY}",
    )
    assert not (recordings / SENT_LOG_NAME).exists()
    assert TOKEN not in board.report().model_dump_json()


async def test_a_game_that_would_leak_a_name_is_withheld(tmp_path: Path) -> None:
    recordings = tmp_path / "recordings"
    write_games(recordings, ["game-1"])
    (tmp_path / "leaking").mkdir()
    leaking = write_source_recording(
        tmp_path / "leaking", extra_payload={"body": "gg Shadow Step, well played"}
    )
    leaking.rename(recordings / "game-2.jsonl.xz")
    github = FakeGitHub()
    board = StatusBoard(home_directory=tmp_path)
    await send_with(github, recordings, TOKEN, board)
    assert set(github.puts) == {"games/game-1-anonymized.jsonl.xz"}
    sent_log = json.loads((recordings / SENT_LOG_NAME).read_text())
    # The build that withheld a game is kept with it, so that the next build tries it again.
    assert sent_log == {
        "sent": ["game-1"],
        "withheld": ["game-2"],
        "withheld_by": "0.1.0 (build 1, abc1234)",
        "crash_reports": [],
        "reports": [],
    }
    assert sending_part(board) == (
        "problem",
        f"Sent 1 game to {REPOSITORY}; 1 sent in all; 1 withheld: no safe anonymized copy",
    )
    # A withheld game is not tried again by the same build.
    github.puts.clear()
    await send_with(github, recordings, TOKEN, board)
    assert github.puts == {}


async def test_a_new_build_tries_the_withheld_games_again(tmp_path: Path) -> None:
    # None of the owner's games reached the repository; when one is withheld, the build that
    # fixes the anonymizer must send it, rather than leave it on the Mac for good.
    recordings = tmp_path / "recordings"
    write_games(recordings, ["game-1"])
    (recordings / SENT_LOG_NAME).write_text(
        json.dumps({"sent": [], "withheld": ["game-1"], "withheld_by": "0.1.0 (build 1, abc1234)"})
    )
    github = FakeGitHub()
    board = StatusBoard(home_directory=tmp_path)
    await send_with(github, recordings, TOKEN, board, build="0.1.0 (build 2, def5678)")
    assert set(github.puts) == {"games/game-1-anonymized.jsonl.xz"}
    sent_log = json.loads((recordings / SENT_LOG_NAME).read_text())
    assert sent_log["sent"] == ["game-1"]
    assert sent_log["withheld"] == []


async def test_a_log_from_before_builds_were_kept_tries_its_withheld_games_once(
    tmp_path: Path,
) -> None:
    recordings = tmp_path / "recordings"
    write_games(recordings, ["game-1"])
    (recordings / SENT_LOG_NAME).write_text(json.dumps({"sent": [], "withheld": ["game-1"]}))
    github = FakeGitHub()
    await send_with(github, recordings, TOKEN, StatusBoard(home_directory=tmp_path))
    assert set(github.puts) == {"games/game-1-anonymized.jsonl.xz"}


async def test_with_no_repository_sending_is_off(tmp_path: Path) -> None:
    board = StatusBoard(home_directory=tmp_path)
    async with aiohttp.ClientSession() as session:
        sender = GameSender(session, tmp_path, "", token_source=lambda: TOKEN, status=board)
        await sender.send_unsent()
    assert sending_part(board) == ("off", "Off: LEAGUEASYMODE_SEND_GAMES_TO is empty")


def test_the_keychain_is_asked_on_a_mac_only() -> None:
    asked: list[list[str]] = []

    def answer(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        asked.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, stdout=f"{TOKEN}\n", stderr="")

    assert keychain_token(run=answer, platform="darwin") == TOKEN
    assert asked == [["security", "find-generic-password", "-s", "LeagueasyMode-GitHub", "-w"]]
    assert keychain_token(run=answer, platform="linux") is None
    assert len(asked) == 1

    def not_found(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(arguments, 44, stdout="", stderr="not found")

    assert keychain_token(run=not_found, platform="darwin") is None


async def test_the_status_page_can_ask_for_a_round_and_nothing_else_can() -> None:
    rounds: list[str] = []

    async def send_games() -> None:
        rounds.append("sent")

    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        async with serve(create_overlay_application(engine, send_games=send_games)) as url:
            # A page elsewhere cannot send the header without a preflight, which is never answered.
            async with session.post(url + "/games/send") as refused:
                refused_status = refused.status
            async with session.post(
                url + "/games/send", headers={"X-LeagueasyMode-Request": "send-games"}
            ) as accepted:
                accepted_status = accepted.status
            for _ in range(50):
                if rounds:
                    break
                await asyncio.sleep(0.01)
        async with (
            serve(create_overlay_application(engine)) as url_without_sending,
            session.post(
                url_without_sending + "/games/send",
                headers={"X-LeagueasyMode-Request": "send-games"},
            ) as unavailable,
        ):
            unavailable_status = unavailable.status
    assert (refused_status, accepted_status, unavailable_status) == (403, 202, 404)
    assert rounds == ["sent"]


async def test_crash_reports_go_with_the_games_once(tmp_path: Path) -> None:
    recordings = tmp_path / "recordings"
    write_games(recordings, ["game-1"])
    reports = recordings / "crash-reports"
    reports.mkdir()
    (reports / "crash-2026-10-28T02-30-00Z-1.json").write_text('{"error_type": "KeyError"}\n')
    github = FakeGitHub()
    board = StatusBoard(home_directory=tmp_path)
    await send_with(github, recordings, TOKEN, board)
    assert set(github.puts) == {
        "games/game-1-anonymized.jsonl.xz",
        "crash-reports/crash-2026-10-28T02-30-00Z-1.json",
    }
    assert sending_part(board) == (
        "ok",
        f"Sent 1 game to {REPOSITORY}; 1 sent in all; 1 report files sent",
    )
    github.puts.clear()
    await send_with(github, recordings, TOKEN, board)
    assert github.puts == {}


def write_unfinished_game(directory: Path, name: str, *, minutes_ago: float) -> Path:
    """A recording an engine stopped before it closed: plain, last written so long ago."""
    finished = write_games(directory, [name])[0]
    plain_path = directory / f"{name}.jsonl"
    plain_path.write_bytes(lzma.decompress(finished.read_bytes()))
    finished.unlink()
    written_at = time.time() - minutes_ago * 60
    os.utime(plain_path, (written_at, written_at))
    return plain_path


async def test_a_game_left_open_by_a_stopped_engine_is_closed_and_sent(tmp_path: Path) -> None:
    # None of the owner's games reached the repository, and none was withheld: the recordings were
    # left open when the app quit or updated before the match timeline came. One untouched for
    # 20 minutes is no longer written by anyone, so it is closed and sent; a newer one may be.
    recordings = tmp_path / "recordings"
    write_unfinished_game(recordings, "game-old", minutes_ago=30)
    recent = write_unfinished_game(recordings, "game-now", minutes_ago=1)
    github = FakeGitHub()
    await send_with(github, recordings, TOKEN, StatusBoard(home_directory=tmp_path))
    assert set(github.puts) == {"games/game-old-anonymized.jsonl.xz"}
    assert (recordings / "game-old.jsonl.xz").exists()
    assert recent.exists()
