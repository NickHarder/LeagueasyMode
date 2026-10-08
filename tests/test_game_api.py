import asyncio
import ssl

import aiohttp
import trustme
from aiohttp import web

from game_payloads import all_game_data
from leagueasymode.game_api import GameApiClient
from leagueasymode.riot_tls import create_riot_tls_context
from local_servers import serve, unused_local_url


def game_application(response: web.Response) -> web.Application:
    application = web.Application()

    async def answer(_request: web.Request) -> web.Response:
        return response

    application.router.add_get("/liveclientdata/allgamedata", answer)
    return application


async def test_a_running_game_answers_with_its_whole_state() -> None:
    payload = all_game_data(125.5)
    async with (
        serve(game_application(web.json_response(payload))) as base_url,
        aiohttp.ClientSession() as session,
    ):
        answer = await GameApiClient(session, base_url, tls_context=None).fetch_all_game_data()
    assert answer == payload


async def test_no_game_running_is_no_answer() -> None:
    async with aiohttp.ClientSession() as session:
        answer = await GameApiClient(
            session, unused_local_url(), tls_context=None
        ).fetch_all_game_data()
    assert answer is None


async def test_the_loading_screen_error_is_no_answer() -> None:
    loading_error = web.json_response(
        {"errorCode": "RESOURCE_NOT_FOUND", "httpStatus": 404, "message": "No game"}, status=404
    )
    async with (
        serve(game_application(loading_error)) as base_url,
        aiohttp.ClientSession() as session,
    ):
        answer = await GameApiClient(session, base_url, tls_context=None).fetch_all_game_data()
    assert answer is None


async def test_an_answer_that_is_not_json_is_no_answer() -> None:
    garbled = web.Response(text="{not json", content_type="application/json")
    async with serve(game_application(garbled)) as base_url, aiohttp.ClientSession() as session:
        answer = await GameApiClient(session, base_url, tls_context=None).fetch_all_game_data()
    assert answer is None


async def test_a_game_that_hangs_is_no_answer_within_the_timeout() -> None:
    application = web.Application()

    async def hang(_request: web.Request) -> web.Response:
        await asyncio.sleep(1)
        return web.json_response({})

    application.router.add_get("/liveclientdata/allgamedata", hang)
    async with serve(application) as base_url, aiohttp.ClientSession() as session:
        client = GameApiClient(session, base_url, tls_context=None, request_timeout_seconds=0.2)
        answer = await asyncio.wait_for(client.fetch_all_game_data(), timeout=2)
    assert answer is None


async def test_https_works_with_a_trusted_authority() -> None:
    authority = trustme.CA()
    server_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    authority.issue_cert("127.0.0.1").configure_cert(server_context)
    client_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    authority.configure_trust(client_context)
    payload = all_game_data(10.0)
    async with (
        serve(game_application(web.json_response(payload)), server_context) as base_url,
        aiohttp.ClientSession() as session,
    ):
        answer = await GameApiClient(
            session, base_url, tls_context=client_context
        ).fetch_all_game_data()
    assert answer == payload


async def test_the_riot_context_refuses_a_server_riot_did_not_sign() -> None:
    impostor_authority = trustme.CA()
    server_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    impostor_authority.issue_cert("127.0.0.1").configure_cert(server_context)
    async with (
        serve(game_application(web.json_response(all_game_data(10.0))), server_context) as base_url,
        aiohttp.ClientSession() as session,
    ):
        answer = await GameApiClient(
            session, base_url, tls_context=create_riot_tls_context()
        ).fetch_all_game_data()
    assert answer is None


def test_the_riot_context_trusts_only_riots_game_authority() -> None:
    context = create_riot_tls_context()
    authorities = context.get_ca_certs()
    assert len(authorities) == 1
    subject = dict(entry[0] for entry in authorities[0]["subject"])  # type: ignore[misc]  # ssl's own typing of subject is loose
    assert subject["commonName"] == "LoL Game Engineering Certificate Authority"
    assert context.verify_mode == ssl.CERT_REQUIRED
