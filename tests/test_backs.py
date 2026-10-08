import dataclasses
from typing import Final, TypedDict

import pytest

from data_dragon_fixtures import fixture_patch_stats
from game_payloads import DEFAULT_PLAYERS, all_game_data
from leagueasymode.data_dragon import PatchStats
from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.backs import BackTracker
from leagueasymode.inference.callouts import CalloutTracker
from leagueasymode.inference.gold import PlayerKey
from leagueasymode.overlay_state import BackEstimate, OverlayState, PlayerCard

ZED: Final = ("CHAOS", "zed")
CAITLYN: Final = ("CHAOS", "caitlyn")
VI_JUNGLER: Final = ("CHAOS", "vi")
LONG_SWORD: Final = (1036, "Long Sword", 350)
BF_SWORD: Final = (1038, "B. F. Sword", 1300)
HEALTH_POTION: Final = (2003, "Health Potion", 50)
# Without the patch's stats, a player moves at 380 a second.
DEFAULT_MOVE_SPEED: Final = 380.0
SHOPPING_SECONDS: Final = 5.0


class SeedChanges(TypedDict, total=False):
    items: tuple[tuple[int, str, int], ...]
    is_dead: bool
    respawn_timer_seconds: float


def observe(
    tracker: BackTracker,
    game_time_seconds: float,
    patch_stats: PatchStats | None = None,
    **changes_by_champion: SeedChanges,
) -> dict[PlayerKey, BackEstimate]:
    players = tuple(
        dataclasses.replace(seed, **changes_by_champion.get(seed.champion_name, {}))
        for seed in DEFAULT_PLAYERS
    )
    snapshot = GameSnapshot.model_validate(all_game_data(game_time_seconds, players=players))
    return tracker.update(snapshot, None, patch_stats)


def test_a_purchase_while_alive_is_a_back() -> None:
    tracker = BackTracker()
    assert observe(tracker, 400.0) == {}
    zed = observe(tracker, 460.0, Zed={"items": (LONG_SWORD,)})[ZED]
    assert zed.shopped_at_game_time_seconds == 460.0
    # Mid is 7,500 units from the fountain.
    assert zed.returns_at_game_time_seconds == pytest.approx(
        460.0 + SHOPPING_SECONDS + 7500 / DEFAULT_MOVE_SPEED
    )


def test_shopping_at_the_start_is_not_a_back() -> None:
    tracker = BackTracker()
    observe(tracker, 5.0)
    assert observe(tracker, 20.0, Zed={"items": (LONG_SWORD,)}) == {}


def test_shopping_while_dead_is_not_a_back() -> None:
    tracker = BackTracker()
    observe(tracker, 400.0, Zed={"is_dead": True, "respawn_timer_seconds": 20.0})
    dead_and_shopping = SeedChanges(items=(LONG_SWORD,), is_dead=True, respawn_timer_seconds=10.0)
    assert observe(tracker, 410.0, Zed=dead_and_shopping) == {}


def test_shopping_right_after_respawning_is_not_a_back() -> None:
    tracker = BackTracker()
    observe(tracker, 400.0, Zed={"is_dead": True, "respawn_timer_seconds": 20.0})
    observe(tracker, 420.0)
    assert observe(tracker, 425.0, Zed={"items": (LONG_SWORD,)}) == {}
    # Once they have been alive a while, a purchase is a back again.
    assert ZED in observe(tracker, 600.0, Zed={"items": (LONG_SWORD, BF_SWORD)})


def test_one_trip_is_one_back_and_the_next_trip_another() -> None:
    tracker = BackTracker()
    observe(tracker, 400.0)
    observe(tracker, 460.0, Zed={"items": (LONG_SWORD,)})
    same_trip = observe(tracker, 465.0, Zed={"items": (LONG_SWORD, HEALTH_POTION)})
    assert same_trip[ZED].shopped_at_game_time_seconds == 460.0
    next_trip = observe(tracker, 700.0, Zed={"items": (LONG_SWORD, HEALTH_POTION, BF_SWORD)})
    assert next_trip[ZED].shopped_at_game_time_seconds == 700.0


def test_a_potion_drunk_is_not_a_back() -> None:
    tracker = BackTracker()
    observe(tracker, 400.0, Zed={"items": (HEALTH_POTION,)})
    assert observe(tracker, 460.0) == {}


def test_the_way_back_depends_on_where_they_play() -> None:
    tracker = BackTracker()
    observe(tracker, 400.0)
    backs = observe(tracker, 460.0, Caitlyn={"items": (LONG_SWORD,)}, Vi={"items": (LONG_SWORD,)})
    # Bottom is 10,000 units from the fountain; the jungle 5,500.
    assert backs[CAITLYN].returns_at_game_time_seconds == pytest.approx(
        460.0 + SHOPPING_SECONDS + 10000 / DEFAULT_MOVE_SPEED
    )
    assert backs[VI_JUNGLER].returns_at_game_time_seconds == pytest.approx(
        460.0 + SHOPPING_SECONDS + 5500 / DEFAULT_MOVE_SPEED
    )


def test_the_way_back_is_at_their_estimated_move_speed() -> None:
    tracker = BackTracker()
    observe(tracker, 400.0, fixture_patch_stats())
    zed = observe(tracker, 460.0, fixture_patch_stats(), Zed={"items": (LONG_SWORD,)})[ZED]
    assert zed.returns_at_game_time_seconds == pytest.approx(460.0 + SHOPPING_SECONDS + 7500 / 345)


def test_a_new_game_starts_the_tracker_over() -> None:
    tracker = BackTracker()
    observe(tracker, 400.0)
    observe(tracker, 460.0, Zed={"items": (LONG_SWORD,)})
    assert observe(tracker, 10.0) == {}


def test_the_overlay_shows_each_players_last_back() -> None:
    tracker = BackTracker()
    compute_overlay_state(all_game_data(400.0), back_tracker=tracker)
    players = tuple(
        dataclasses.replace(seed, items=(LONG_SWORD,)) if seed.champion_name == "Zed" else seed
        for seed in DEFAULT_PLAYERS
    )
    state = compute_overlay_state(all_game_data(460.0, players=players), back_tracker=tracker)
    last_backs = {card.champion_name: card.last_back for card in state.players}
    assert last_backs["Zed"] is not None
    assert last_backs["Caitlyn"] is None


def jungler_card(last_back: BackEstimate | None) -> PlayerCard:
    return PlayerCard(
        champion_name="Vi",
        side="enemy",
        position="JUNGLE",
        role="JUNGLE",
        role_confidence="given",
        level=7,
        is_dead=False,
        respawns_at_game_time_seconds=None,
        last_back=last_back,
    )


def state_with(game_time_seconds: float, card: PlayerCard) -> OverlayState:
    return OverlayState(is_game_running=True, game_time_seconds=game_time_seconds, players=[card])


def test_the_enemy_junglers_back_is_called_out() -> None:
    callouts = CalloutTracker()
    assert callouts.update(state_with(459.0, jungler_card(None))) == []
    back = BackEstimate(shopped_at_game_time_seconds=460.0, returns_at_game_time_seconds=479.5)
    made = callouts.update(state_with(460.0, jungler_card(back)))
    assert [(callout.kind, callout.text) for callout in made] == [
        ("went_back", "Vi went back: in the jungle again in ~0:20")
    ]


def test_a_back_already_made_when_the_overlay_starts_is_not_called_out() -> None:
    callouts = CalloutTracker()
    back = BackEstimate(shopped_at_game_time_seconds=460.0, returns_at_game_time_seconds=479.5)
    assert callouts.update(state_with(470.0, jungler_card(back))) == []
    assert callouts.update(state_with(471.0, jungler_card(back))) == []
