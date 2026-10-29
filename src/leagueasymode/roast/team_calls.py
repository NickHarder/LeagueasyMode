"""Team calls (phase 11.9): calm, constructive calls for the whole team, to paste in team chat.

The owner asked for "a constructive mode for non friends", to keep the team alive and moving for
objectives, with "non tilt messages to boost coordination and encouragement". Each call is worked
out from what the overlay already shows:

- an epic monster spawning soon: stay alive, ward, start moving;
- enemies dead for long enough while most of us are alive: take something now;
- a fight lost (several of us dead at once, fewer of them): reset and group for the next objective;
- a teammate's death streak: steady the team toward the next objective, naming no one;
- behind in estimated gold while the win chance is still in reach: play safe, it is winnable.

Off the Rift (ARAM and the rest) only the window to push is called: those maps have no epic
monsters and no recall, so "reset and buy" and "next up is…" do not hold there (the owner,
2026-10-29: "i am getting stuff like reset for obj even in aram"). No call is made while a fight is
on, a death in the last few seconds, so a fight brings one call when it ends, not one a death; and
while the numbers window callout is shown, the call that enemies are down stays off the overlay,
since the callout says it already (⌃⌥C still copies it).

A call blames no one and names no player. The gold lead is an estimate, so it is said as "about".
At most one call a minute; each shows beside the callouts as a callout of kind "team_call", is
never spoken, and ⌃⌥C copies the newest call or moment (11.4). Nothing is sent to chat.
"""

import math
import tomllib
from importlib import resources
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from leagueasymode.game_state import GameSnapshot
from leagueasymode.overlay_state import Callout, OverlayState
from leagueasymode.roast.rules import TeamCallRules

CHAMPION_KILL_EVENT: Final = "ChampionKill"
SECONDS_PER_MINUTE: Final = 60
GOLD_PER_THOUSAND: Final = 1000
# A call noticed later than this after its moment, as when the engine starts mid-game, is not shown.
FRESH_SECONDS: Final = 30.0
NEW_GAME_CLOCK_DROP_SECONDS: Final = 5.0
MONSTER_NAMES: Final = {
    "dragon": "Dragon",
    "elder_dragon": "Elder",
    "baron": "Baron",
    "rift_herald": "Herald",
    "voidgrubs": "Grubs",
}

type TeamCallKind = Literal[
    "objective_soon", "enemies_down", "fight_lost", "death_streak", "behind_but_winnable"
]


class TeamCallLines(BaseModel):
    """One line for each kind of call, with its slots in braces (`team_calls.toml`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective_soon: str
    enemies_down: str
    fight_lost: str
    death_streak: str
    behind_but_winnable: str


class TeamCall(BaseModel):
    """One call of this game."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Stable for one happening, so that it is made once.
    call_id: str
    kind: TeamCallKind
    text: str
    made_at_game_time_seconds: float


class UpcomingObjective(BaseModel):
    """An epic monster that is up, or the time it spawns."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    spawns_at_game_time_seconds: float | None


def load_team_call_lines() -> TeamCallLines:
    """Return the calls' lines.

    Returns:
        The lines in `team_calls.toml`.
    """
    lines_text = resources.files(__package__).joinpath("team_calls.toml").read_text("utf-8")
    return TeamCallLines.model_validate(tomllib.loads(lines_text)["lines"])


class TeamCallTracker:
    """Reads each state of the game and makes this game's team calls."""

    def __init__(self, rules: TeamCallRules, lines: TeamCallLines | None = None) -> None:
        """Start with no game seen.

        Args:
            rules: The thresholds.
            lines: The lines; those of `team_calls.toml` when None.
        """
        self.rules: Final = rules
        self.lines: Final = lines or load_team_call_lines()
        self._calls: list[TeamCall] = []
        self._last_game_time_seconds: float | None = None

    @property
    def calls(self) -> tuple[TeamCall, ...]:
        """This game's calls, oldest first."""
        return tuple(self._calls)

    def update(self, state: OverlayState, snapshot: GameSnapshot | None) -> TeamCall | None:
        """Take the next state and return the call it made, if any.

        Args:
            state: The overlay's state for the answer.
            snapshot: The game's answer, for the kill feed; None when no game is running.

        Returns:
            The new call, or None; at most one a minute.
        """
        game_time_seconds = state.game_time_seconds
        if not state.is_game_running or game_time_seconds is None or snapshot is None:
            self._calls = []
            self._last_game_time_seconds = None
            return None
        last_game_time_seconds = self._last_game_time_seconds
        if (
            last_game_time_seconds is not None
            and game_time_seconds < last_game_time_seconds - NEW_GAME_CLOCK_DROP_SECONDS
        ):
            self._calls = []
        self._last_game_time_seconds = game_time_seconds
        last_call_seconds = self._calls[-1].made_at_game_time_seconds if self._calls else None
        if (
            last_call_seconds is not None
            and game_time_seconds - last_call_seconds < self.rules.least_gap_seconds
        ):
            return None
        if _is_fight_on(snapshot, game_time_seconds, self.rules.fight_quiet_seconds):
            return None
        made_ids = {call.call_id for call in self._calls}
        candidates = [
            *self._objective_soon(state, game_time_seconds),
            *self._enemies_down(state, game_time_seconds),
            *self._fight_lost(state, game_time_seconds),
            *self._death_streak(state, snapshot, game_time_seconds),
            *self._behind_but_winnable(state, game_time_seconds),
        ]
        new_call = next((call for call in candidates if call.call_id not in made_ids), None)
        if new_call is not None:
            self._calls.append(new_call)
        return new_call

    def callouts(
        self, game_time_seconds: float | None, *, is_numbers_window_shown: bool = False
    ) -> list[Callout]:
        """Return the calls still shown, as callouts of kind "team_call".

        Args:
            game_time_seconds: The game's clock; None when no game is running.
            is_numbers_window_shown: Whether the numbers window callout shows now; it says what a
                call that enemies are down would, so that call stays off the overlay.

        Returns:
            The calls made less than `shown_seconds` ago, oldest first.
        """
        if game_time_seconds is None:
            return []
        return [
            Callout(
                callout_id=f"team_call:{call.call_id}",
                kind="team_call",
                text=call.text,
                shown_until_game_time_seconds=call.made_at_game_time_seconds
                + self.rules.shown_seconds,
            )
            for call in self._calls
            if call.made_at_game_time_seconds + self.rules.shown_seconds > game_time_seconds
            and not (is_numbers_window_shown and call.kind == "enemies_down")
        ]

    def _call(self, call_id: str, kind: TeamCallKind, text: str, now: float) -> TeamCall:
        """Return a call made now."""
        return TeamCall(call_id=call_id, kind=kind, text=text, made_at_game_time_seconds=now)

    def _objective_soon(self, state: OverlayState, now: float) -> list[TeamCall]:
        """Return a call for an epic monster spawning soon."""
        if not state.is_summoners_rift:
            return []
        calls: list[TeamCall] = []
        for upcoming in upcoming_objectives(state, now):
            spawns_at = upcoming.spawns_at_game_time_seconds
            if spawns_at is None:
                continue
            seconds_until = spawns_at - now
            if (
                self.rules.objective_soon_from_seconds
                <= seconds_until
                <= self.rules.objective_soon_until_seconds
            ):
                calls.append(
                    self._call(
                        f"objective_soon:{upcoming.name}:{round(spawns_at)}",
                        "objective_soon",
                        self.lines.objective_soon.format(
                            monster=upcoming.name, clock=_clock(seconds_until)
                        ),
                        now,
                    )
                )
        return calls

    def _enemies_down(self, state: OverlayState, now: float) -> list[TeamCall]:
        """Return a call to take something while enemies are dead long enough."""
        down_for = sorted(
            card.respawns_at_game_time_seconds - now
            for card in state.players
            if card.side == "enemy"
            and card.is_dead
            and card.respawns_at_game_time_seconds is not None
            and card.respawns_at_game_time_seconds - now >= self.rules.enemies_down_seconds
        )
        allies_alive = sum(1 for card in state.players if card.side == "ally" and not card.is_dead)
        if (
            len(down_for) < self.rules.enemies_down_count
            or allies_alive < self.rules.enemies_down_allies_alive
        ):
            return []
        # The time all of them are still down: the shortest of their timers.
        seconds_down = math.floor(down_for[0])
        return [
            self._call(
                f"enemies_down:{math.floor(now / self.rules.least_gap_seconds)}",
                "enemies_down",
                self.lines.enemies_down.format(
                    count=len(down_for), seconds=seconds_down, target=_target(state)
                ),
                now,
            )
        ]

    def _fight_lost(self, state: OverlayState, now: float) -> list[TeamCall]:
        """Return a call to reset after a lost fight; on the Rift only, which has a recall."""
        if not state.is_summoners_rift:
            return []
        allies_dead = sum(1 for card in state.players if card.side == "ally" and card.is_dead)
        enemies_dead = sum(1 for card in state.players if card.side == "enemy" and card.is_dead)
        if allies_dead < self.rules.fight_lost_allies_dead or enemies_dead >= allies_dead:
            return []
        return [
            self._call(
                f"fight_lost:{math.floor(now / self.rules.least_gap_seconds)}",
                "fight_lost",
                self.lines.fight_lost.format(next=_next_objective_text(state, now)),
                now,
            )
        ]

    def _death_streak(
        self, state: OverlayState, snapshot: GameSnapshot, now: float
    ) -> list[TeamCall]:
        """Return a call to steady the team after a teammate's deaths; on the Rift only."""
        if not state.is_summoners_rift:
            return []
        ally_team = snapshot.ally_team()
        recent_deaths: dict[str, list[float]] = {}
        for event in snapshot.event_list.events:
            victim = event.victim_name
            if (
                event.event_name != CHAMPION_KILL_EVENT
                or victim is None
                or snapshot.team_of(victim) != ally_team
                or now - event.event_time_seconds > self.rules.death_streak_seconds
            ):
                continue
            recent_deaths.setdefault(victim, []).append(event.event_time_seconds)
        streaks = [
            (victim, deaths)
            for victim, deaths in recent_deaths.items()
            if len(deaths) >= self.rules.death_streak_deaths
        ]
        if not streaks:
            return []
        streak_victim, streak_deaths = streaks[0]
        # Once per streak: by the teammate's place on the scoreboard, never their name, since the
        # id travels with the overlay's state, and by the streak's first death.
        place = next(
            (
                index
                for index, player in enumerate(snapshot.players)
                if player.is_named(streak_victim)
            ),
            -1,
        )
        return [
            self._call(
                f"death_streak:{place}:{round(streak_deaths[0])}",
                "death_streak",
                self.lines.death_streak.format(next=_next_objective_text(state, now)),
                now,
            )
        ]

    def _behind_but_winnable(self, state: OverlayState, now: float) -> list[TeamCall]:
        """Return a call to play safe while behind in gold but still winnable."""
        team_gold = state.team_gold
        win_chance = state.win_chance
        if team_gold is None or win_chance is None:
            return []
        behind = team_gold.enemy_total_gold - team_gold.ally_total_gold
        if behind < self.rules.behind_gold or win_chance.ally_chance < self.rules.winnable_chance:
            return []
        five_minutes = 5 * SECONDS_PER_MINUTE
        return [
            self._call(
                f"behind_but_winnable:{math.floor(now / five_minutes)}",
                "behind_but_winnable",
                self.lines.behind_but_winnable.format(gold=_rounded_gold(behind)),
                now,
            )
        ]


def upcoming_objectives(state: OverlayState, now: float) -> list[UpcomingObjective]:
    """Return the epic monsters that are up or will spawn, soonest first.

    Args:
        state: The overlay's state.
        now: The game's clock.

    Returns:
        Each monster, with its spawn time, or None when it is up.
    """
    timers: list[tuple[str, str, float | None]] = []
    if state.dragon is not None:
        timers.append(
            (state.dragon.objective, state.dragon.status, state.dragon.spawns_at_game_time_seconds)
        )
    timers.extend(
        (timer.objective, timer.status, timer.spawns_at_game_time_seconds)
        for timer in state.objectives
        if timer.status != "gone"
    )
    upcoming = [
        UpcomingObjective(
            name=MONSTER_NAMES[objective],
            spawns_at_game_time_seconds=None if status == "alive" else spawns_at,
        )
        for objective, status, spawns_at in timers
        if status == "alive" or (spawns_at is not None and spawns_at > now)
    ]
    return sorted(
        upcoming,
        key=lambda item: (
            item.spawns_at_game_time_seconds is not None,
            item.spawns_at_game_time_seconds or 0.0,
        ),
    )


def _is_fight_on(snapshot: GameSnapshot, now: float, quiet_seconds: float) -> bool:
    """Return whether a champion died in the last `quiet_seconds`: a fight still on."""
    return any(
        event.event_name == CHAMPION_KILL_EVENT
        and now - quiet_seconds < event.event_time_seconds <= now
        for event in snapshot.event_list.events
    )


def _next_objective_text(state: OverlayState, now: float) -> str:
    """Return the next objective as a call says it: "Dragon at 18:40", "Baron (up now)"."""
    upcoming = upcoming_objectives(state, now) if state.is_summoners_rift else []
    if not upcoming:
        return "the next objective"
    first = upcoming[0]
    if first.spawns_at_game_time_seconds is None:
        return f"{first.name} (up now)"
    return f"{first.name} at {_clock(first.spawns_at_game_time_seconds)}"


def _target(state: OverlayState) -> str:
    """Return what to take while enemies are down: a monster that is up, else a tower."""
    if state.is_summoners_rift:
        for objective in ("baron", "elder_dragon", "dragon", "rift_herald"):
            dragon_up = (
                state.dragon is not None
                and state.dragon.objective == objective
                and state.dragon.status == "alive"
            )
            other_up = any(
                timer.objective == objective and timer.status == "alive"
                for timer in state.objectives
            )
            if dragon_up or other_up:
                return MONSTER_NAMES[objective]
    return "a tower"


def _rounded_gold(gold: int) -> str:
    """Return gold rounded to half a thousand: "2.5k"."""
    halves = round(gold / (GOLD_PER_THOUSAND / 2)) / 2
    return f"{halves:g}k"


def _clock(seconds: float) -> str:
    """Return a duration or game time as minutes and seconds: "1:25"."""
    whole_seconds = max(0, round(seconds))
    return f"{whole_seconds // SECONDS_PER_MINUTE}:{whole_seconds % SECONDS_PER_MINUTE:02d}"
