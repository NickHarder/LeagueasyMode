"""Suggestions: callouts that name an action when the facts line up.

The owner's answer of 2026-10-08 allows the overlay to tell the player what to do. Each suggestion
is a rule over facts the overlay already has, made once when its facts first line up and shown like
any callout. The wording is a first draft for the owner to tune, and it is text only to start.

- An objective up, or spawning within 30 seconds, while more enemies than allies are dead for at
  least 20 more seconds: take it.
- Their jungler dead for at least 20 more seconds: take an objective that is up or spawning within a
  minute, or else invade or push.
- A Flash or an ultimate the player has just marked: punish it, or fight now.
- A Baron or Elder buff just taken: push or defend, force a fight or avoid one.
"""

import math
from typing import Final

from pydantic import BaseModel, ConfigDict

from leagueasymode.overlay_state import (
    BuffTimer,
    Callout,
    DragonTimer,
    ObjectiveTimer,
    OverlayState,
    PlayerCard,
)

SECONDS_PER_MINUTE: Final = 60
OBJECTIVE_NAMES: Final = {
    "dragon": "Dragon",
    "elder_dragon": "Elder",
    "baron": "Baron",
    "rift_herald": "Herald",
    "voidgrubs": "Voidgrubs",
}
BUFF_NAMES: Final = {"baron": "Baron", "elder": "Elder"}
BUFF_ADVICE: Final = {
    ("baron", "ally"): "group and push",
    ("baron", "enemy"): "group and defend",
    ("elder", "ally"): "force a fight",
    ("elder", "enemy"): "avoid fights",
}
KNOWN_ROLE_CONFIDENCES: Final = frozenset({"given", "likely"})


class SuggestionRules(BaseModel):
    """The suggestions' hand-set thresholds: `tuning.json`'s "suggestions"."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # How long a suggestion shows, in game seconds.
    shown_seconds: float = 6.0
    # An objective spawning within this is as good as up for a numbers window.
    objective_window_seconds: float = 30.0
    # A window shorter than this is too short to walk to an objective and take it.
    shortest_usable_seconds: float = 20.0
    # With their jungler down, an objective spawning within this is worth taking.
    jungler_objective_seconds: float = 60.0


SUGGESTION_RULES: Final = SuggestionRules()


def suggestions(
    previous_state: OverlayState | None,
    state: OverlayState,
    game_time_seconds: float,
    rules: SuggestionRules = SUGGESTION_RULES,
) -> list[Callout]:
    """Return the suggestions whose facts line up in a state.

    Nothing is suggested from the first state seen, whose facts may be long under way.

    Args:
        previous_state: The last state, or None when this is the first of the game.
        state: The new state.
        game_time_seconds: Its game time.
        rules: The hand-set thresholds.

    Returns:
        The suggestions; the caller makes each one only once.
    """
    if previous_state is None:
        return []
    return [
        *_objective_windows(state, game_time_seconds, rules),
        *_jungler_down(state, game_time_seconds, rules),
        *_spells_down(previous_state, state, game_time_seconds),
        *_buffs_taken(previous_state, state, game_time_seconds),
    ]


def _objective_windows(
    state: OverlayState, game_time_seconds: float, rules: SuggestionRules
) -> list[Callout]:
    """Suggest taking an objective that is up, or about to be, while enemies are down.

    Args:
        state: The new state.
        game_time_seconds: Its game time.
        rules: The hand-set thresholds.

    Returns:
        One suggestion per such objective.
    """
    window = state.numbers_window
    if window is None:
        return []
    window_seconds_left = window.ends_at_game_time_seconds - game_time_seconds
    if window_seconds_left < rules.shortest_usable_seconds:
        return []
    enemy_text = "enemy" if window.enemy_dead_count == 1 else "enemies"
    return [
        _suggestion(
            f"suggest:objective:{objective_name}:{spawns_at_seconds:.0f}:"
            f"{window.ends_at_game_time_seconds:.0f}:{window.enemy_dead_count}",
            f"{_objective_text(objective_name, spawns_at_seconds, game_time_seconds)}, "
            f"{window.enemy_dead_count} {enemy_text} down for {_clock_text(window_seconds_left)}: "
            "take it",
            game_time_seconds,
        )
        for objective_name, spawns_at_seconds in _objectives_within(
            state, game_time_seconds, rules.objective_window_seconds
        )
    ]


def _jungler_down(
    state: OverlayState, game_time_seconds: float, rules: SuggestionRules
) -> list[Callout]:
    """Suggest using the time their jungler is dead.

    Args:
        state: The new state.
        game_time_seconds: Its game time.
        rules: The hand-set thresholds.

    Returns:
        The suggestion, or nothing.
    """
    jungler = next((card for card in state.players if _is_enemy_jungler(card)), None)
    if jungler is None or not jungler.is_dead or jungler.respawns_at_game_time_seconds is None:
        return []
    seconds_down = jungler.respawns_at_game_time_seconds - game_time_seconds
    if seconds_down < rules.shortest_usable_seconds:
        return []
    near_objectives = _objectives_within(state, game_time_seconds, rules.jungler_objective_seconds)
    advice = (
        f"take {OBJECTIVE_NAMES[near_objectives[0][0]]}" if near_objectives else "invade or push"
    )
    return [
        _suggestion(
            f"suggest:jungler:{jungler.respawns_at_game_time_seconds:.0f}",
            f"Their jungler is down for {_clock_text(seconds_down)}: {advice}",
            game_time_seconds,
        )
    ]


def _spells_down(
    previous_state: OverlayState, state: OverlayState, game_time_seconds: float
) -> list[Callout]:
    """Suggest using a Flash or an ultimate the player has just marked an enemy as having used.

    Args:
        previous_state: The last state.
        state: The new state.
        game_time_seconds: Its game time.

    Returns:
        One suggestion per new mark of a Flash or an ultimate.
    """
    previous_ids = {timer.cooldown_id for timer in previous_state.cooldowns}
    return [
        _suggestion(
            f"suggest:spell:{timer.cooldown_id}",
            f"{timer.champion_name} has no {timer.spell_name} for "
            f"{_clock_text(timer.ready_at_game_time_seconds - game_time_seconds)}: "
            + ("punish it" if timer.spell == "flash" else "fight now"),
            game_time_seconds,
        )
        for timer in state.cooldowns
        if timer.cooldown_id not in previous_ids and timer.spell in {"flash", "ultimate"}
    ]


def _buffs_taken(
    previous_state: OverlayState, state: OverlayState, game_time_seconds: float
) -> list[Callout]:
    """Suggest what a Baron or Elder buff just taken calls for, by who holds it.

    Args:
        previous_state: The last state.
        state: The new state.
        game_time_seconds: Its game time.

    Returns:
        One suggestion per new buff.
    """
    previous_buffs = {_buff_key(buff) for buff in previous_state.buffs}
    return [
        _suggestion(
            f"suggest:buff:{buff.buff}:{buff.holder}:{buff.ends_at_game_time_seconds:.0f}",
            f"{'You have' if buff.holder == 'ally' else 'They have'} {BUFF_NAMES[buff.buff]} for "
            f"{_clock_text(buff.ends_at_game_time_seconds - game_time_seconds)}: "
            f"{BUFF_ADVICE[buff.buff, buff.holder]}",
            game_time_seconds,
        )
        for buff in state.buffs
        if _buff_key(buff) not in previous_buffs
    ]


def _objectives_within(
    state: OverlayState, game_time_seconds: float, within_seconds: float
) -> list[tuple[str, float]]:
    """Return the objectives up, or spawning within some seconds, with their spawn time.

    Args:
        state: The state.
        game_time_seconds: Its game time.
        within_seconds: How soon a spawn counts.

    Returns:
        Each objective's name and spawn time, the dragon first.
    """
    timers: list[DragonTimer | ObjectiveTimer] = [
        *([state.dragon] if state.dragon is not None else []),
        *state.objectives,
    ]
    return [
        (timer.objective, timer.spawns_at_game_time_seconds)
        for timer in timers
        if timer.spawns_at_game_time_seconds is not None
        and (
            timer.status == "alive"
            or 0 < timer.spawns_at_game_time_seconds - game_time_seconds <= within_seconds
        )
    ]


def _objective_text(objective_name: str, spawns_at_seconds: float, game_time_seconds: float) -> str:
    """Return how an objective stands: "Baron up" or "Dragon in 0:20".

    Args:
        objective_name: The objective.
        spawns_at_seconds: When it spawns or spawned.
        game_time_seconds: Now.

    Returns:
        The text.
    """
    name = OBJECTIVE_NAMES[objective_name]
    if spawns_at_seconds <= game_time_seconds:
        return f"{name} up"
    return f"{name} in {_clock_text(spawns_at_seconds - game_time_seconds)}"


def _is_enemy_jungler(card: PlayerCard) -> bool:
    """Return whether a card is the enemy jungler, given or likely.

    Args:
        card: A player's card.

    Returns:
        Whether it is.
    """
    return (
        card.side == "enemy"
        and card.role == "JUNGLE"
        and card.role_confidence in KNOWN_ROLE_CONFIDENCES
    )


def _buff_key(buff: BuffTimer) -> tuple[str, str, float]:
    """Return what tells one buff taken apart from another.

    Args:
        buff: The buff.

    Returns:
        Its kind, its holder and when it ends.
    """
    return buff.buff, buff.holder, buff.ends_at_game_time_seconds


def _suggestion(callout_id: str, text: str, game_time_seconds: float) -> Callout:
    """Return a suggestion shown from now for the usual few seconds.

    Args:
        callout_id: Its stable id.
        text: What it says.
        game_time_seconds: Now.

    Returns:
        The suggestion, as a callout of its own kind.
    """
    return Callout(
        callout_id=callout_id,
        kind="suggestion",
        text=text,
        shown_until_game_time_seconds=game_time_seconds + SUGGESTION_RULES.shown_seconds,
    )


def _clock_text(seconds: float) -> str:
    """Return a duration as minutes and seconds, rounded up.

    Args:
        seconds: The duration.

    Returns:
        Such as "1:00" or "0:24".
    """
    whole_seconds = max(0, math.ceil(seconds))
    return f"{whole_seconds // SECONDS_PER_MINUTE}:{whole_seconds % SECONDS_PER_MINUTE:02d}"
