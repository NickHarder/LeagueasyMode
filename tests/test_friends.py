"""The friends list (phase 11.5): kept, changed from the settings page, and marked in a game."""

import dataclasses
from pathlib import Path
from typing import Final

import aiohttp
import pytest
from pydantic import ValidationError

from game_payloads import DEFAULT_PLAYERS, all_game_data
from leagueasymode.engine import OverlayEngine, compute_overlay_state
from leagueasymode.friends import MOST_FRIENDS, FriendsList, load_friends, save_friends
from leagueasymode.game_api import GameApiClient
from leagueasymode.overlay_server import create_overlay_application
from local_servers import serve, unused_local_url

FRIENDS_HEADERS: Final = {"X-LeagueasyMode-Request": "friends"}


def test_riot_ids_are_kept_as_written_and_matched_in_any_case() -> None:
    friends = FriendsList(riot_ids=("  Zed Main#NA1 ", "zed main#na1", "Lux Enjoyer#EUW"))
    assert friends.riot_ids == ("Zed Main#NA1", "Lux Enjoyer#EUW")
    assert friends.riot_id_keys == frozenset({"zed main#na1", "lux enjoyer#euw"})


@pytest.mark.parametrize(
    "riot_id",
    ["no tag", "#NA1", "ab#NA1", "Name#", "Name#TOOLONG", "a#b#NA1", "x" * 17 + "#NA1"],
)
def test_a_line_that_is_not_a_riot_id_is_refused(riot_id: str) -> None:
    with pytest.raises(ValidationError, match="Riot ID"):
        FriendsList(riot_ids=(riot_id,))


def test_the_list_has_a_limit() -> None:
    many = tuple(f"Friend{index:03d}#NA1" for index in range(MOST_FRIENDS + 1))
    with pytest.raises(ValidationError, match="at most"):
        FriendsList(riot_ids=many)


def test_the_list_is_kept_between_runs(tmp_path: Path) -> None:
    friends_path = tmp_path / "friends.json"
    assert load_friends(friends_path) == FriendsList()
    save_friends(friends_path, FriendsList(riot_ids=("Zed Main#NA1",)))
    assert load_friends(friends_path) == FriendsList(riot_ids=("Zed Main#NA1",))
    friends_path.write_text("not json")
    assert load_friends(friends_path) == FriendsList()


def test_the_overlay_marks_the_friends_in_the_game() -> None:
    zed = next(seed for seed in DEFAULT_PLAYERS if seed.champion_name == "Zed")
    jinx = next(seed for seed in DEFAULT_PLAYERS if seed.champion_name == "Jinx")
    state = compute_overlay_state(
        all_game_data(300.0),
        friend_riot_ids=FriendsList(riot_ids=(zed.riot_id.upper(), jinx.riot_id)).riot_id_keys,
    )
    friends = sorted(card.champion_name for card in state.players if card.is_friend)
    assert friends == ["Jinx", "Zed"]


def test_without_friends_no_one_is_marked() -> None:
    state = compute_overlay_state(all_game_data(300.0))
    assert not any(card.is_friend for card in state.players)


async def test_the_settings_page_changes_the_list(tmp_path: Path) -> None:
    friends_path = tmp_path / "friends.json"
    async with aiohttp.ClientSession() as session:
        engine = OverlayEngine(
            GameApiClient(session, unused_local_url(), tls_context=None), poll_interval_seconds=1
        )
        application = create_overlay_application(engine, friends_path=friends_path)
        async with serve(application) as overlay_url:
            async with session.get(overlay_url + "/friends") as empty_response:
                empty = await empty_response.json()
            body = {"riot_ids": ["Zed Main#NA1"]}
            async with session.put(overlay_url + "/friends", json=body) as refused_response:
                refused_status = refused_response.status
            async with session.put(
                overlay_url + "/friends", json={"riot_ids": ["no tag"]}, headers=FRIENDS_HEADERS
            ) as invalid_response:
                invalid_status = invalid_response.status
                invalid_message = (await invalid_response.json())["message"]
            async with session.put(
                overlay_url + "/friends", json=body, headers=FRIENDS_HEADERS
            ) as saved_response:
                saved_status = saved_response.status
            async with session.get(overlay_url + "/friends") as kept_response:
                kept = await kept_response.json()
    assert empty == {"riot_ids": []}
    # Only the settings page, served from here, can send the header.
    assert refused_status == 403
    assert invalid_status == 400
    assert "no tag" in invalid_message
    assert saved_status == 200
    assert kept == {"riot_ids": ["Zed Main#NA1"]}
    assert engine.friends == FriendsList(riot_ids=("Zed Main#NA1",))
    assert load_friends(friends_path) == engine.friends


def test_the_friends_are_not_in_the_overlays_state() -> None:
    # The state goes to the overlay page and into problem reports' status; names stay out of it.
    zed = dataclasses.replace(DEFAULT_PLAYERS[6])
    state = compute_overlay_state(
        all_game_data(300.0), friend_riot_ids=frozenset({zed.riot_id.lower()})
    )
    assert zed.riot_id.lower() not in state.model_dump_json().lower()
