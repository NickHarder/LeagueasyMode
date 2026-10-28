"""Click to mark: each enemy's card carries what a click needs to mark the same enemy and spell."""

import dataclasses

from game_payloads import DEFAULT_PLAYERS, all_game_data
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.cooldowns import enemies_in_role_order
from leagueasymode.overlay_state import OverlayPreferences


def test_each_enemy_card_has_its_place_in_role_order_as_the_marks_count_it() -> None:
    payload = all_game_data(600.0)
    state = compute_overlay_state(payload)
    slots_by_champion = {
        card.champion_name: card.enemy_slot for card in state.players if card.side == "enemy"
    }
    in_role_order = enemies_in_role_order(GameSnapshot.model_validate(payload))
    # The keyboard's ⌃⌥1 to 5 and a click name the same enemy.
    assert slots_by_champion == {
        enemy.champion_name: slot for slot, enemy in enumerate(in_role_order, start=1)
    }
    assert all(card.enemy_slot is None for card in state.players if card.side == "ally")


def test_each_enemy_card_names_the_spells_its_buttons_mark() -> None:
    # Flash second: the "Flash" button is still their Flash, the other button the other spell.
    lux = dataclasses.replace(DEFAULT_PLAYERS[9], summoner_spells=("Exhaust", "Flash"))
    players = (*DEFAULT_PLAYERS[:9], lux)
    state = compute_overlay_state(all_game_data(600.0, players=players))
    lux_card = next(card for card in state.players if card.champion_name == "Lux")
    assert lux_card.marked_spell_names == ["Flash", "Exhaust"]
    ally_card = next(card for card in state.players if card.side == "ally")
    assert ally_card.marked_spell_names == []


def test_clicking_to_mark_is_off_until_the_player_turns_it_on() -> None:
    assert OverlayPreferences().click_to_mark is False
