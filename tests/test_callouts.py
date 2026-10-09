from leagueasymode.inference.callouts import CALLOUT_SHOWN_SECONDS, CalloutTracker
from leagueasymode.overlay_state import (
    CooldownTimer,
    DragonTimer,
    LevelEstimate,
    NumbersWindow,
    ObjectiveTimer,
    OverlayState,
    PlayerCard,
    PlayerIntel,
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


def enemy_with_items(champion_name: str, finished_item_names: list[str]) -> PlayerCard:
    return enemy(champion_name, 9).model_copy(
        update={
            "item_gold": 3400 * len(finished_item_names),
            "finished_item_names": finished_item_names,
        }
    )


def test_an_enemy_finishing_an_item_is_called_out_once() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(900.0, [enemy_with_items("Caitlyn", [])]))
    callouts = tracker.update(state_at(901.0, [enemy_with_items("Caitlyn", ["Infinity Edge"])]))
    assert [(callout.kind, callout.text) for callout in callouts] == [
        ("item_spike", "Caitlyn finished Infinity Edge")
    ]
    later = tracker.update(state_at(920.0, [enemy_with_items("Caitlyn", ["Infinity Edge"])]))
    assert later == []


def test_items_owned_when_the_catalog_arrives_are_not_called_out() -> None:
    tracker = CalloutTracker()
    before_catalog = enemy("Caitlyn", 9)  # item_gold None: the catalog is not known yet
    after_catalog = enemy("Caitlyn", 9).model_copy(
        update={"item_gold": 3400, "finished_item_names": ["Infinity Edge"]}
    )
    tracker.update(state_at(900.0, [before_catalog]))
    assert tracker.update(state_at(901.0, [after_catalog])) == []


def zed_flash_timer() -> CooldownTimer:
    return CooldownTimer(
        cooldown_id="Zed-flash-600.0",
        champion_name="Zed",
        spell="flash",
        spell_name="Flash",
        label="F",
        marked_at_game_time_seconds=600.0,
        ready_at_game_time_seconds=900.0,
    )


def test_a_marked_spell_coming_back_is_called_out_once() -> None:
    tracker = CalloutTracker()
    running = state_at(899.5).model_copy(update={"cooldowns": [zed_flash_timer()]})
    assert tracker.update(running) == []
    back = tracker.update(state_at(900.0))
    assert [callout.text for callout in back] == ["Zed's Flash is up"]
    assert back[0].kind == "cooldown_ready"
    assert [callout.text for callout in tracker.update(state_at(900.5))] == ["Zed's Flash is up"]


def test_a_marked_ultimate_coming_back_is_called_out_by_name() -> None:
    tracker = CalloutTracker()
    ultimate = zed_flash_timer().model_copy(
        update={"cooldown_id": "Zed-ultimate-600.0", "spell": "ultimate", "spell_name": "ultimate"}
    )
    tracker.update(state_at(899.5).model_copy(update={"cooldowns": [ultimate]}))
    assert [callout.text for callout in tracker.update(state_at(900.0))] == ["Zed's ultimate is up"]


def enemy_close_to_six(
    game_time_seconds: float, seconds_to_six: float, band_seconds: float
) -> PlayerCard:
    return enemy("Zed", 5).model_copy(
        update={
            "level_estimate": LevelEstimate(
                experience=2300,
                band_experience=round(band_seconds * 9),
                progress_to_next_level=580 / 680,
                next_power_level=6,
                power_level_at_game_time_seconds=game_time_seconds + seconds_to_six,
                power_level_band_seconds=band_seconds,
            )
        }
    )


def test_an_enemy_close_to_a_power_level_is_called_out_once() -> None:
    tracker = CalloutTracker()
    assert tracker.update(state_at(300.0, [enemy_close_to_six(300.0, 30.0, 10.0)])) == []
    soon = tracker.update(state_at(310.0, [enemy_close_to_six(310.0, 15.0, 10.0)]))
    assert [(callout.kind, callout.text) for callout in soon] == [
        ("level_soon", "Zed hits 6 in ~0:15")
    ]
    again = tracker.update(state_at(312.0, [enemy_close_to_six(312.0, 13.0, 10.0)]))
    assert [callout.callout_id for callout in again] == [soon[0].callout_id]


def test_an_unsure_estimate_of_a_power_level_is_not_called_out() -> None:
    tracker = CalloutTracker()
    tracker.update(state_at(300.0, [enemy_close_to_six(300.0, 30.0, 40.0)]))
    assert tracker.update(state_at(310.0, [enemy_close_to_six(310.0, 15.0, 40.0)])) == []


def enemy_jungler(
    start_count: int, start_games: int, role: str = "JUNGLE", four_minute_count: int = 0
) -> PlayerCard:
    return PlayerCard(
        champion_name="Vi",
        side="enemy",
        position="",
        role=role,
        role_confidence="likely",
        level=1,
        is_dead=False,
        respawns_at_game_time_seconds=None,
        intel=PlayerIntel(
            ranked=None,
            recent_game_count=start_games,
            recent_win_count=0,
            streak=0,
            champion_game_count=0,
            champion_win_count=0,
            usual_position="JUNGLE",
            is_off_role=False,
            jungle_start_side="red",
            jungle_start_half="top",
            jungle_start_count=start_count,
            jungle_start_games=start_games,
            four_minute_half="bot" if four_minute_count else None,
            four_minute_count=four_minute_count,
            four_minute_games=start_games if four_minute_count else 0,
        ),
    )


def test_where_the_enemy_jungler_usually_starts_is_called_out_before_the_camps_spawn() -> None:
    tracker = CalloutTracker()
    first = tracker.update(state_at(20.0, [enemy_jungler(3, 4)]))
    assert [(callout.kind, callout.text) for callout in first] == [
        ("jungle_start", "Vi usually starts red, top side (3 of 4)")
    ]
    again = tracker.update(state_at(21.0, [enemy_jungler(3, 4)]))
    assert [callout.callout_id for callout in again] == [first[0].callout_id]


def test_a_jungle_start_is_not_called_out_once_the_camps_are_up() -> None:
    assert CalloutTracker().update(state_at(95.0, [enemy_jungler(3, 4)])) == []


def test_a_jungler_with_no_clear_habit_or_another_role_is_not_called_out() -> None:
    assert CalloutTracker().update(state_at(20.0, [enemy_jungler(3, 5)])) == []
    assert CalloutTracker().update(state_at(20.0, [enemy_jungler(1, 1)])) == []
    assert CalloutTracker().update(state_at(20.0, [enemy_jungler(3, 4, role="TOP")])) == []


def test_where_the_enemy_jungler_usually_is_at_four_minutes_is_called_out_before_it() -> None:
    tracker = CalloutTracker()
    assert tracker.update(state_at(150.0, [enemy_jungler(3, 4, four_minute_count=3)])) == []
    soon = tracker.update(state_at(170.0, [enemy_jungler(3, 4, four_minute_count=3)]))
    assert [(callout.kind, callout.text) for callout in soon] == [
        ("jungle_four_minutes", "Vi is usually bot side at 4:00 (3 of 4)")
    ]


def test_a_four_minute_habit_is_not_called_out_late_or_when_unclear() -> None:
    assert (
        CalloutTracker().update(state_at(215.0, [enemy_jungler(3, 4, four_minute_count=3)])) == []
    )
    assert (
        CalloutTracker().update(state_at(170.0, [enemy_jungler(3, 5, four_minute_count=3)])) == []
    )
