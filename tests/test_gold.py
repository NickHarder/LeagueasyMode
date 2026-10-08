import dataclasses
from typing import Final, TypedDict

import pytest
from pydantic import JsonValue

from game_payloads import (
    DEFAULT_PLAYERS,
    PlayerSeed,
    all_game_data,
    baron_kill_event,
    champion_kill_event,
    game_start_event,
    inhibitor_killed_event,
    turret_killed_event,
)
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.gold import (
    GoldTracker,
    PlayerKey,
    base_bounty_gold,
    chance_of_affording,
    feed_gold,
    passive_gold,
    team_gold,
)
from leagueasymode.overlay_state import GoldEstimate, PlayerCard
from leagueasymode.patch_data import CatalogItem, ItemCatalog

LONG_SWORD: Final = (1036, "Long Sword", 350)
BF_SWORD: Final = (1038, "B. F. Sword", 1300)
INFINITY_EDGE: Final = (3031, "Infinity Edge", 3400)
DORANS_BLADE: Final = (1055, "Doran's Blade", 450)
HEALTH_POTION: Final = (2003, "Health Potion", 50)
WORLD_ATLAS: Final = (3865, "World Atlas", 400)
RUNIC_COMPASS: Final = (3866, "Runic Compass", 0)
CATALOG: Final = ItemCatalog(
    [
        CatalogItem.model_validate(item)
        for item in list[dict[str, JsonValue]](
            [
                {"id": 1036, "name": "Long Sword", "priceTotal": 350, "to": [3031]},
                {"id": 1038, "name": "B. F. Sword", "priceTotal": 1300, "to": [3031]},
                {"id": 1018, "name": "Cloak of Agility", "priceTotal": 600, "to": [3031]},
                {"id": 3031, "name": "Infinity Edge", "priceTotal": 3400, "from": [1038, 1018]},
                {"id": 1055, "name": "Doran's Blade", "priceTotal": 450},
                {
                    "id": 2003,
                    "name": "Health Potion",
                    "priceTotal": 50,
                    "categories": ["Consumable"],
                },
                {"id": 3865, "name": "World Atlas", "priceTotal": 400, "to": [3866]},
                # The later stages are worth what World Atlas cost, whatever the catalog says.
                {"id": 3866, "name": "Runic Compass", "priceTotal": 0, "from": [3865]},
            ]
        )
    ]
)
GAREN: Final = ("ORDER", "garen")
LEE_SIN: Final = ("ORDER", "leesin")
AHRI: Final = ("ORDER", "ahri")
DARIUS: Final = ("CHAOS", "darius")
VI_JUNGLER: Final = ("CHAOS", "vi")
ZED: Final = ("CHAOS", "zed")
LUX: Final = ("CHAOS", "lux")
CHAOS_TEAM: Final = (DARIUS, VI_JUNGLER, ZED, ("CHAOS", "caitlyn"), LUX)


class SeedChanges(TypedDict, total=False):
    items: tuple[tuple[int, str, int], ...]
    creep_score: int


def players_with(**changes_by_champion: SeedChanges) -> tuple[PlayerSeed, ...]:
    return tuple(
        dataclasses.replace(seed, **changes_by_champion.get(seed.champion_name, {}))
        for seed in DEFAULT_PLAYERS
    )


def snapshot_at(
    game_time_seconds: float,
    *,
    players: tuple[PlayerSeed, ...] = DEFAULT_PLAYERS,
    events: list[dict[str, JsonValue]] | None = None,
    current_gold: float = 500.0,
) -> GameSnapshot:
    return GameSnapshot.model_validate(
        all_game_data(game_time_seconds, events=events, players=players, current_gold=current_gold)
    )


def gold_of(estimates: dict[PlayerKey, GoldEstimate], key: PlayerKey) -> GoldEstimate:
    return estimates[key]


def test_passive_gold_starts_at_1_30_and_rises_at_15_and_25_minutes() -> None:
    assert passive_gold(90.0) == 0.0
    assert passive_gold(190.0) == pytest.approx(210.0)
    assert passive_gold(900.0) == pytest.approx(1701.0)
    assert passive_gold(1000.0) == pytest.approx(1701.0 + 230.0)
    assert passive_gold(1600.0) == pytest.approx(1701.0 + 1380.0 + 260.0)


def test_the_base_bounty_grows_by_level_from_7_to_420_at_18() -> None:
    assert [base_bounty_gold(level) for level in (1, 6, 7, 12, 18)] == [300, 300, 310, 360, 420]


def test_a_kill_pays_the_killer_and_half_of_it_to_the_assisters() -> None:
    kill = champion_kill_event(1, 300.0, "Garen Main", "Top Dog", ["Jungle Diff", "Ahri"])
    gold = feed_gold(snapshot_at(310.0, events=[game_start_event(), kill]))
    assert gold[GAREN].champion_gold == 300.0
    assert gold[LEE_SIN].champion_gold == 75.0
    assert gold[AHRI].champion_gold == 75.0
    assert DARIUS not in gold


def test_kills_since_the_last_death_raise_a_bounty_that_is_paid_once() -> None:
    victims = ["Garen Main", "Ahri", "Bot Gap"]
    streak = [
        champion_kill_event(index + 1, 100.0 * (index + 1), "Top Dog", victim, [])
        for index, victim in enumerate(victims)
    ]
    shutdown = champion_kill_event(4, 400.0, "Garen Main", "Top Dog", ["Jungle Diff"])
    second_kill = champion_kill_event(5, 500.0, "Garen Main", "Top Dog", [])
    gold = feed_gold(snapshot_at(510.0, events=[game_start_event(), *streak, shutdown]))
    # 900 gold from kills is a bounty of 900 / 3 - 100 = 200; assists share at most half the base.
    assert gold[GAREN].champion_gold == 500.0
    assert gold[LEE_SIN].champion_gold == 150.0
    after_the_shutdown = feed_gold(
        snapshot_at(510.0, events=[game_start_event(), *streak, shutdown, second_kill])
    )
    assert after_the_shutdown[GAREN].champion_gold == 800.0


def test_a_turret_pays_its_destroyers_globally_and_its_takers_locally() -> None:
    outer_top = turret_killed_event(1, 600.0, "Turret_T1_L_03_A", "Top Dog", ["Gank Plz"])
    gold = feed_gold(snapshot_at(610.0, events=[game_start_event(), outer_top]))
    assert gold[DARIUS].objective_gold == 50.0 + 125.0
    assert gold[VI_JUNGLER].objective_gold == 50.0 + 125.0
    assert gold[ZED].objective_gold == 50.0
    assert GAREN not in gold


def test_inner_turrets_inhibitors_and_baron_pay_their_own_amounts() -> None:
    events = [
        game_start_event(),
        turret_killed_event(1, 1300.0, "Turret_T2_C_04_A", "Ahri"),
        inhibitor_killed_event(2, 1400.0, "Barracks_T2_C1", "Ahri"),
        baron_kill_event(3, 1500.0, "Jungle Diff"),
    ]
    gold = feed_gold(snapshot_at(1510.0, events=events))
    assert gold[AHRI].objective_gold == 25.0 + 425.0 + 50.0 + 300.0
    assert gold[GAREN].objective_gold == 25.0 + 300.0
    assert DARIUS not in gold


def test_a_turret_a_minion_takes_alone_pays_only_the_global_gold() -> None:
    turret = turret_killed_event(1, 700.0, "Turret_T1_R_03_A", "Minion_T200L1S04N0007")
    gold = feed_gold(snapshot_at(710.0, events=[game_start_event(), turret]))
    assert [gold[key].objective_gold for key in CHAOS_TEAM] == [50.0] * 5


def test_everyone_starts_with_500_gold_exactly() -> None:
    estimates = GoldTracker().update(
        snapshot_at(20.0, players=players_with(Darius={"items": (DORANS_BLADE,)})), CATALOG
    )
    assert gold_of(estimates, DARIUS) == GoldEstimate(
        source="estimate", total_gold=500, unspent_gold=50, band_gold=0
    )


def test_with_nothing_else_gold_grows_by_passive_gold() -> None:
    darius = GoldTracker().update(snapshot_at(600.0), CATALOG)[DARIUS]
    assert darius.total_gold == 500 + 1071
    assert darius.unspent_gold == darius.total_gold
    assert 0 < darius.band_gold < 200


def test_creeps_pay_by_when_they_died() -> None:
    tracker = GoldTracker()
    tracker.update(snapshot_at(300.0, players=players_with(Zed={"creep_score": 40})), CATALOG)
    zed = tracker.update(
        snapshot_at(1000.0, players=players_with(Zed={"creep_score": 90})), CATALOG
    )[ZED]
    # 40 creeps by 5:00, counted at 2:30's rate; 50 more by 16:40, at 10:50's.
    creep_gold = 40 * 18.5 + 50 * 18.5
    assert zed.total_gold == round(500 + passive_gold(1000.0) + creep_gold)


def test_a_jungler_is_paid_by_the_jungles_rate() -> None:
    vi_gold = GoldTracker().update(
        snapshot_at(600.0, players=players_with(Vi={"creep_score": 50})), CATALOG
    )[VI_JUNGLER]
    assert vi_gold.total_gold == round(500 + passive_gold(600.0) + 50 * 22.0)


def test_nobody_owns_more_than_they_earned() -> None:
    darius = GoldTracker().update(
        snapshot_at(180.0, players=players_with(Darius={"items": (INFINITY_EDGE,)})), CATALOG
    )[DARIUS]
    assert (darius.total_gold, darius.unspent_gold) == (3400, 0)


def test_a_finished_shopping_trip_is_weighed_against_the_model() -> None:
    kills = [
        champion_kill_event(index + 1, 200.0 + index, "Top Dog", victim, [])
        for index, victim in enumerate(["Garen Main", "Ahri", "Bot Gap"])
    ]
    events = [game_start_event(), *kills]
    tracker = GoldTracker()
    before = tracker.update(snapshot_at(479.0, events=events), CATALOG)[DARIUS]
    bought = players_with(Darius={"items": (BF_SWORD,)})
    while_shopping = tracker.update(snapshot_at(480.0, players=bought, events=events), CATALOG)
    after = tracker.update(snapshot_at(486.0, players=bought, events=events), CATALOG)[DARIUS]
    # While the trip lasts, only the floor applies.
    assert while_shopping[DARIUS].band_gold == pytest.approx(before.band_gold, abs=2)
    assert while_shopping[DARIUS].unspent_gold == pytest.approx(before.total_gold - 1300, abs=3)
    # Once it ends, little is left in hand: the estimate moves toward that, and is surer.
    assert after.unspent_gold < while_shopping[DARIUS].unspent_gold - 200
    assert after.band_gold < before.band_gold


def test_a_small_purchase_is_not_a_shopping_trip() -> None:
    tracker = GoldTracker()
    with_potion = players_with(Darius={"items": (HEALTH_POTION,)})
    tracker.update(snapshot_at(479.0), CATALOG)
    tracker.update(snapshot_at(480.0, players=with_potion), CATALOG)
    darius = tracker.update(snapshot_at(486.0, players=with_potion), CATALOG)[DARIUS]
    assert darius.unspent_gold == round(500 + passive_gold(486.0) - 50)


def test_your_own_gold_is_exact() -> None:
    estimates = GoldTracker().update(
        snapshot_at(
            600.0, players=players_with(Ahri={"items": (LONG_SWORD,)}), current_gold=1234.0
        ),
        CATALOG,
    )
    assert estimates[AHRI] == GoldEstimate(
        source="exact", total_gold=1584, unspent_gold=1234, band_gold=0
    )


def test_a_drunk_potion_stays_spent() -> None:
    tracker = GoldTracker()
    two_potions = players_with(Ahri={"items": (HEALTH_POTION, HEALTH_POTION)})
    one_potion = players_with(Ahri={"items": (HEALTH_POTION,)})
    tracker.update(snapshot_at(100.0, players=two_potions, current_gold=0.0), CATALOG)
    ahri = tracker.update(snapshot_at(101.0, players=one_potion, current_gold=0.0), CATALOG)[AHRI]
    assert ahri.total_gold == 100


def test_a_sale_gives_back_seventy_percent() -> None:
    tracker = GoldTracker()
    with_edge = players_with(Darius={"items": (INFINITY_EDGE,)})
    tracker.update(snapshot_at(180.0, players=with_edge), CATALOG)
    darius = tracker.update(snapshot_at(181.0), CATALOG)[DARIUS]
    assert darius.unspent_gold == pytest.approx(0.7 * 3400, abs=5)


def test_the_support_items_quest_pins_its_gold_at_each_stage() -> None:
    with_atlas = players_with(Lux={"items": (WORLD_ATLAS,)})
    with_compass = players_with(Lux={"items": (RUNIC_COMPASS,)})
    upgraded = GoldTracker()
    upgraded.update(snapshot_at(60.0, players=with_atlas), CATALOG)
    upgraded.update(snapshot_at(359.0, players=with_atlas), CATALOG)
    upgraded.update(snapshot_at(360.0, players=with_compass), CATALOG)
    lux_upgraded = upgraded.update(snapshot_at(480.0, players=with_compass), CATALOG)[LUX]
    still_atlas = GoldTracker()
    still_atlas.update(snapshot_at(60.0, players=with_atlas), CATALOG)
    lux_atlas = still_atlas.update(snapshot_at(480.0, players=with_atlas), CATALOG)[LUX]
    base_gold = 500 + passive_gold(480.0) - 400
    # The quest's 400 gold at 6:00 is a rate of 400 / 270 s, carried on to 8:00.
    assert lux_upgraded.unspent_gold == pytest.approx(base_gold + 400 + 120 * 400 / 270, abs=2)
    assert lux_atlas.unspent_gold == pytest.approx(base_gold + 0.75 * 390, abs=2)


def test_the_first_stages_quest_gold_stops_at_its_threshold() -> None:
    lux = GoldTracker().update(
        snapshot_at(1200.0, players=players_with(Lux={"items": (WORLD_ATLAS,)})), CATALOG
    )[LUX]
    assert lux.unspent_gold == round(500 + passive_gold(1200.0) - 400 + 400)


def test_your_own_gold_tunes_creep_gold_for_players_of_your_kind() -> None:
    farmed = players_with(
        Ahri={"creep_score": 100}, Zed={"creep_score": 100}, Vi={"creep_score": 100}
    )
    modelled_ahri_gold = 500 + passive_gold(600.0) + 100 * 18.5
    honest = GoldTracker().update(
        snapshot_at(600.0, players=farmed, current_gold=modelled_ahri_gold), CATALOG
    )
    richer = GoldTracker().update(
        snapshot_at(600.0, players=farmed, current_gold=modelled_ahri_gold + 1000), CATALOG
    )
    assert honest[ZED].total_gold == round(modelled_ahri_gold)
    # Ahri's creeps paid 2850 rather than 1850: weighed against the model, that is +33% at most.
    assert richer[ZED].total_gold == pytest.approx(500 + passive_gold(600.0) + 1850 * 1.33, abs=1)
    assert richer[VI_JUNGLER].total_gold == honest[VI_JUNGLER].total_gold


def test_a_new_game_starts_the_tracker_over() -> None:
    tracker = GoldTracker()
    tracker.update(
        snapshot_at(1200.0, players=players_with(Darius={"items": (INFINITY_EDGE,)})), CATALOG
    )
    darius = tracker.update(snapshot_at(10.0), CATALOG)[DARIUS]
    assert darius.total_gold == 500


def test_the_chance_of_affording_follows_the_band() -> None:
    # A band of 256 gold is 200 gold of standard deviation.
    estimate = GoldEstimate(source="estimate", total_gold=3000, unspent_gold=1000, band_gold=256)
    assert chance_of_affording(estimate, 1000) == pytest.approx(0.5, abs=0.01)
    assert chance_of_affording(estimate, 600) == pytest.approx(0.977, abs=0.01)
    assert chance_of_affording(estimate, 1400) == pytest.approx(0.023, abs=0.01)
    exact = GoldEstimate(source="exact", total_gold=3000, unspent_gold=1000, band_gold=0)
    assert [chance_of_affording(exact, cost) for cost in (999, 1000, 1001)] == [1.0, 1.0, 0.0]


def card_with_gold(side: str, total_gold: int, band_gold: int) -> PlayerCard:
    return PlayerCard.model_validate(
        {
            "champion_name": "Garen",
            "side": side,
            "position": "",
            "level": 1,
            "is_dead": False,
            "respawns_at_game_time_seconds": None,
            "gold": {
                "source": "exact" if band_gold == 0 else "estimate",
                "total_gold": total_gold,
                "unspent_gold": 0,
                "band_gold": band_gold,
            },
        }
    )


def test_team_gold_sums_each_side_and_the_bands_in_quadrature() -> None:
    cards = [
        card_with_gold("ally", 5000, 0),
        card_with_gold("ally", 4000, 300),
        card_with_gold("enemy", 6000, 400),
    ]
    totals = team_gold(cards)
    assert totals is not None
    assert (totals.ally_total_gold, totals.enemy_total_gold, totals.lead_band_gold) == (
        9000,
        6000,
        500,
    )
    assert team_gold([*cards, cards[0].model_copy(update={"gold": None})]) is None


def test_the_overlay_shows_each_players_gold_and_the_teams() -> None:
    tracker = GoldTracker()
    state = compute_overlay_state(all_game_data(600.0), CATALOG, gold_tracker=tracker)
    gold_by_champion = {card.champion_name: card.gold for card in state.players}
    assert all(gold is not None for gold in gold_by_champion.values())
    assert gold_by_champion["Ahri"] == GoldEstimate(
        source="exact", total_gold=500, unspent_gold=500, band_gold=0
    )
    zed_gold = gold_by_champion["Zed"]
    assert zed_gold is not None
    assert zed_gold.source == "estimate"
    assert state.team_gold is not None
    assert state.team_gold.enemy_total_gold == 5 * zed_gold.total_gold
    assert compute_overlay_state(all_game_data(600.0), CATALOG).team_gold is None
