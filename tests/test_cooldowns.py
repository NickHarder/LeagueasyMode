import dataclasses
from typing import Final

import pytest

from data_dragon_fixtures import fixture_patch_stats
from game_payloads import DEFAULT_PLAYERS, PlayerSeed, all_game_data
from leagueasymode.game_state import GameSnapshot, SummonerSpell
from leagueasymode.inference.cooldowns import (
    enemies_in_role_order,
    marked_cooldown,
    running_cooldowns,
)

ZED: Final = DEFAULT_PLAYERS[7]
BLACK_CLEAVER: Final = (3071, "Black Cleaver", 3000)
IONIAN_BOOTS: Final = (3158, "Ionian Boots of Lucidity", 900)
MIDDLE_SLOT: Final = 3


def snapshot_with(zed: PlayerSeed, game_time_seconds: float = 600.0) -> GameSnapshot:
    players = tuple(zed if seed is ZED else seed for seed in DEFAULT_PLAYERS)
    return GameSnapshot.model_validate(all_game_data(game_time_seconds, players=players))


def test_a_summoner_spell_is_known_by_its_raw_name() -> None:
    flash = SummonerSpell.model_validate(
        {
            "displayName": "Destello",
            "rawDisplayName": "GeneratedTip_SummonerSpell_SummonerFlash_DisplayName",
        }
    )
    assert flash.spell_id() == "SummonerFlash"
    assert SummonerSpell.model_validate({"displayName": "Flash"}).spell_id() == ""


def test_enemies_are_numbered_in_role_order() -> None:
    enemies = enemies_in_role_order(snapshot_with(ZED))
    assert [enemy.champion_name for enemy in enemies] == ["Darius", "Vi", "Zed", "Caitlyn", "Lux"]


def test_a_marked_flash_is_back_after_its_cooldown() -> None:
    timer = marked_cooldown(snapshot_with(ZED), MIDDLE_SLOT, "flash", fixture_patch_stats())
    assert timer is not None
    assert (timer.champion_name, timer.label, timer.spell_name) == ("Zed", "F", "Flash")
    assert timer.marked_at_game_time_seconds == 600.0
    assert timer.ready_at_game_time_seconds == pytest.approx(900.0)


def test_the_other_summoner_spell_is_the_one_that_is_not_flash() -> None:
    timer = marked_cooldown(snapshot_with(ZED), MIDDLE_SLOT, "summoner", fixture_patch_stats())
    assert timer is not None
    assert (timer.label, timer.spell_name) == ("IGN", "Ignite")
    assert timer.ready_at_game_time_seconds == pytest.approx(780.0)


def test_the_ultimates_cooldown_goes_by_its_rank_from_the_level() -> None:
    patch_stats = fixture_patch_stats()
    for level, cooldown_seconds in ((6, 120.0), (11, 100.0), (16, 80.0), (3, 120.0)):
        zed = dataclasses.replace(ZED, level=level)
        timer = marked_cooldown(snapshot_with(zed), MIDDLE_SLOT, "ultimate", patch_stats)
        assert timer is not None
        assert timer.label == "R"
        assert timer.ready_at_game_time_seconds == pytest.approx(600.0 + cooldown_seconds), level


def test_haste_from_items_shortens_the_cooldown() -> None:
    zed = dataclasses.replace(ZED, level=6, items=(BLACK_CLEAVER, IONIAN_BOOTS))
    patch_stats = fixture_patch_stats()
    ultimate = marked_cooldown(snapshot_with(zed), MIDDLE_SLOT, "ultimate", patch_stats)
    flash = marked_cooldown(snapshot_with(zed), MIDDLE_SLOT, "flash", patch_stats)
    assert ultimate is not None
    assert flash is not None
    # 35 ability haste from the two items; 10 summoner spell haste from the boots.
    assert ultimate.ready_at_game_time_seconds == pytest.approx(600.0 + 120.0 * 100 / 135)
    assert flash.ready_at_game_time_seconds == pytest.approx(600.0 + 300.0 * 100 / 110)


def test_a_player_without_flash_has_their_first_spell_marked_as_flash() -> None:
    zed = dataclasses.replace(ZED, summoner_spells=("Ghost", "Ignite"))
    timer = marked_cooldown(snapshot_with(zed), MIDDLE_SLOT, "flash", fixture_patch_stats())
    assert timer is not None
    assert timer.spell_name == "Ghost"


def test_an_empty_slot_or_unknown_patch_gives_no_timer() -> None:
    assert marked_cooldown(snapshot_with(ZED), 6, "flash", fixture_patch_stats()) is None
    assert marked_cooldown(snapshot_with(ZED), 0, "flash", fixture_patch_stats()) is None
    assert marked_cooldown(snapshot_with(ZED), MIDDLE_SLOT, "flash", None) is None


def test_a_timer_is_shown_until_its_spell_is_back() -> None:
    timer = marked_cooldown(snapshot_with(ZED), MIDDLE_SLOT, "summoner", fixture_patch_stats())
    assert timer is not None
    assert running_cooldowns([timer], 779.0) == [timer]
    assert running_cooldowns([timer], 780.0) == []
