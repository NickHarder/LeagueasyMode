import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import aiohttp
import pytest

from data_dragon_fixtures import FIXTURE_FILES, FIXTURE_VERSIONS, fake_data_dragon
from leagueasymode.data_dragon import (
    DataDragonClient,
    ItemHaste,
    PatchStats,
    PatchStatsStore,
    create_system_tls_context,
    load_patch_stats,
)
from local_servers import serve, unused_local_url


@asynccontextmanager
async def data_dragon_client(
    requested_paths: list[str], versions: list[str] = FIXTURE_VERSIONS
) -> AsyncIterator[DataDragonClient]:
    async with (
        serve(fake_data_dragon(requested_paths, versions)) as base_url,
        aiohttp.ClientSession() as session,
    ):
        yield DataDragonClient(session, base_url, tls_context=None)


def files_under(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.rglob("*"))


@pytest.fixture
def patch_data_directory(tmp_path: Path) -> Path:
    return tmp_path / "patch-data"


async def test_a_patch_is_fetched_once_and_then_read_from_disk(patch_data_directory: Path) -> None:
    requested_paths: list[str] = []
    store = PatchStatsStore(patch_data_directory)
    async with data_dragon_client(requested_paths) as client:
        first = await load_patch_stats(client, store, "16.19.712.1234")
        paths_after_the_first = list(requested_paths)
        second = await load_patch_stats(client, store, "16.19.712.1234")
    assert first is not None
    assert first.version == "16.19.1"
    assert paths_after_the_first == [
        "/api/versions.json",
        "/cdn/16.19.1/data/en_US/championFull.json",
        "/cdn/16.19.1/data/en_US/item.json",
        "/cdn/16.19.1/data/en_US/summoner.json",
    ]
    # The second game of the same patch asks nothing of the internet.
    assert requested_paths == paths_after_the_first
    assert second is not None
    assert second.version == "16.19.1"
    assert (
        patch_data_directory / "16.19.1" / "championFull.json"
    ).read_bytes() == FIXTURE_FILES.champions


async def test_a_game_on_a_new_patch_fetches_that_patch(patch_data_directory: Path) -> None:
    store = PatchStatsStore(patch_data_directory)
    store.save("16.18.1", FIXTURE_FILES)
    requested_paths: list[str] = []
    async with data_dragon_client(requested_paths) as client:
        stats = await load_patch_stats(client, store, "16.19.700.1")
    assert stats is not None
    assert stats.version == "16.19.1"
    assert "/cdn/16.19.1/data/en_US/championFull.json" in requested_paths
    assert store.cached_versions() == ["16.19.1", "16.18.1"]


async def test_the_newest_patch_on_disk_stands_in_when_data_dragon_cannot_be_reached(
    patch_data_directory: Path,
) -> None:
    store = PatchStatsStore(patch_data_directory)
    store.save("16.17.1", FIXTURE_FILES)
    store.save("16.18.1", FIXTURE_FILES)
    async with aiohttp.ClientSession() as session:
        client = DataDragonClient(session, unused_local_url(), tls_context=None)
        stats = await load_patch_stats(client, store, "16.19.700.1")
    assert stats is not None
    assert stats.version == "16.18.1"


async def test_nothing_on_disk_and_no_data_dragon_means_no_stats(
    patch_data_directory: Path,
) -> None:
    async with aiohttp.ClientSession() as session:
        client = DataDragonClient(session, unused_local_url(), tls_context=None)
        stats = await load_patch_stats(client, PatchStatsStore(patch_data_directory), "16.19.7.1")
    assert stats is None


async def test_with_downloads_off_only_the_patches_on_disk_are_used(
    patch_data_directory: Path,
) -> None:
    store = PatchStatsStore(patch_data_directory)
    assert await load_patch_stats(None, store, "16.19.700.1") is None
    store.save("16.18.1", FIXTURE_FILES)
    stats = await load_patch_stats(None, store, "16.19.700.1")
    assert stats is not None
    assert stats.version == "16.18.1"


async def test_without_the_league_client_the_newest_patch_is_used(
    patch_data_directory: Path,
) -> None:
    requested_paths: list[str] = []
    async with data_dragon_client(requested_paths) as client:
        stats = await load_patch_stats(client, PatchStatsStore(patch_data_directory), None)
    assert stats is not None
    assert stats.version == "16.19.1"


async def test_a_patch_data_dragon_has_not_published_yet_gets_its_newest(
    patch_data_directory: Path,
) -> None:
    requested_paths: list[str] = []
    async with data_dragon_client(requested_paths) as client:
        stats = await load_patch_stats(client, PatchStatsStore(patch_data_directory), "16.20.100.1")
    assert stats is not None
    assert stats.version == "16.19.1"


async def test_a_version_that_is_not_a_patch_number_never_names_a_file(tmp_path: Path) -> None:
    patch_data_directory = tmp_path / "patch-data"
    requested_paths: list[str] = []
    async with data_dragon_client(requested_paths, versions=["../../escaped"]) as client:
        stats = await load_patch_stats(client, PatchStatsStore(patch_data_directory), None)
    assert stats is None
    assert requested_paths == ["/api/versions.json"]
    assert files_under(tmp_path) == []


async def test_a_game_version_that_is_not_a_patch_number_is_taken_as_unknown(
    patch_data_directory: Path,
) -> None:
    requested_paths: list[str] = []
    async with data_dragon_client(requested_paths) as client:
        stats = await load_patch_stats(client, PatchStatsStore(patch_data_directory), "../../16.18")
    assert stats is not None
    assert stats.version == "16.19.1"


async def test_a_patch_on_disk_that_cannot_be_read_is_fetched_again(
    patch_data_directory: Path,
) -> None:
    broken_directory = patch_data_directory / "16.19.1"
    broken_directory.mkdir(parents=True)
    for file_name in ("championFull.json", "item.json", "summoner.json"):
        (broken_directory / file_name).write_text("not json")
    requested_paths: list[str] = []
    async with data_dragon_client(requested_paths) as client:
        stats = await load_patch_stats(
            client, PatchStatsStore(patch_data_directory), "16.19.712.1234"
        )
    assert stats is not None
    assert (broken_directory / "championFull.json").read_bytes() == FIXTURE_FILES.champions


def test_a_champion_is_found_by_the_games_raw_name_or_by_its_name() -> None:
    stats = PatchStats.from_data_dragon("16.19.1", FIXTURE_FILES)
    assert stats is not None
    # Wukong is "MonkeyKing" to the game and to Data Dragon alike.
    by_raw_name = stats.champion_base_stats("game_character_displayname_MonkeyKing", "悟空")
    assert by_raw_name is not None
    assert by_raw_name.health == 610
    by_name = stats.champion_base_stats("", "Wukong")
    assert by_name is not None
    assert by_name.health == 610
    # The game's spelling of a raw name can differ in case from Data Dragon's.
    assert stats.champion_base_stats("game_character_displayname_leesin", "") is not None
    assert stats.champion_base_stats("game_character_displayname_Nobody", "Nobody") is None


def test_an_item_has_its_stat_bonuses() -> None:
    stats = PatchStats.from_data_dragon("16.19.1", FIXTURE_FILES)
    assert stats is not None
    infinity_edge = stats.item_bonuses(3031)
    assert infinity_edge is not None
    assert infinity_edge.flat_attack_damage == 65
    control_ward = stats.item_bonuses(2055)
    assert control_ward is not None
    assert control_ward.flat_health == 0
    assert stats.item_bonuses(999999) is None


def test_files_that_are_not_data_dragons_give_no_stats() -> None:
    assert PatchStats.from_data_dragon("16.19.1", replace(FIXTURE_FILES, champions=b"[]")) is None
    assert PatchStats.from_data_dragon("16.19.1", replace(FIXTURE_FILES, items=b"not json")) is None
    assert (
        PatchStats.from_data_dragon("16.19.1", replace(FIXTURE_FILES, summoners=b"not json"))
        is None
    )
    assert (
        PatchStats.from_data_dragon(
            "16.19.1", replace(FIXTURE_FILES, champions=b'{"version": "x", "data": {}}')
        )
        is None
    )


def test_a_champions_ultimate_cooldowns_go_by_rank() -> None:
    stats = PatchStats.from_data_dragon("16.19.1", FIXTURE_FILES)
    assert stats is not None
    assert stats.ultimate_cooldowns("game_character_displayname_Zed", "Zed") == (120, 100, 80)
    assert stats.ultimate_cooldowns("", "Nobody") is None


def test_a_summoner_spell_has_its_cooldown() -> None:
    stats = PatchStats.from_data_dragon("16.19.1", FIXTURE_FILES)
    assert stats is not None
    assert stats.summoner_spell_cooldown("SummonerFlash") == 300
    assert stats.summoner_spell_cooldown("SummonerTeleport") == 360
    assert stats.summoner_spell_cooldown("SummonerNothing") is None


def test_an_items_haste_is_read_from_its_description() -> None:
    stats = PatchStats.from_data_dragon("16.19.1", FIXTURE_FILES)
    assert stats is not None
    assert stats.item_haste(3158) == ItemHaste(ability_haste=15, summoner_spell_haste=10)
    assert stats.item_haste(3071) == ItemHaste(ability_haste=20, summoner_spell_haste=0)
    assert stats.item_haste(3031) == ItemHaste(ability_haste=0, summoner_spell_haste=0)
    assert stats.item_haste(999999) == ItemHaste(ability_haste=0, summoner_spell_haste=0)


def test_data_dragon_is_reached_with_the_systems_trust_and_its_hostname_checked() -> None:
    tls_context = create_system_tls_context()
    assert tls_context.verify_mode == ssl.CERT_REQUIRED
    assert tls_context.check_hostname is True
