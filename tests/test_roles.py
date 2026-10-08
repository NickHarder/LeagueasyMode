import dataclasses
from typing import Final

from game_payloads import CHAOS, ORDER, PlayerSeed, all_game_data
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.players import player_cards
from leagueasymode.inference.roles import assign_roles

SUPPORT_ITEM: Final = ((3865, "World Atlas", 400),)


def team(side: str, *seeds: PlayerSeed) -> tuple[PlayerSeed, ...]:
    return tuple(dataclasses.replace(seed, team=side) for seed in seeds)


def unassigned(
    name: str,
    champion: str,
    spells: tuple[str, str],
    creep_score: int,
    items: tuple[tuple[int, str, int], ...] = (),
) -> PlayerSeed:
    return PlayerSeed(
        name, "NA1", champion, ORDER, "", spells, creep_score=creep_score, items=items
    )


BLIND_PICK_TEAM: Final = (
    unassigned("A", "Darius", ("Flash", "Teleport"), 70),
    unassigned("B", "Vi", ("Flash", "Smite"), 55),
    unassigned("C", "Zed", ("Flash", "Ignite"), 80),
    unassigned("D", "Caitlyn", ("Flash", "Heal"), 85),
    unassigned("E", "Lux", ("Flash", "Exhaust"), 10, SUPPORT_ITEM),
)


def roles_by_champion(
    players: tuple[PlayerSeed, ...], game_time_seconds: float = 600.0
) -> dict[str, tuple[str, bool]]:
    snapshot = GameSnapshot.model_validate(
        all_game_data(game_time_seconds, [], players=players, active_player_index=0)
    )
    assigned = assign_roles(snapshot)
    # Both teams field the same champions; the player's own team (ORDER) is the one read.
    return {
        player.champion_name: (assigned[player_index].role, assigned[player_index].is_inferred)
        for player_index, player in enumerate(snapshot.players)
        if player.team == ORDER
    }


def test_blind_pick_roles_follow_smite_the_support_item_and_the_spells() -> None:
    roles = roles_by_champion(team(ORDER, *BLIND_PICK_TEAM) + team(CHAOS, *BLIND_PICK_TEAM))
    assert {champion: role for champion, (role, _) in roles.items()} == {
        "Darius": "TOP",
        "Vi": "JUNGLE",
        "Zed": "MIDDLE",
        "Caitlyn": "BOTTOM",
        "Lux": "UTILITY",
    }
    assert all(is_inferred for _, is_inferred in roles.values())


def test_roles_the_game_assigns_are_taken_as_given() -> None:
    given = tuple(
        dataclasses.replace(seed, position=position)
        for seed, position in zip(
            BLIND_PICK_TEAM, ("JUNGLE", "TOP", "MIDDLE", "BOTTOM", "UTILITY"), strict=True
        )
    )
    roles = roles_by_champion(team(ORDER, *given) + team(CHAOS, *BLIND_PICK_TEAM))
    # Darius was given JUNGLE although he has no Smite: what the game says wins.
    assert roles["Darius"] == ("JUNGLE", False)


def test_without_a_support_item_the_lowest_cs_takes_support() -> None:
    no_support_item = tuple(dataclasses.replace(seed, items=()) for seed in BLIND_PICK_TEAM)
    roles = roles_by_champion(team(ORDER, *no_support_item) + team(CHAOS, *no_support_item))
    assert roles["Lux"][0] == "UTILITY"


def test_each_role_is_given_once_per_team() -> None:
    two_junglers = (
        unassigned("A", "Darius", ("Flash", "Smite"), 70),
        unassigned("B", "Vi", ("Flash", "Smite"), 55),
        *BLIND_PICK_TEAM[2:],
    )
    snapshot = GameSnapshot.model_validate(
        all_game_data(600.0, [], players=team(ORDER, *two_junglers) + team(CHAOS, *BLIND_PICK_TEAM))
    )
    order_roles = [
        guess.role
        for guess, player in zip(assign_roles(snapshot), snapshot.players, strict=True)
        if player.team == ORDER
    ]
    assert sorted(order_roles) == ["BOTTOM", "JUNGLE", "MIDDLE", "TOP", "UTILITY"]


def test_each_card_carries_the_role_and_how_sure_it_is() -> None:
    snapshot = GameSnapshot.model_validate(
        all_game_data(
            600.0,
            [],
            players=team(ORDER, *BLIND_PICK_TEAM) + team(CHAOS, *BLIND_PICK_TEAM),
            active_player_index=0,
        )
    )
    cards = player_cards(snapshot)
    enemy_vi = next(card for card in cards if card.side == "enemy" and card.champion_name == "Vi")
    assert (enemy_vi.role, enemy_vi.role_confidence) == ("JUNGLE", "likely")
