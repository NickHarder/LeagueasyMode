import dataclasses

from game_payloads import DEFAULT_PLAYERS, all_game_data
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.players import numbers_window, player_cards

# DEFAULT_PLAYERS: 0-4 are the player's team (ORDER), 5-9 the enemy (CHAOS).


def snapshot_with_dead(
    game_time_seconds: float, respawn_seconds_by_index: dict[int, float]
) -> GameSnapshot:
    players = tuple(
        dataclasses.replace(
            seed, is_dead=True, respawn_timer_seconds=respawn_seconds_by_index[index]
        )
        if index in respawn_seconds_by_index
        else seed
        for index, seed in enumerate(DEFAULT_PLAYERS)
    )
    return GameSnapshot.model_validate(all_game_data(game_time_seconds, [], players=players))


def test_nobody_dead_is_no_window() -> None:
    assert numbers_window(snapshot_with_dead(900.0, {})) is None


def test_two_enemies_down_last_until_the_later_respawn() -> None:
    window = numbers_window(snapshot_with_dead(900.0, {6: 10.0, 8: 25.0}))
    assert window is not None
    assert (window.ally_dead_count, window.enemy_dead_count) == (0, 2)
    assert window.ends_at_game_time_seconds == 925.0


def test_the_window_closes_when_the_counts_even_out() -> None:
    window = numbers_window(snapshot_with_dead(900.0, {6: 10.0, 8: 25.0, 2: 15.0}))
    assert window is not None
    assert (window.ally_dead_count, window.enemy_dead_count) == (1, 2)
    assert window.ends_at_game_time_seconds == 910.0


def test_an_even_count_is_no_window() -> None:
    assert numbers_window(snapshot_with_dead(900.0, {6: 10.0, 1: 30.0})) is None


def test_more_of_your_team_down_is_no_window() -> None:
    assert numbers_window(snapshot_with_dead(900.0, {1: 10.0, 2: 12.0, 7: 5.0})) is None


def test_each_player_card_says_side_level_and_respawn() -> None:
    leveled_players = tuple(
        dataclasses.replace(seed, level=index + 3) for index, seed in enumerate(DEFAULT_PLAYERS)
    )
    dead_mid = tuple(
        dataclasses.replace(seed, is_dead=True, respawn_timer_seconds=12.5)
        if seed.champion_name == "Zed"
        else seed
        for seed in leveled_players
    )
    snapshot = GameSnapshot.model_validate(all_game_data(600.0, [], players=dead_mid))
    cards = player_cards(snapshot)
    zed = next(card for card in cards if card.champion_name == "Zed")
    garen = next(card for card in cards if card.champion_name == "Garen")
    assert (zed.side, zed.position, zed.level, zed.is_dead, zed.respawns_at_game_time_seconds) == (
        "enemy",
        "MIDDLE",
        10,
        True,
        612.5,
    )
    assert (garen.side, garen.is_dead, garen.respawns_at_game_time_seconds) == ("ally", False, None)
    assert [card.side for card in cards] == ["ally"] * 5 + ["enemy"] * 5
