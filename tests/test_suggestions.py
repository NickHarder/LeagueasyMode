from typing import Final

from leagueasymode.inference.callouts import CalloutTracker
from leagueasymode.overlay_state import (
    BuffTimer,
    CooldownTimer,
    DragonTimer,
    NumbersWindow,
    ObjectiveTimer,
    OverlayState,
    PlayerCard,
)

BARON_UP: Final = ObjectiveTimer(
    objective="baron", status="alive", spawns_at_game_time_seconds=1200.0, is_rule_verified=True
)
TWO_DOWN_UNTIL_1440: Final = NumbersWindow(
    ally_dead_count=0, enemy_dead_count=2, ends_at_game_time_seconds=1440.0
)


def dragon_at(status: str, spawns_at_seconds: float) -> DragonTimer:
    return DragonTimer.model_validate(
        {
            "objective": "dragon",
            "status": status,
            "spawns_at_game_time_seconds": spawns_at_seconds,
            "ally_dragon_count": 1,
            "enemy_dragon_count": 1,
            "soul_type": None,
            "soul_holder": None,
        }
    )


def enemy_jungler(respawns_at_seconds: float | None) -> PlayerCard:
    return PlayerCard(
        champion_name="Vi",
        side="enemy",
        position="JUNGLE",
        role="JUNGLE",
        role_confidence="given",
        level=9,
        is_dead=respawns_at_seconds is not None,
        respawns_at_game_time_seconds=respawns_at_seconds,
    )


def state_at(game_time_seconds: float, **fields: object) -> OverlayState:
    return OverlayState.model_validate(
        {"is_game_running": True, "game_time_seconds": game_time_seconds, **fields}
    )


def suggestion_texts(tracker: CalloutTracker, state: OverlayState) -> list[str]:
    return [callout.text for callout in tracker.update(state) if callout.kind == "suggestion"]


def test_an_objective_up_while_enemies_are_down_is_suggested_once() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(1399.0, objectives=[BARON_UP]))
    with_window = state_at(1400.0, objectives=[BARON_UP], numbers_window=TWO_DOWN_UNTIL_1440)
    assert suggestion_texts(tracker, with_window) == ["Baron up, 2 enemies down for 0:40: take it"]
    later = state_at(1401.0, objectives=[BARON_UP], numbers_window=TWO_DOWN_UNTIL_1440)
    # Still shown, not made again.
    assert suggestion_texts(tracker, later) == ["Baron up, 2 enemies down for 0:40: take it"]


def test_an_objective_about_to_spawn_counts_too() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(1399.0))
    soon = state_at(
        1400.0, dragon=dragon_at("respawning", 1420.0), numbers_window=TWO_DOWN_UNTIL_1440
    )
    assert "Dragon in 0:20, 2 enemies down for 0:40: take it" in suggestion_texts(tracker, soon)


def test_no_suggestion_without_enough_time_or_an_objective_near() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(1399.0))
    short_window = NumbersWindow(
        ally_dead_count=0, enemy_dead_count=2, ends_at_game_time_seconds=1410.0
    )
    assert (
        suggestion_texts(
            tracker, state_at(1400.0, objectives=[BARON_UP], numbers_window=short_window)
        )
        == []
    )
    far_dragon = dragon_at("respawning", 1600.0)
    assert (
        suggestion_texts(
            tracker, state_at(1401.0, dragon=far_dragon, numbers_window=TWO_DOWN_UNTIL_1440)
        )
        == []
    )


def test_their_jungler_down_opens_an_objective() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(1399.0, players=[enemy_jungler(None)]))
    jungler_down = state_at(
        1400.0, players=[enemy_jungler(1435.0)], dragon=dragon_at("alive", 1300.0)
    )
    assert suggestion_texts(tracker, jungler_down) == [
        "Their jungler is down for 0:35: take Dragon"
    ]


def test_their_jungler_down_with_no_objective_near_opens_their_jungle() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(1399.0, players=[enemy_jungler(None)]))
    jungler_down = state_at(1400.0, players=[enemy_jungler(1430.0)])
    assert suggestion_texts(tracker, jungler_down) == [
        "Their jungler is down for 0:30: invade or push"
    ]


def test_their_jungler_back_soon_is_no_suggestion() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(1399.0, players=[enemy_jungler(None)]))
    assert suggestion_texts(tracker, state_at(1400.0, players=[enemy_jungler(1410.0)])) == []


def flash_timer(spell: str) -> CooldownTimer:
    return CooldownTimer.model_validate(
        {
            "cooldown_id": f"Zed-{spell}-1400.0",
            "champion_name": "Zed",
            "spell": spell,
            "spell_name": "Flash" if spell == "flash" else "ultimate",
            "label": "F" if spell == "flash" else "R",
            "marked_at_game_time_seconds": 1400.0,
            "ready_at_game_time_seconds": 1700.0 if spell == "flash" else 1520.0,
        }
    )


def test_a_marked_flash_is_a_chance_to_punish() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(1399.0))
    assert suggestion_texts(tracker, state_at(1400.0, cooldowns=[flash_timer("flash")])) == [
        "Zed has no Flash for 5:00: punish it"
    ]


def test_a_marked_ultimate_is_a_window_to_fight() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(1399.0))
    assert suggestion_texts(tracker, state_at(1400.0, cooldowns=[flash_timer("ultimate")])) == [
        "Zed has no ultimate for 2:00: fight now"
    ]


def test_a_baron_buff_says_whether_to_push_or_defend() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(1399.0))
    enemy_buff = BuffTimer(buff="baron", holder="enemy", ends_at_game_time_seconds=1580.0)
    assert suggestion_texts(tracker, state_at(1400.0, buffs=[enemy_buff])) == [
        "They have Baron for 3:00: group and defend"
    ]
    ally_tracker = CalloutTracker()
    ally_tracker.update(state_at(1399.0))
    ally_buff = BuffTimer(buff="baron", holder="ally", ends_at_game_time_seconds=1580.0)
    assert suggestion_texts(ally_tracker, state_at(1400.0, buffs=[ally_buff])) == [
        "You have Baron for 3:00: group and push"
    ]


def test_nothing_is_suggested_on_the_first_state_seen() -> None:
    tracker = CalloutTracker()
    first = state_at(1400.0, objectives=[BARON_UP], numbers_window=TWO_DOWN_UNTIL_1440)
    assert suggestion_texts(tracker, first) == []


def test_an_elder_buff_says_whether_to_force_or_avoid_a_fight() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(2399.0))
    enemy_elder = BuffTimer(buff="elder", holder="enemy", ends_at_game_time_seconds=2550.0)
    assert suggestion_texts(tracker, state_at(2400.0, buffs=[enemy_elder])) == [
        "They have Elder for 2:30: avoid fights"
    ]
    ally_tracker = CalloutTracker()
    ally_tracker.update(state_at(2399.0))
    ally_elder = BuffTimer(buff="elder", holder="ally", ends_at_game_time_seconds=2550.0)
    assert suggestion_texts(ally_tracker, state_at(2400.0, buffs=[ally_elder])) == [
        "You have Elder for 2:30: force a fight"
    ]
