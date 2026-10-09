"""The game reconstructed (phase 6.3): what the post-game window shows of the last game.

From a recorded game, once its timeline has come:

- the result, your champion and the game's length;
- the win chance at the start of each minute (estimator 12), and the gold lead each minute, as
  the overlay estimated it and as the timeline has it;
- the moments of the feed, from your side: kills, monsters, turrets and inhibitors;
- the minutes that moved the win chance most, with what happened in each;
- every estimator's score on the game.

The page (`/summary.html`, phase 6.4) reads it as JSON from `/summary`;
`overlay/web/game_summary.schema.json` holds its JSON Schema, which a test keeps current.
"""

import itertools
import json
import sys
from collections.abc import Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from leagueasymode.game_state import GameEvent, GameSnapshot
from leagueasymode.inference.gold import (
    CHAMPION_KILL_EVENT,
    TURRET_KILLED_EVENT,
    TURRET_NAME_PATTERN,
    TURRET_TIER_BY_LANE_AND_PLACE,
)
from leagueasymode.inference.objectives import (
    BARON_KILL_EVENT,
    DRAGON_KILL_EVENT,
    ELDER_DRAGON_TYPE,
    INHIBITOR_KILLED_EVENT,
    INHIBITOR_NAME_PATTERN,
    LANE_BY_LETTER,
    TEAM_BY_NUMBER,
)
from leagueasymode.inference.win_chance import WIN_CHANCE_RULES, WinChanceRules, win_chance
from leagueasymode.scoring import (
    EstimatorScore,
    RecordedGame,
    ally_result,
    timeline_gold_leads,
)

SECONDS_PER_MINUTE: Final = 60.0
SHOWN_SWING_COUNT: Final = 3
MONSTER_BY_EVENT: Final[dict[str, tuple[Literal["baron", "herald", "voidgrubs"], str]]] = {
    BARON_KILL_EVENT: ("baron", "Baron"),
    "HeraldKill": ("herald", "the Herald"),
    "HordeKill": ("voidgrubs", "the Voidgrubs"),
}

type MomentKind = Literal[
    "kill", "dragon", "elder", "baron", "herald", "voidgrubs", "turret", "inhibitor"
]


class SummaryPoint(BaseModel):
    """One minute's value of a series."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minute: int
    value: float


class SummaryMoment(BaseModel):
    """One moment of the feed, from your side."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_time_seconds: float
    kind: MomentKind
    # Whose good it was: your team's ("ally") or theirs ("enemy").
    side: Literal["ally", "enemy"]
    # Such as "Zed killed Ahri" or "your team took their top outer turret".
    text: str


class WinSwing(BaseModel):
    """A minute that moved the win chance, and what happened in it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minute: int
    # The change of your team's chance over the minute: above 0 for your team.
    change: float
    moments: list[str]


class SummaryScore(BaseModel):
    """One estimator's score on the game."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    estimator: str
    measure: str
    sample_count: int
    value: float
    # The score in one line, as `leagueasymode score` prints it.
    text: str


class GameSummary(BaseModel):
    """The game reconstructed, for the post-game window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    recording_name: str
    # None when the recording does not say.
    result: Literal["win", "loss"] | None
    champion_name: str | None
    duration_seconds: float
    # Your team's chance at the start of each minute.
    win_chance: list[SummaryPoint]
    # Your team's gold lead each minute: the overlay's estimate, and the timeline's truth (empty
    # without a timeline).
    gold_lead_estimated: list[SummaryPoint]
    gold_lead_true: list[SummaryPoint]
    moments: list[SummaryMoment]
    swings: list[WinSwing]
    scores: list[SummaryScore]


def game_summary(
    recording_name: str,
    game: RecordedGame,
    scores: Sequence[EstimatorScore],
    rules: WinChanceRules = WIN_CHANCE_RULES,
) -> GameSummary:
    """Return the game reconstructed.

    Args:
        recording_name: The recording's file name.
        game: What the harness read from the recording.
        scores: Every estimator's score on it.
        rules: The win chance's weights.

    Returns:
        The summary.
    """
    last_snapshot = game.minute_snapshots[-1] if game.minute_snapshots else None
    features_by_minute = sorted(game.minute_win_features.items())
    win_series = [
        SummaryPoint(minute=minute, value=round(win_chance(features, rules).ally_chance, 4))
        for minute, features in features_by_minute
    ]
    moments = feed_moments(last_snapshot) if last_snapshot is not None else []
    has_won = ally_result(game)
    return GameSummary(
        recording_name=recording_name,
        result=None if has_won is None else ("win" if has_won else "loss"),
        champion_name=_your_champion(last_snapshot) if last_snapshot is not None else None,
        duration_seconds=(
            last_snapshot.game_data.game_time_seconds if last_snapshot is not None else 0.0
        ),
        win_chance=win_series,
        gold_lead_estimated=[
            SummaryPoint(minute=minute, value=round(features.gold_lead))
            for minute, features in features_by_minute
        ],
        gold_lead_true=[
            SummaryPoint(minute=minute, value=lead)
            for minute, lead in sorted(timeline_gold_leads(game).items())
        ],
        moments=moments,
        swings=win_swings(win_series, moments),
        scores=[
            SummaryScore(
                estimator=score.estimator,
                measure=score.measure,
                sample_count=score.sample_count,
                value=score.value,
                text=score.describe(),
            )
            for score in scores
        ],
    )


def win_swings(
    win_series: Sequence[SummaryPoint],
    moments: Sequence[SummaryMoment],
    count: int = SHOWN_SWING_COUNT,
) -> list[WinSwing]:
    """Return the minutes that moved the win chance most, with the moments in each.

    Args:
        win_series: Your team's chance at the start of each minute, in order.
        moments: The game's moments.
        count: How many minutes to return.

    Returns:
        The swings, the largest first; a swing's minute runs from the minute before to its own.
    """
    changes = [
        (later.minute, later.value - earlier.value)
        for earlier, later in itertools.pairwise(win_series)
    ]
    largest = sorted(changes, key=lambda change: abs(change[1]), reverse=True)[:count]
    return [
        WinSwing(
            minute=minute,
            change=round(change, 4),
            moments=[
                moment.text
                for moment in moments
                if (minute - 1) * SECONDS_PER_MINUTE
                < moment.game_time_seconds
                <= minute * SECONDS_PER_MINUTE
            ],
        )
        for minute, change in largest
    ]


def feed_moments(snapshot: GameSnapshot) -> list[SummaryMoment]:
    """Return the moments of the feed, from your side, oldest first.

    Args:
        snapshot: The game's last answer, whose feed holds the whole game.

    Returns:
        The kills, monsters, turrets and inhibitors; the other entries are left out.
    """
    ally_team = snapshot.ally_team()
    moments = [
        moment
        for event in snapshot.event_list.events
        for moment in _event_moments(event, snapshot, ally_team)
    ]
    return sorted(moments, key=lambda moment: moment.game_time_seconds)


def _event_moments(event: GameEvent, snapshot: GameSnapshot, ally_team: str) -> list[SummaryMoment]:
    """Return the moment an entry of the feed is, alone; nothing for an entry left out.

    Args:
        event: The entry.
        snapshot: The game's state, for who is who.
        ally_team: Your team.

    Returns:
        The moment, or nothing.
    """
    if event.event_name == CHAMPION_KILL_EVENT:
        return _kill_moments(event, snapshot, ally_team)
    killer_team = snapshot.team_of(event.killer_name)
    taken = _what_was_taken(event, ally_team)
    if killer_team is None or taken is None:
        return []
    kind, words = taken
    team_words = "your team" if killer_team == ally_team else "their team"
    return [
        SummaryMoment(
            game_time_seconds=event.event_time_seconds,
            kind=kind,
            side="ally" if killer_team == ally_team else "enemy",
            text=f"{team_words} took {words}",
        )
    ]


def _kill_moments(event: GameEvent, snapshot: GameSnapshot, ally_team: str) -> list[SummaryMoment]:
    """Return the moment of a champion's death, alone; nothing when the victim is not known.

    Args:
        event: The kill.
        snapshot: The game's state, for who is who.
        ally_team: Your team.

    Returns:
        "Zed killed Ahri", good for the killer's side; or "Ahri died", to a turret or a monster,
        good for the other side.
    """
    killer = snapshot.player_named(event.killer_name)
    victim = snapshot.player_named(event.victim_name)
    if victim is None:
        return []
    is_your_good = killer.team == ally_team if killer is not None else victim.team != ally_team
    return [
        SummaryMoment(
            game_time_seconds=event.event_time_seconds,
            kind="kill",
            side="ally" if is_your_good else "enemy",
            text=(
                f"{killer.champion_name} killed {victim.champion_name}"
                if killer is not None
                else f"{victim.champion_name} died"
            ),
        )
    ]


def _what_was_taken(event: GameEvent, ally_team: str) -> tuple[MomentKind, str] | None:
    """Return a monster or a structure the feed says was taken, in words from your side.

    Args:
        event: An entry of the feed.
        ally_team: Your team.

    Returns:
        Its kind, and such as "the Fire dragon" or "their top outer turret"; None for another
        entry.
    """
    if event.event_name == DRAGON_KILL_EVENT:
        if event.dragon_type == ELDER_DRAGON_TYPE:
            return "elder", "the Elder Dragon"
        return "dragon", f"the {event.dragon_type} dragon"
    if event.event_name in MONSTER_BY_EVENT:
        return MONSTER_BY_EVENT[event.event_name]
    return _structure_words(event, ally_team)


def _structure_words(
    event: GameEvent, ally_team: str
) -> tuple[Literal["turret", "inhibitor"], str] | None:
    """Return a turret or an inhibitor the feed says fell, in words from your side.

    Args:
        event: An entry of the feed.
        ally_team: Your team.

    Returns:
        Its kind, and such as "their top outer turret"; None for another entry.
    """
    if event.event_name == TURRET_KILLED_EVENT:
        turret_match = TURRET_NAME_PATTERN.match(event.turret_killed_name or "")
        if turret_match is None:
            return None
        whose = "your" if TEAM_BY_NUMBER[turret_match["team"]] == ally_team else "their"
        tier = TURRET_TIER_BY_LANE_AND_PLACE.get(
            (turret_match["lane"], int(turret_match["place"])), "base"
        )
        if tier == "nexus":
            return "turret", f"{whose} nexus turret"
        return "turret", f"{whose} {LANE_BY_LETTER[turret_match['lane']]} {tier} turret"
    if event.event_name == INHIBITOR_KILLED_EVENT:
        inhibitor_match = INHIBITOR_NAME_PATTERN.match(event.inhibitor_killed_name or "")
        if inhibitor_match is None:
            return None
        whose = "your" if TEAM_BY_NUMBER[inhibitor_match["team"]] == ally_team else "their"
        return "inhibitor", f"{whose} {LANE_BY_LETTER[inhibitor_match['lane']]} inhibitor"
    return None


def _your_champion(snapshot: GameSnapshot) -> str | None:
    """Return the champion of the player on this machine.

    Args:
        snapshot: The game's state.

    Returns:
        The champion's name; None when spectating.
    """
    return next(
        (player.champion_name for player in snapshot.players if snapshot.is_active_player(player)),
        None,
    )


if __name__ == "__main__":
    # `python -m leagueasymode.game_summary` prints the page's contract, kept in
    # overlay/web/game_summary.schema.json beside the TypeScript that mirrors it.
    sys.stdout.write(json.dumps(GameSummary.model_json_schema(), indent=2) + "\n")
