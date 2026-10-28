"""Sightings: when your team last saw each enemy, from what the game gives only in sight."""

import dataclasses
from typing import Final

from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    PlayerSeed,
    all_game_data,
    champion_kill_event,
    game_start_event,
)
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.positions import PositionRules
from leagueasymode.inference.sightings import SightingTracker
from leagueasymode.tuning import Tuning

AHRI: Final = DEFAULT_PLAYERS[2]
VI_SEED: Final = DEFAULT_PLAYERS[6]
ZED: Final = DEFAULT_PLAYERS[7]
CAITLYN: Final = DEFAULT_PLAYERS[8]
LONG_SWORD: Final = (1036, "Long Sword", 350)


def answer_at(
    game_time_seconds: float,
    changed: dict[str, PlayerSeed] | None = None,
    events: list[dict[str, JsonValue]] | None = None,
) -> JsonValue:
    """The game at a time, with some players changed from the default ones."""
    players = tuple((changed or {}).get(seed.champion_name, seed) for seed in DEFAULT_PLAYERS)
    return all_game_data(game_time_seconds, [game_start_event(), *(events or [])], players=players)


def sightings_of(*answers: JsonValue) -> dict[str, float]:
    """When each enemy was last seen after a run of answers, by lower-cased champion alias."""
    tracker = SightingTracker()
    last_seen: dict[tuple[str, str], float] = {}
    for answer in answers:
        last_seen = tracker.update(GameSnapshot.model_validate(answer))
    return {champion_alias: seen_at for (_, champion_alias), seen_at in last_seen.items()}


def test_an_enemys_creep_score_items_or_level_changing_is_a_sighting() -> None:
    assert sightings_of(
        answer_at(100.0),
        answer_at(101.0, {"Zed": dataclasses.replace(ZED, creep_score=4)}),
        answer_at(
            102.0,
            {
                "Zed": dataclasses.replace(ZED, creep_score=4),
                "Vi": dataclasses.replace(VI_SEED, level=2),
            },
        ),
        answer_at(
            103.0,
            {
                "Zed": dataclasses.replace(ZED, creep_score=4),
                "Vi": dataclasses.replace(VI_SEED, level=2),
                "Caitlyn": dataclasses.replace(CAITLYN, items=(LONG_SWORD,)),
            },
        ),
    ) == {"zed": 101.0, "vi": 102.0, "caitlyn": 103.0}


def test_the_first_answer_and_your_own_team_are_no_sighting() -> None:
    # Everyone has a creep score in the first answer the overlay sees; that is no sighting, and
    # your own team's farming never is.
    assert (
        sightings_of(
            answer_at(100.0, {"Zed": dataclasses.replace(ZED, creep_score=30)}),
            answer_at(
                101.0,
                {
                    "Zed": dataclasses.replace(ZED, creep_score=30),
                    "Ahri": dataclasses.replace(AHRI, creep_score=4),
                },
            ),
        )
        == {}
    )


def test_an_enemy_shopping_while_dead_is_not_seen() -> None:
    dead_zed = dataclasses.replace(ZED, is_dead=True, respawn_timer_seconds=20.0)
    assert (
        sightings_of(
            answer_at(100.0, {"Zed": dead_zed}),
            answer_at(101.0, {"Zed": dataclasses.replace(dead_zed, items=(LONG_SWORD,))}),
        )
        == {}
    )


def test_a_kill_with_your_team_is_a_sighting() -> None:
    zed_kills_ahri = champion_kill_event(
        1, 95.0, ZED.riot_id_game_name, AHRI.riot_id_game_name, [VI_SEED.riot_id_game_name]
    )
    ahri_kills_caitlyn = champion_kill_event(
        2, 97.0, AHRI.riot_id_game_name, CAITLYN.riot_id_game_name, []
    )
    # The killer and the helper of an ally's death were in sight, and so was an enemy your team
    # killed.
    assert sightings_of(answer_at(100.0, events=[zed_kills_ahri, ahri_kills_caitlyn])) == {
        "zed": 95.0,
        "vi": 95.0,
        "caitlyn": 97.0,
    }


def test_a_new_game_starts_the_sightings_over() -> None:
    assert (
        sightings_of(
            answer_at(600.0),
            answer_at(601.0, {"Zed": dataclasses.replace(ZED, creep_score=4)}),
            answer_at(30.0),
        )
        == {}
    )


def test_an_enemy_seen_in_the_last_three_seconds_is_marked_seen() -> None:
    def zed_card_at(game_time_seconds: float, tuning: Tuning) -> tuple[bool, float | None]:
        tracker = SightingTracker()
        compute_overlay_state(answer_at(100.0), sighting_tracker=tracker, tuning=tuning)
        farming = {"Zed": dataclasses.replace(ZED, creep_score=4)}
        compute_overlay_state(answer_at(101.0, farming), sighting_tracker=tracker, tuning=tuning)
        state = compute_overlay_state(
            answer_at(game_time_seconds, farming), sighting_tracker=tracker, tuning=tuning
        )
        zed = next(card for card in state.players if card.champion_name == "Zed")
        return zed.is_seen, zed.seen_seconds_ago

    assert zed_card_at(103.0, Tuning()) == (True, 2.0)
    assert zed_card_at(105.0, Tuning()) == (False, 4.0)
    # How long a sighting lasts is the owner's to tune.
    assert zed_card_at(105.0, Tuning(positions=PositionRules(seen_for_seconds=5.0))) == (True, 4.0)


def test_without_a_sighting_no_card_is_seen() -> None:
    state = compute_overlay_state(answer_at(100.0), sighting_tracker=SightingTracker())
    assert not any(card.is_seen for card in state.players)
    assert all(card.seen_seconds_ago is None for card in state.players)
