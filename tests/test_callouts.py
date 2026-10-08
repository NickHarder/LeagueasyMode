from leagueasymode.inference.callouts import CALLOUT_SHOWN_SECONDS, CalloutTracker
from leagueasymode.overlay_state import (
    DragonTimer,
    NumbersWindow,
    ObjectiveTimer,
    OverlayState,
    PlayerCard,
)


def enemy(champion_name: str, level: int) -> PlayerCard:
    return PlayerCard(
        champion_name=champion_name,
        side="enemy",
        position="MIDDLE",
        level=level,
        is_dead=False,
        respawns_at_game_time_seconds=None,
    )


def dragon_spawning_at(spawns_at_seconds: float) -> DragonTimer:
    return DragonTimer(
        objective="dragon",
        status="respawning",
        spawns_at_game_time_seconds=spawns_at_seconds,
        ally_dragon_count=0,
        enemy_dragon_count=1,
        soul_type=None,
        soul_holder=None,
    )


def state_at(
    game_time_seconds: float,
    players: list[PlayerCard] | None = None,
    numbers_window: NumbersWindow | None = None,
    dragon: DragonTimer | None = None,
    objectives: list[ObjectiveTimer] | None = None,
) -> OverlayState:
    return OverlayState(
        is_game_running=True,
        game_time_seconds=game_time_seconds,
        dragon=dragon,
        objectives=objectives or [],
        players=players or [],
        numbers_window=numbers_window,
    )


def test_an_enemy_reaching_level_six_is_called_out_once() -> None:
    tracker = CalloutTracker()
    assert tracker.update(state_at(400.0, [enemy("Zed", 5)])) == []
    first = tracker.update(state_at(401.0, [enemy("Zed", 6)]))
    assert [callout.text for callout in first] == ["Zed is level 6"]
    assert first[0].kind == "level_spike"
    again = tracker.update(state_at(402.0, [enemy("Zed", 6)]))
    assert [callout.callout_id for callout in again] == [first[0].callout_id]


def test_a_callout_is_shown_for_a_few_seconds_then_gone() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(400.0, [enemy("Zed", 10)]))
    shown = tracker.update(state_at(401.0, [enemy("Zed", 11)]))
    assert shown[0].shown_until_game_time_seconds == 401.0 + CALLOUT_SHOWN_SECONDS
    assert tracker.update(state_at(401.0 + CALLOUT_SHOWN_SECONDS + 0.5, [enemy("Zed", 11)])) == []


def test_levels_already_reached_when_the_overlay_starts_are_not_called_out() -> None:
    assert CalloutTracker().update(state_at(1200.0, [enemy("Zed", 16)])) == []


def test_a_numbers_window_opening_is_called_out() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(900.0))
    window = NumbersWindow(ally_dead_count=0, enemy_dead_count=2, ends_at_game_time_seconds=925.0)
    callouts = tracker.update(state_at(901.0, numbers_window=window))
    assert [(callout.kind, callout.text) for callout in callouts] == [
        ("numbers_window", "2 enemies down for 0:24")
    ]


def test_an_objective_a_minute_away_is_called_out() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(630.0, dragon=dragon_spawning_at(700.0)))
    callouts = tracker.update(state_at(641.0, dragon=dragon_spawning_at(700.0)))
    assert [(callout.kind, callout.text) for callout in callouts] == [
        ("objective_soon", "Dragon in 1:00")
    ]


def test_a_provisional_spawn_time_is_called_out_as_such() -> None:
    baron = ObjectiveTimer(
        objective="baron",
        status="not_spawned",
        spawns_at_game_time_seconds=1200.0,
        is_rule_verified=False,
    )
    tracker = CalloutTracker()
    tracker.update(state_at(1130.0, objectives=[baron]))
    callouts = tracker.update(state_at(1141.0, objectives=[baron]))
    assert [callout.text for callout in callouts] == ["Baron in ~1:00"]


def test_a_new_game_starts_the_callouts_over() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(400.0, [enemy("Zed", 5)]))
    tracker.update(state_at(401.0, [enemy("Zed", 6)]))
    tracker.update(state_at(10.0, [enemy("Zed", 5)]))
    callouts = tracker.update(state_at(11.0, [enemy("Zed", 6)]))
    assert [callout.text for callout in callouts] == ["Zed is level 6"]


def test_no_game_is_no_callout() -> None:
    assert CalloutTracker().update(OverlayState(is_game_running=False)) == []
