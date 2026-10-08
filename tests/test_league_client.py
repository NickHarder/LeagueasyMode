import base64
from pathlib import Path
from typing import Final

import aiohttp
from aiohttp import web

from leagueasymode.league_client import (
    ClientCredentials,
    LeagueClient,
    find_client_credentials,
    parse_lockfile,
    parse_process_arguments,
)
from local_servers import serve

CLIENT_PASSWORD: Final = "AbC-123_xyz"  # noqa: S105  a stand-in for the password the client picks
CLIENT_DIRECTORY: Final = "/Applications/League of Legends.app/Contents/LoL"
PS_OUTPUT_WITH_CLIENT: Final = "\n".join(
    [
        "/sbin/launchd",
        f"{CLIENT_DIRECTORY}/LeagueClient.app/Contents/MacOS/LeagueClient"
        " --riotclient-app-port=50000",
        f"{CLIENT_DIRECTORY}/LeagueClient.app/Contents/Frameworks/LeagueClientUx Helper.app"
        "/Contents/MacOS/LeagueClientUx Helper --type=renderer",
        f"{CLIENT_DIRECTORY}/LeagueClient.app/Contents/MacOS/LeagueClientUx"
        ' "--riotclient-auth-token=other" "--app-port=54321"'
        f' "--remoting-auth-token={CLIENT_PASSWORD}" "--install-directory={CLIENT_DIRECTORY}"',
    ]
)

SERVER_PASSWORD: Final = "secret"  # noqa: S105  the stand-in server's password
WRONG_PASSWORD: Final = "guess"  # noqa: S105  a password the stand-in server refuses


def test_the_lockfile_gives_the_port_and_the_password() -> None:
    assert parse_lockfile(f"LeagueClient:12345:54321:{CLIENT_PASSWORD}:https") == ClientCredentials(
        port=54321, password=CLIENT_PASSWORD
    )


def test_a_damaged_lockfile_gives_nothing() -> None:
    assert parse_lockfile("LeagueClient:12345") is None
    assert parse_lockfile("LeagueClient:12345:not-a-port:secret:https") is None


def test_the_client_process_arguments_give_the_port_and_the_password() -> None:
    assert parse_process_arguments(PS_OUTPUT_WITH_CLIENT) == ClientCredentials(
        port=54321, password=CLIENT_PASSWORD
    )


def test_no_client_process_gives_nothing() -> None:
    assert parse_process_arguments("/sbin/launchd\n/usr/bin/zsh\n") is None


async def test_the_lockfile_is_read_first(tmp_path: Path) -> None:
    lockfile = tmp_path / "lockfile"
    lockfile_password = "from-lockfile"  # noqa: S105  a stand-in for the password the client picks
    lockfile.write_text(f"LeagueClient:1:40000:{lockfile_password}:https")

    async def list_processes() -> str:
        raise AssertionError("the process list is read only when no lockfile is found")

    credentials = await find_client_credentials([tmp_path / "missing", lockfile], list_processes)
    assert credentials == ClientCredentials(port=40000, password=lockfile_password)


async def test_without_a_lockfile_the_process_list_is_read(tmp_path: Path) -> None:
    async def list_processes() -> str:
        return PS_OUTPUT_WITH_CLIENT

    credentials = await find_client_credentials([tmp_path / "missing"], list_processes)
    assert credentials == ClientCredentials(port=54321, password=CLIENT_PASSWORD)


def client_application(password: str) -> web.Application:
    application = web.Application()
    expected_header = "Basic " + base64.b64encode(f"riot:{password}".encode()).decode()

    async def gameflow_session(request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != expected_header:
            return web.json_response({"message": "unauthorized"}, status=401)
        return web.json_response({"phase": "InProgress", "gameData": {"gameId": 7}})

    application.router.add_get("/lol-gameflow/v1/session", gameflow_session)
    return application


async def test_the_client_answers_with_the_password() -> None:
    async with (
        serve(client_application(SERVER_PASSWORD)) as base_url,
        aiohttp.ClientSession() as session,
    ):
        client = LeagueClient(session, base_url, password=SERVER_PASSWORD, tls_context=None)
        answer = await client.get_json("/lol-gameflow/v1/session")
    assert answer == {"phase": "InProgress", "gameData": {"gameId": 7}}


async def test_a_wrong_password_or_a_missing_path_is_no_answer() -> None:
    async with (
        serve(client_application(SERVER_PASSWORD)) as base_url,
        aiohttp.ClientSession() as session,
    ):
        wrong_password = LeagueClient(session, base_url, password=WRONG_PASSWORD, tls_context=None)
        right_password = LeagueClient(session, base_url, password=SERVER_PASSWORD, tls_context=None)
        assert await wrong_password.get_json("/lol-gameflow/v1/session") is None
        assert await right_password.get_json("/lol-match-history/v1/game-timelines/7") is None


def test_the_credentials_never_print_the_password() -> None:
    assert CLIENT_PASSWORD not in repr(ClientCredentials(port=54321, password=CLIENT_PASSWORD))
