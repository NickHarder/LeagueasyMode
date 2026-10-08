"""Callouts: short notices when something happens, worked out from one state to the next.

A callout states a fact at the moment it becomes true ("Zed is level 6", "Baron in 1:00", "2
enemies down for 0:24"), or an estimate sure enough to act on ("Zed hits 6 in ~0:15"), and is shown
for a few seconds; a suggestion (`suggestions.py`) names an
action when facts line up, as the owner's policy allows. Each callout is made once per game; a state
whose clock runs backwards starts a new game.
"""

import math
from typing import Final

from leagueasymode.inference.suggestions import suggestions
from leagueasymode.overlay_state import Callout, CalloutKind, OverlayState, PlayerCard

CALLOUT_SHOWN_SECONDS: Final = 6.0
LEVEL_SPIKES: Final = (6, 11, 16)
# An enemy estimated to reach 6, 11 or 16 within this long is called out, when the estimate's
# time is sure to within the second figure.
LEVEL_SOON_SECONDS: Final = 20.0
LEVEL_SOON_MAX_BAND_SECONDS: Final = 20.0
# An enemy whose chance to afford their next item reaches this is called out.
ITEM_SOON_CHANCE: Final = 0.75
OBJECTIVE_SOON_SECONDS: Final = 60.0
# A clock this far behind the last one is a new game, not a replayed second.
NEW_GAME_CLOCK_DROP_SECONDS: Final = 5.0
SECONDS_PER_MINUTE: Final = 60
PROVISIONAL_MARK: Final = "~"
OBJECTIVE_NAMES: Final = {
    "dragon": "Dragon",
    "elder_dragon": "Elder",
    "baron": "Baron",
    "rift_herald": "Herald",
    "voidgrubs": "Voidgrubs",
}


class CalloutTracker:
    """Remembers the last state and the callouts made, and makes the new ones."""

    def __init__(self) -> None:
        """Start with no game seen."""
        self._previous_state: OverlayState | None = None
        self._made_callout_ids: set[str] = set()
        self._shown_callouts: list[Callout] = []

    def update(self, state: OverlayState) -> list[Callout]:
        """Take the next state and return the callouts to show with it.

        Args:
            state: The overlay's state, without callouts.

        Returns:
            The callouts still to be shown at this state's game time, oldest first.
        """
        game_time_seconds = state.game_time_seconds
        if not state.is_game_running or game_time_seconds is None:
            self._forget_the_game()
            return []
        previous_state = self._previous_state
        previous_game_time_seconds = (
            previous_state.game_time_seconds if previous_state is not None else None
        )
        if (
            previous_game_time_seconds is not None
            and game_time_seconds < previous_game_time_seconds - NEW_GAME_CLOCK_DROP_SECONDS
        ):
            self._forget_the_game()
        candidate_callouts = [
            *self._level_spikes(state, game_time_seconds),
            *_levels_soon(state, game_time_seconds),
            *self._jungler_backs(state, game_time_seconds),
            *self._items_soon(state, game_time_seconds),
            *self._numbers_window(state, game_time_seconds),
            *self._objectives_soon(state, game_time_seconds),
            *self._item_spikes(state, game_time_seconds),
            *self._cooldowns_ready(state, game_time_seconds),
            *suggestions(self._previous_state, state, game_time_seconds),
        ]
        new_callouts = [
            callout
            for callout in candidate_callouts
            if callout.callout_id not in self._made_callout_ids
        ]
        self._made_callout_ids.update(callout.callout_id for callout in new_callouts)
        self._shown_callouts = [
            callout
            for callout in [*self._shown_callouts, *new_callouts]
            if callout.shown_until_game_time_seconds > game_time_seconds
        ]
        self._previous_state = state
        return list(self._shown_callouts)

    def _forget_the_game(self) -> None:
        """Start over, for a new game or none."""
        self._previous_state = None
        self._made_callout_ids = set()
        self._shown_callouts = []

    def _level_spikes(self, state: OverlayState, game_time_seconds: float) -> list[Callout]:
        """Return a callout for each enemy who has just reached level 6, 11 or 16.

        A level already reached when the overlay first sees the game is not called out.

        Args:
            state: The new state.
            game_time_seconds: Its game time.

        Returns:
            The callouts.
        """
        if self._previous_state is None:
            return []
        previous_levels = {
            card.champion_name: card.level
            for card in self._previous_state.players
            if card.side == "enemy"
        }
        return [
            _callout(
                f"level:{card.champion_name}:{spike_level}",
                "level_spike",
                f"{card.champion_name} is level {spike_level}",
                game_time_seconds,
            )
            for card in state.players
            if card.side == "enemy"
            for spike_level in LEVEL_SPIKES
            if _has_just_reached(previous_levels, card, spike_level)
        ]

    def _jungler_backs(self, state: OverlayState, game_time_seconds: float) -> list[Callout]:
        """Return a callout when the enemy jungler, whom the map rarely shows, has gone back.

        A trip made before the overlay first sees the game is not called out.

        Args:
            state: The new state.
            game_time_seconds: Its game time.

        Returns:
            The callouts.
        """
        if self._previous_state is None:
            return []
        previous_backs = {
            card.champion_name: card.last_back for card in self._previous_state.players
        }
        return [
            _callout(
                f"back:{card.champion_name}:{last_back.shopped_at_game_time_seconds:.0f}",
                "went_back",
                f"{card.champion_name} went back: in the jungle again in "
                f"~{_clock_text(last_back.returns_at_game_time_seconds - game_time_seconds)}",
                game_time_seconds,
            )
            for card in state.players
            if card.side == "enemy" and card.role == "JUNGLE"
            for last_back in [card.last_back]
            if last_back is not None and previous_backs.get(card.champion_name) != last_back
        ]

    def _items_soon(self, state: OverlayState, game_time_seconds: float) -> list[Callout]:
        """Return a callout for each enemy who has just become likely to afford their next item.

        Their next trip to base then brings it: a fight is better taken before.

        Args:
            state: The new state.
            game_time_seconds: Its game time.

        Returns:
            The callouts.
        """
        if self._previous_state is None:
            return []
        previous_chances = {
            card.champion_name: (card.next_item.item_id, card.next_item.chance_to_afford)
            for card in self._previous_state.players
            if card.next_item is not None
        }
        return [
            _callout(
                f"item-soon:{card.champion_name}:{estimate.item_id}",
                "item_soon",
                f"{card.champion_name} can likely buy {estimate.item_name}",
                game_time_seconds,
            )
            for card in state.players
            if card.side == "enemy"
            for estimate in [card.next_item]
            if estimate is not None
            and estimate.chance_to_afford is not None
            and estimate.chance_to_afford >= ITEM_SOON_CHANCE
            and not _was_likely(previous_chances.get(card.champion_name), estimate.item_id)
        ]

    def _item_spikes(self, state: OverlayState, game_time_seconds: float) -> list[Callout]:
        """Return a callout for each finished item an enemy has bought since the last state.

        Items already owned when the overlay first sees the game, or when the item catalog arrives,
        are not called out: only an enemy whose items were known in the last state counts.

        Args:
            state: The new state.
            game_time_seconds: Its game time.

        Returns:
            The callouts.
        """
        if self._previous_state is None:
            return []
        previous_items = {
            card.champion_name: card.finished_item_names
            for card in self._previous_state.players
            if card.side == "enemy" and card.item_gold is not None
        }
        return [
            _callout(
                f"item:{card.champion_name}:{item_name}:{card.finished_item_names.count(item_name)}",
                "item_spike",
                f"{card.champion_name} finished {item_name}",
                game_time_seconds,
            )
            for card in state.players
            if card.side == "enemy" and card.champion_name in previous_items
            for item_name in set(card.finished_item_names)
            if card.finished_item_names.count(item_name)
            > previous_items[card.champion_name].count(item_name)
        ]

    def _cooldowns_ready(self, state: OverlayState, game_time_seconds: float) -> list[Callout]:
        """Return a callout for each marked spell that has come back since the last state.

        Args:
            state: The new state.
            game_time_seconds: Its game time.

        Returns:
            The callouts.
        """
        if self._previous_state is None:
            return []
        running_ids = {timer.cooldown_id for timer in state.cooldowns}
        return [
            _callout(
                f"cooldown:{timer.cooldown_id}",
                "cooldown_ready",
                f"{timer.champion_name}'s {timer.spell_name} is up",
                game_time_seconds,
            )
            for timer in self._previous_state.cooldowns
            if timer.cooldown_id not in running_ids
            and game_time_seconds >= timer.ready_at_game_time_seconds
        ]

    def _numbers_window(self, state: OverlayState, game_time_seconds: float) -> list[Callout]:
        """Return a callout when a numbers window opens or another enemy falls in one.

        Args:
            state: The new state.
            game_time_seconds: Its game time.

        Returns:
            The callout, or nothing.
        """
        window = state.numbers_window
        if window is None:
            return []
        enemy_text = "enemy" if window.enemy_dead_count == 1 else "enemies"
        remaining_text = _clock_text(window.ends_at_game_time_seconds - game_time_seconds)
        return [
            _callout(
                f"numbers:{window.ends_at_game_time_seconds:.0f}:{window.enemy_dead_count}",
                "numbers_window",
                f"{window.enemy_dead_count} {enemy_text} down for {remaining_text}",
                game_time_seconds,
            )
        ]

    def _objectives_soon(self, state: OverlayState, game_time_seconds: float) -> list[Callout]:
        """Return a callout for each objective that is now a minute or less from spawning.

        Args:
            state: The new state.
            game_time_seconds: Its game time.

        Returns:
            The callouts.
        """
        upcoming = [
            (objective_name, spawns_at_seconds, is_verified)
            for objective_name, spawns_at_seconds, is_verified, is_waiting in _spawn_times(state)
            if is_waiting and 0 < spawns_at_seconds - game_time_seconds <= OBJECTIVE_SOON_SECONDS
        ]
        return [
            _callout(
                f"soon:{objective_name}:{spawns_at_seconds:.0f}",
                "objective_soon",
                f"{OBJECTIVE_NAMES[objective_name]} in "
                f"{'' if is_verified else PROVISIONAL_MARK}{_clock_text(OBJECTIVE_SOON_SECONDS)}",
                game_time_seconds,
            )
            for objective_name, spawns_at_seconds, is_verified in upcoming
        ]


def _spawn_times(state: OverlayState) -> list[tuple[str, float, bool, bool]]:
    """Return each objective's name, spawn time, whether its rule is verified, and whether it waits.

    Args:
        state: The overlay's state.

    Returns:
        One entry per objective with a spawn time.
    """
    dragon = state.dragon
    dragon_entries = (
        [
            (
                dragon.objective,
                dragon.spawns_at_game_time_seconds,
                True,
                dragon.status != "alive",
            )
        ]
        if dragon is not None
        else []
    )
    objective_entries = [
        (
            timer.objective,
            timer.spawns_at_game_time_seconds,
            timer.is_rule_verified,
            timer.status in {"not_spawned", "respawning"},
        )
        for timer in state.objectives
        if timer.spawns_at_game_time_seconds is not None
    ]
    return [*dragon_entries, *objective_entries]


def _levels_soon(state: OverlayState, game_time_seconds: float) -> list[Callout]:
    """Return a callout for each enemy about to reach 6, 11 or 16, by their experience's estimate.

    Args:
        state: The new state.
        game_time_seconds: Its game time.

    Returns:
        The callouts: those within 20 seconds, whose time is sure to within 20 seconds.
    """
    return [
        callout
        for callout in (
            _level_soon(card, game_time_seconds) for card in state.players if card.side == "enemy"
        )
        if callout is not None
    ]


def _level_soon(card: PlayerCard, game_time_seconds: float) -> Callout | None:
    """Return the callout for an enemy about to reach their next power level, if they are.

    Args:
        card: The enemy.
        game_time_seconds: The game's clock.

    Returns:
        The callout, or None when the level is not near or its time is not sure enough.
    """
    estimate = card.level_estimate
    if (
        estimate is None
        or estimate.next_power_level is None
        or estimate.power_level_at_game_time_seconds is None
        or estimate.power_level_band_seconds is None
        or estimate.power_level_band_seconds > LEVEL_SOON_MAX_BAND_SECONDS
    ):
        return None
    seconds_to_go = estimate.power_level_at_game_time_seconds - game_time_seconds
    if not 0 < seconds_to_go <= LEVEL_SOON_SECONDS:
        return None
    return _callout(
        f"level-soon:{card.champion_name}:{estimate.next_power_level}",
        "level_soon",
        f"{card.champion_name} hits {estimate.next_power_level} in ~{_clock_text(seconds_to_go)}",
        game_time_seconds,
    )


def _was_likely(previous: tuple[int, float | None] | None, item_id: int) -> bool:
    """Return whether an enemy was already likely to afford the same item in the last state.

    Args:
        previous: Their next item's id and chance to afford it in the last state; None without one.
        item_id: Their next item's id now.

    Returns:
        Whether it was the same item, as likely.
    """
    if previous is None:
        return False
    previous_item_id, previous_chance = previous
    return (
        previous_item_id == item_id
        and previous_chance is not None
        and previous_chance >= ITEM_SOON_CHANCE
    )


def _has_just_reached(previous_levels: dict[str, int], card: PlayerCard, spike_level: int) -> bool:
    """Return whether an enemy has reached a level since the last state.

    Args:
        previous_levels: Each enemy's level in the last state.
        card: The enemy now.
        spike_level: The level.

    Returns:
        Whether the level was crossed between the two states.
    """
    previous_level = previous_levels.get(card.champion_name)
    return previous_level is not None and previous_level < spike_level <= card.level


def _callout(callout_id: str, kind: CalloutKind, text: str, game_time_seconds: float) -> Callout:
    """Return a callout shown from now for the usual few seconds.

    Args:
        callout_id: Its stable id.
        kind: Its kind.
        text: What it says.
        game_time_seconds: Now.

    Returns:
        The callout.
    """
    return Callout(
        callout_id=callout_id,
        kind=kind,
        text=text,
        shown_until_game_time_seconds=game_time_seconds + CALLOUT_SHOWN_SECONDS,
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
