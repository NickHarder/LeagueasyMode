"""Callouts: short notices when something happens, worked out from one state to the next.

A callout states a fact at the moment it becomes true ("Zed is level 6", "Baron in 1:00", "2
enemies down for 0:24"), or an estimate sure enough to act on ("Zed hits 6 in ~0:15"), and is shown
for a few seconds; a suggestion (`suggestions.py`) names an
action when facts line up, as the owner's policy allows. Each callout is made once per game; a state
whose clock runs backwards starts a new game.
"""

import math
from typing import Final

from pydantic import BaseModel, ConfigDict

from leagueasymode.inference.positions import reach_seconds_of
from leagueasymode.inference.suggestions import SUGGESTION_RULES, SuggestionRules, suggestions
from leagueasymode.overlay_state import Callout, CalloutKind, OverlayState, PlayerCard

LEVEL_SPIKES: Final = (6, 11, 16)
LANE_OF_ROLE: Final = {"TOP": "top", "MIDDLE": "mid", "BOTTOM": "bot", "UTILITY": "bot"}
MAP_HALF_TEXT: Final = {"top": "top side", "mid": "mid", "bot": "bot side"}
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


class CalloutRules(BaseModel):
    """The callouts' hand-set thresholds: `tuning.json`'s "callouts"."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # How long a callout shows, in game seconds.
    shown_seconds: float = 6.0
    # An enemy estimated to reach 6, 11 or 16 within this long is called out, when the estimate's
    # time is sure to within the second figure.
    level_soon_seconds: float = 20.0
    level_soon_max_band_seconds: float = 20.0
    # An enemy whose chance to afford their next item reaches this is called out.
    item_soon_chance: float = 0.75
    # An enemy unseen this long, likely (this chance) away from where they play, who could reach
    # your lane this soon, is called out as missing; one at a time, at most once in the last.
    missing_unseen_seconds: float = 20.0
    missing_away_chance: float = 0.5
    missing_reach_seconds: float = 20.0
    missing_gap_seconds: float = 30.0
    # An objective this close to spawning is called out.
    objective_soon_seconds: float = 60.0
    # Scouting (a jungler's usual start, an enemy one-trick) is called out before this: the camps
    # spawn at 1:30.
    scouting_until_seconds: float = 90.0
    # A jungler's habit is called out when at least this share of at least this many of their
    # recent jungle games had it.
    habit_min_share: float = 0.7
    habit_min_games: int = 2
    # Where a jungler usually is at 4:00 is called out in this window.
    jungle_four_minutes_from_seconds: float = 165.0
    jungle_four_minutes_until_seconds: float = 210.0


CALLOUT_RULES: Final = CalloutRules()


class CalloutTracker:
    """Remembers the last state and the callouts made, and makes the new ones."""

    def __init__(
        self,
        rules: CalloutRules = CALLOUT_RULES,
        suggestion_rules: SuggestionRules = SUGGESTION_RULES,
    ) -> None:
        """Start with no game seen.

        Args:
            rules: The callouts' hand-set thresholds.
            suggestion_rules: The suggestions'.
        """
        self.rules: Final = rules
        self.suggestion_rules: Final = suggestion_rules
        self._previous_state: OverlayState | None = None
        self._made_callout_ids: set[str] = set()
        self._shown_callouts: list[Callout] = []
        self._last_missing_seconds: float | None = None

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
            *_levels_soon(state, game_time_seconds, self.rules),
            *_jungle_starts(state, game_time_seconds, self.rules),
            *_one_tricks(state, game_time_seconds, self.rules),
            *_jungle_four_minutes(state, game_time_seconds, self.rules),
            *self._jungler_backs(state, game_time_seconds),
            *self._items_soon(state, game_time_seconds),
            *self._missing(state, game_time_seconds),
            *self._numbers_window(state, game_time_seconds),
            *self._objectives_soon(state, game_time_seconds),
            *self._item_spikes(state, game_time_seconds),
            *self._cooldowns_ready(state, game_time_seconds),
            *self._inhibitors_opened(state, game_time_seconds),
            *suggestions(self._previous_state, state, game_time_seconds, self.suggestion_rules),
        ]
        # Each is shown for as long as the rules say from now.
        new_callouts = [
            callout.model_copy(
                update={
                    "shown_until_game_time_seconds": game_time_seconds
                    + (
                        self.suggestion_rules.shown_seconds
                        if callout.kind == "suggestion"
                        else self.rules.shown_seconds
                    )
                }
            )
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
        self._last_missing_seconds = None

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

    def _inhibitors_opened(self, state: OverlayState, game_time_seconds: float) -> list[Callout]:
        """Return a callout for each inhibitor, either side's, whose turret has just fallen.

        An inhibitor already open when the overlay first sees the game is not called out, and
        each is called out once a game.

        Args:
            state: The new state.
            game_time_seconds: Its game time.

        Returns:
            The callouts.
        """
        if self._previous_state is None:
            return []
        previously_open = {
            (lane.side, lane.lane)
            for lane in self._previous_state.structures
            if lane.is_inhibitor_exposed
        }
        return [
            _callout(
                f"inhibitor-open:{lane.side}:{lane.lane}",
                "inhibitor_open",
                f"{'Your' if lane.side == 'ally' else 'Enemy'} {lane.lane} inhibitor is open",
                game_time_seconds,
            )
            for lane in state.structures
            if lane.is_inhibitor_exposed and (lane.side, lane.lane) not in previously_open
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

    def _missing(self, state: OverlayState, game_time_seconds: float) -> list[Callout]:
        """Return a callout for the missing enemy who could reach your lane soonest, if one could.

        Args:
            state: The new state.
            game_time_seconds: Its game time.

        Returns:
            At most one callout, and none within 30 seconds of the last.
        """
        last_missing_seconds = self._last_missing_seconds
        if self._previous_state is None or (
            last_missing_seconds is not None
            and game_time_seconds - last_missing_seconds < self.rules.missing_gap_seconds
        ):
            return []
        you = next((card for card in state.players if card.is_you), None)
        lane = LANE_OF_ROLE.get(you.role) if you is not None else None
        if lane is None:
            return []
        candidates = [
            candidate
            for card in state.players
            if card.side == "enemy" and not card.is_dead
            for candidate in [_missing_from(card, lane, self.rules)]
            if candidate is not None
        ]
        if not candidates:
            return []
        reach_seconds, unseen_seconds, champion_name = min(candidates)
        self._last_missing_seconds = game_time_seconds
        return [
            _callout(
                f"missing:{champion_name}:{game_time_seconds:.0f}",
                "missing",
                f"{champion_name} missing {_clock_text(unseen_seconds)}: can reach {lane} "
                f"in ~{_clock_text(reach_seconds)}",
                game_time_seconds,
            )
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
            and estimate.chance_to_afford >= self.rules.item_soon_chance
            and not _was_likely(
                previous_chances.get(card.champion_name), estimate.item_id, self.rules
            )
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
        soon_seconds = self.rules.objective_soon_seconds
        upcoming = [
            (objective_name, spawns_at_seconds, is_verified)
            for objective_name, spawns_at_seconds, is_verified, is_waiting in _spawn_times(state)
            if is_waiting and 0 < spawns_at_seconds - game_time_seconds <= soon_seconds
        ]
        return [
            _callout(
                f"soon:{objective_name}:{spawns_at_seconds:.0f}",
                "objective_soon",
                f"{OBJECTIVE_NAMES[objective_name]} in "
                f"{'' if is_verified else PROVISIONAL_MARK}{_clock_text(soon_seconds)}",
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


def _levels_soon(
    state: OverlayState, game_time_seconds: float, rules: CalloutRules
) -> list[Callout]:
    """Return a callout for each enemy about to reach 6, 11 or 16, by their experience's estimate.

    Args:
        state: The new state.
        game_time_seconds: Its game time.
        rules: The hand-set thresholds.

    Returns:
        The callouts: those within 20 seconds, whose time is sure to within 20 seconds.
    """
    return [
        callout
        for callout in (
            _level_soon(card, game_time_seconds, rules)
            for card in state.players
            if card.side == "enemy"
        )
        if callout is not None
    ]


def _jungle_starts(
    state: OverlayState, game_time_seconds: float, rules: CalloutRules
) -> list[Callout]:
    """Return where the enemy jungler usually starts, before the camps spawn.

    Args:
        state: The new state.
        game_time_seconds: Its game time.
        rules: The hand-set thresholds.

    Returns:
        A callout for each enemy in the jungle whose recent jungle games mostly started on one
        side; none from 1:30 on.
    """
    if game_time_seconds >= rules.scouting_until_seconds:
        return []
    return [
        _callout(
            f"jungle-start:{card.champion_name}",
            "jungle_start",
            f"{card.champion_name} usually starts {intel.jungle_start_side}"
            f"{f', {intel.jungle_start_half} side' if intel.jungle_start_half else ''} "
            f"({intel.jungle_start_count} of {intel.jungle_start_games})",
            game_time_seconds,
        )
        for card in state.players
        if card.side == "enemy"
        and card.role == "JUNGLE"
        and (intel := card.intel) is not None
        and intel.jungle_start_side is not None
        and intel.jungle_start_games >= rules.habit_min_games
        and intel.jungle_start_count >= rules.habit_min_share * intel.jungle_start_games
    ]


def _one_tricks(
    state: OverlayState, game_time_seconds: float, rules: CalloutRules
) -> list[Callout]:
    """Return each enemy who plays little but this game's champion, before the camps spawn.

    Args:
        state: The new state.
        game_time_seconds: Its game time.
        rules: The hand-set thresholds.

    Returns:
        A callout for each enemy one-trick; none from 1:30 on.
    """
    if game_time_seconds >= rules.scouting_until_seconds:
        return []
    return [
        _callout(
            f"one-trick:{card.champion_name}",
            "one_trick",
            f"{card.champion_name} is a one-trick ({intel.champion_game_count} of "
            f"{intel.recent_game_count} games)",
            game_time_seconds,
        )
        for card in state.players
        if card.side == "enemy" and (intel := card.intel) is not None and intel.is_one_trick
    ]


def _jungle_four_minutes(
    state: OverlayState, game_time_seconds: float, rules: CalloutRules
) -> list[Callout]:
    """Return where the enemy jungler usually is at 4:00, shortly before it.

    Args:
        state: The new state.
        game_time_seconds: Its game time.
        rules: The hand-set thresholds.

    Returns:
        A callout for each enemy in the jungle whose recent jungle games mostly found them on one
        side at 4:00; none outside 2:45 to 3:30.
    """
    if (
        not rules.jungle_four_minutes_from_seconds
        <= game_time_seconds
        < rules.jungle_four_minutes_until_seconds
    ):
        return []
    return [
        _callout(
            f"jungle-four-minutes:{card.champion_name}",
            "jungle_four_minutes",
            f"{card.champion_name} is usually {MAP_HALF_TEXT[intel.four_minute_half]} at 4:00 "
            f"({intel.four_minute_count} of {intel.four_minute_games})",
            game_time_seconds,
        )
        for card in state.players
        if card.side == "enemy"
        and card.role == "JUNGLE"
        and (intel := card.intel) is not None
        and intel.four_minute_half is not None
        and intel.four_minute_games >= rules.habit_min_games
        and intel.four_minute_count >= rules.habit_min_share * intel.four_minute_games
    ]


def _level_soon(card: PlayerCard, game_time_seconds: float, rules: CalloutRules) -> Callout | None:
    """Return the callout for an enemy about to reach their next power level, if they are.

    Args:
        card: The enemy.
        game_time_seconds: The game's clock.
        rules: The hand-set thresholds.

    Returns:
        The callout, or None when the level is not near or its time is not sure enough.
    """
    estimate = card.level_estimate
    if (
        estimate is None
        or estimate.next_power_level is None
        or estimate.power_level_at_game_time_seconds is None
        or estimate.power_level_band_seconds is None
        or estimate.power_level_band_seconds > rules.level_soon_max_band_seconds
    ):
        return None
    seconds_to_go = estimate.power_level_at_game_time_seconds - game_time_seconds
    if not 0 < seconds_to_go <= rules.level_soon_seconds:
        return None
    return _callout(
        f"level-soon:{card.champion_name}:{estimate.next_power_level}",
        "level_soon",
        f"{card.champion_name} hits {estimate.next_power_level} in ~{_clock_text(seconds_to_go)}",
        game_time_seconds,
    )


def _missing_from(
    card: PlayerCard, lane: str, rules: CalloutRules
) -> tuple[float, float, str] | None:
    """Return how soon an enemy unseen and likely away could reach a lane, if soon enough.

    Args:
        card: The enemy.
        lane: "top", "mid" or "bot".
        rules: The hand-set thresholds.

    Returns:
        The seconds to reach it, the seconds unseen and their champion; None when they were seen
        lately, are likely where they play, or could not reach it soon.
    """
    location = card.location
    if location is None or location.unseen_seconds is None:
        return None
    reach_seconds = reach_seconds_of(location, lane)
    if (
        reach_seconds is None
        or location.unseen_seconds < rules.missing_unseen_seconds
        or location.away_chance < rules.missing_away_chance
        or reach_seconds > rules.missing_reach_seconds
    ):
        return None
    return reach_seconds, location.unseen_seconds, card.champion_name


def _was_likely(
    previous: tuple[int, float | None] | None, item_id: int, rules: CalloutRules
) -> bool:
    """Return whether an enemy was already likely to afford the same item in the last state.

    Args:
        previous: Their next item's id and chance to afford it in the last state; None without one.
        item_id: Their next item's id now.
        rules: The hand-set thresholds.

    Returns:
        Whether it was the same item, as likely.
    """
    if previous is None:
        return False
    previous_item_id, previous_chance = previous
    return (
        previous_item_id == item_id
        and previous_chance is not None
        and previous_chance >= rules.item_soon_chance
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
        shown_until_game_time_seconds=game_time_seconds + CALLOUT_RULES.shown_seconds,
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
