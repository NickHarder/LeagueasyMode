"""Jungle path (estimator 8): each jungler's likely clear, their next camp, and when camps are back.

A jungler's creep score rises in bursts, one a camp: rises within a few seconds of each other are
one camp, finished at the last. Which camp each burst was is decoded from what is possible: a
camp is up at its first spawn and then its respawn after it was last cleared, and between two
camps the jungler walks the map (`rift_map.py`) at their move speed and takes the camp's clear
time. Among the paths that fit, the likeliest wastes the least time between camps and stays in
their own jungle. The respawn rule depends on the whole path, not only its last camp, so the
decoding keeps the best paths with their history (a beam search: Viterbi decoding with memory)
rather than the last camp alone.

From the likeliest path: the camps lately, the next camp (the soonest they could start, their own
side first), and when each camp it cleared is back. The camps' timings are from past seasons and
unconfirmed for this one (a 2026 change may have moved the first spawns earlier); the first
recording's jungle creep score settles them.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.gold import NEW_GAME_SLACK_SECONDS, PlayerKey, player_key
from leagueasymode.inference.rift_map import RIFT_MAP, TEAM_PREFIX, fountain_of
from leagueasymode.inference.roles import assign_roles
from leagueasymode.overlay_state import CampTimer, JunglePath

# Each team's camps by kind, and the two scuttle crabs in the river.
TEAM_CAMP_KINDS: Final = ("blue_buff", "gromp", "wolves", "raptors", "red_buff", "krugs")
SCUTTLES: Final = ("top_river_scuttle", "bot_river_scuttle")
CAMP_WORDS: Final = {
    "blue_buff": "blue",
    "gromp": "gromp",
    "wolves": "wolves",
    "raptors": "raptors",
    "red_buff": "red",
    "krugs": "krugs",
    "top_river_scuttle": "top scuttle",
    "bot_river_scuttle": "bot scuttle",
}
BUFF_KINDS: Final = frozenset({"blue_buff", "red_buff"})
RECENT_CAMP_COUNT: Final = 3


@dataclass(frozen=True)
class CampRules:
    """When camps are up, how long they take, and how the decoding weighs a path."""

    # Unconfirmed: past seasons' timings.
    first_spawn_seconds: float = 90.0
    scuttle_first_spawn_seconds: float = 210.0
    buff_respawn_seconds: float = 300.0
    camp_respawn_seconds: float = 135.0
    scuttle_respawn_seconds: float = 150.0
    # A first guess at how long each camp takes.
    clear_seconds: Mapping[str, float] = field(
        default_factory=lambda: {
            "blue_buff": 12.0,
            "gromp": 10.0,
            "wolves": 9.0,
            "raptors": 9.0,
            "red_buff": 12.0,
            "krugs": 12.0,
            "top_river_scuttle": 8.0,
            "bot_river_scuttle": 8.0,
        }
    )
    # Creep score rises this close together are one camp.
    burst_gap_seconds: float = 6.0
    # A camp may finish this much after its burst, for the poll's delay.
    slack_seconds: float = 6.0
    # A path loses one unit of log chance for each this many seconds wasted between camps.
    waste_scale_seconds: float = 20.0
    # A camp of the other team's jungle is this much less likely than one of their own.
    enemy_camp_share: float = 0.3
    # A path that cannot fit a burst at all loses this much log chance, so that it still goes on.
    impossible_penalty: float = 5.0
    beam_width: int = 40
    default_move_speed: float = 380.0


CAMP_RULES: Final = CampRules()


@dataclass(frozen=True)
class _Path:
    """One way the bursts so far could have gone: the camps cleared, with when, and its score."""

    clears: tuple[tuple[str, float], ...]
    log_chance: float


@dataclass
class _Jungler:
    """What the tracker remembers of one jungler between answers."""

    creep_score: int
    burst_ends_seconds: list[float] = field(default_factory=list)
    decoded_burst_count: int = 0
    paths: list[_Path] = field(default_factory=lambda: [_Path(clears=(), log_chance=0.0)])


def camps_of_game() -> tuple[str, ...]:
    """Return every jungle camp of the map, by its point's name.

    Returns:
        Both teams' camps and the scuttle crabs.
    """
    return (
        *(f"{prefix}_{kind}" for prefix in TEAM_PREFIX.values() for kind in TEAM_CAMP_KINDS),
        *SCUTTLES,
    )


def camp_kind(camp: str) -> str:
    """Return a camp's kind, without its team.

    Args:
        camp: The camp's point name, such as "chaos_raptors".

    Returns:
        Such as "raptors" or "top_river_scuttle".
    """
    team_prefix, _, kind = camp.partition("_")
    return kind if team_prefix in TEAM_PREFIX.values() else camp


def travel_seconds(from_point: str, to_point: str, move_speed: float) -> float:
    """Return how long a walk along the map takes.

    Args:
        from_point: Where it starts.
        to_point: Where it ends.
        move_speed: The walker's speed, in game units a second.

    Returns:
        The seconds.
    """
    return RIFT_MAP.distance(from_point, to_point) / move_speed


class JunglePathTracker:
    """Follows both junglers' clears through a game, one answer of the game's API after another.

    A game time well before the last one seen starts a new game, and the tracker over.
    """

    def __init__(self, rules: CampRules = CAMP_RULES) -> None:
        """Start with no game.

        Args:
            rules: When camps are up, and how a path is weighed.
        """
        self.rules: Final = rules
        self._junglers: Final[dict[PlayerKey, _Jungler]] = {}
        self._last_game_time_seconds = 0.0

    def update(
        self, snapshot: GameSnapshot, move_speeds: Mapping[PlayerKey, float] | None = None
    ) -> tuple[list[JunglePath], list[CampTimer]]:
        """Take in one answer of the game's API, and return the junglers' paths and camp timers.

        Args:
            snapshot: The game's state.
            move_speeds: Each player's move speed; the default speed for one not given.

        Returns:
            Each jungler's path, and every camp cleared that is not back yet, soonest first.
        """
        game_time_seconds = snapshot.game_data.game_time_seconds
        if game_time_seconds < self._last_game_time_seconds - NEW_GAME_SLACK_SECONDS:
            self._junglers.clear()
        self._last_game_time_seconds = game_time_seconds
        ally_team = snapshot.ally_team()
        paths: list[JunglePath] = []
        timers: list[CampTimer] = []
        for player, role_guess in zip(snapshot.players, assign_roles(snapshot), strict=True):
            if role_guess.role != "JUNGLE":
                continue
            key = player_key(player)
            move_speed = (move_speeds or {}).get(key, self.rules.default_move_speed)
            jungler = self._junglers.setdefault(
                key, _Jungler(creep_score=player.scores.creep_score)
            )
            self._take_creep_score(jungler, player.scores.creep_score, game_time_seconds)
            self._decode_new_bursts(jungler, player.team, move_speed, game_time_seconds)
            side: Literal["ally", "enemy"] = "ally" if player.team == ally_team else "enemy"
            best = max(jungler.paths, key=lambda path: path.log_chance)
            paths.append(
                self._jungle_path(
                    player.champion_name,
                    side,
                    player.team,
                    best,
                    move_speed=move_speed,
                    ally_team=ally_team,
                    game_time_seconds=game_time_seconds,
                )
            )
            timers.extend(self._camp_timers(best, side, ally_team, game_time_seconds))
        return paths, sorted(timers, key=lambda timer: timer.respawns_at_game_time_seconds)

    def last_clears(self) -> dict[PlayerKey, tuple[str, float]]:
        """Return each jungler's last camp on their likeliest path, and when they finished it.

        Returns:
            The camp's point and the game time, by key; a jungler with no camp yet is left out.
        """
        best_paths = {
            key: max(jungler.paths, key=lambda path: path.log_chance)
            for key, jungler in self._junglers.items()
        }
        return {key: path.clears[-1] for key, path in best_paths.items() if path.clears}

    def _take_creep_score(
        self, jungler: _Jungler, creep_score: int, game_time_seconds: float
    ) -> None:
        """Add a rise of creep score to the jungler's bursts.

        Args:
            jungler: The jungler's state.
            creep_score: Their creep score now.
            game_time_seconds: The game's clock.
        """
        if creep_score <= jungler.creep_score:
            return
        jungler.creep_score = creep_score
        bursts = jungler.burst_ends_seconds
        is_same_burst = (
            len(bursts) > jungler.decoded_burst_count
            and game_time_seconds - bursts[-1] <= self.rules.burst_gap_seconds
        )
        if is_same_burst:
            bursts[-1] = game_time_seconds
        else:
            bursts.append(game_time_seconds)

    def _decode_new_bursts(
        self, jungler: _Jungler, team: str, move_speed: float, game_time_seconds: float
    ) -> None:
        """Extend the jungler's paths with each burst that is over.

        A burst is over once no rise has come for the burst gap; the one under way waits.

        Args:
            jungler: The jungler's state.
            team: Their team.
            move_speed: Their move speed.
            game_time_seconds: The game's clock.
        """
        bursts = jungler.burst_ends_seconds
        while jungler.decoded_burst_count < len(bursts):
            burst_end_seconds = bursts[jungler.decoded_burst_count]
            is_last = jungler.decoded_burst_count == len(bursts) - 1
            if is_last and game_time_seconds - burst_end_seconds <= self.rules.burst_gap_seconds:
                return
            jungler.paths = self._extended(jungler.paths, burst_end_seconds, team, move_speed)
            jungler.decoded_burst_count += 1

    def _extended(
        self, paths: list[_Path], burst_end_seconds: float, team: str, move_speed: float
    ) -> list[_Path]:
        """Return the best paths that add one camp, finished by a burst's end, to each path.

        Args:
            paths: The paths so far.
            burst_end_seconds: When the burst ended.
            team: The jungler's team.
            move_speed: Their move speed.

        Returns:
            The best paths, as many as the beam holds.
        """
        rules = self.rules
        candidates = [
            _Path(
                clears=(*path.clears, (camp, burst_end_seconds)),
                log_chance=path.log_chance
                + self._step_log_chance(path, camp, burst_end_seconds, team, move_speed),
            )
            for path in paths
            for camp in camps_of_game()
        ]
        return sorted(candidates, key=lambda path: path.log_chance, reverse=True)[
            : rules.beam_width
        ]

    def _step_log_chance(
        self, path: _Path, camp: str, burst_end_seconds: float, team: str, move_speed: float
    ) -> float:
        """Return the log chance a path's next camp was this one, finished by a burst's end.

        Args:
            path: The path so far.
            camp: The camp.
            burst_end_seconds: When the burst ended.
            team: The jungler's team.
            move_speed: Their move speed.

        Returns:
            The log chance: the time wasted, and the other team's camp, cost; a camp that could
            not have been finished costs the most.
        """
        rules = self.rules
        last_point, last_seconds = path.clears[-1] if path.clears else (fountain_of(team), 0.0)
        arrives_at_seconds = last_seconds + travel_seconds(last_point, camp, move_speed)
        starts_at_seconds = max(arrives_at_seconds, self._up_at(path, camp))
        finishes_at_seconds = starts_at_seconds + rules.clear_seconds[camp_kind(camp)]
        own_prefix = TEAM_PREFIX.get(team, "order")
        side_log_chance = (
            0.0
            if camp.startswith(own_prefix) or camp in SCUTTLES
            else math.log(rules.enemy_camp_share)
        )
        if finishes_at_seconds > burst_end_seconds + rules.slack_seconds:
            late_seconds = finishes_at_seconds - burst_end_seconds
            return (
                side_log_chance
                - rules.impossible_penalty
                - late_seconds / rules.waste_scale_seconds
            )
        wasted_seconds = max(0.0, burst_end_seconds - finishes_at_seconds)
        return side_log_chance - wasted_seconds / rules.waste_scale_seconds

    def _up_at(self, path: _Path, camp: str) -> float:
        """Return when a camp is up, as a path has it: its first spawn, or its last respawn.

        Args:
            path: The path.
            camp: The camp.

        Returns:
            The game time.
        """
        rules = self.rules
        kind = camp_kind(camp)
        last_cleared = next(
            (cleared_at for cleared, cleared_at in reversed(path.clears) if cleared == camp), None
        )
        if last_cleared is None:
            return (
                rules.scuttle_first_spawn_seconds if camp in SCUTTLES else rules.first_spawn_seconds
            )
        return last_cleared + self._respawn_seconds(kind)

    def _respawn_seconds(self, kind: str) -> float:
        """Return how long a camp of a kind takes to come back.

        Args:
            kind: The camp's kind.

        Returns:
            The seconds.
        """
        rules = self.rules
        if kind in BUFF_KINDS:
            return rules.buff_respawn_seconds
        if kind in SCUTTLES:
            return rules.scuttle_respawn_seconds
        return rules.camp_respawn_seconds

    def _jungle_path(
        self,
        champion_name: str,
        side: Literal["ally", "enemy"],
        team: str,
        best: _Path,
        *,
        move_speed: float,
        ally_team: str,
        game_time_seconds: float,
    ) -> JunglePath:
        """Return a jungler's likely path in words, with their likely next camp.

        Args:
            champion_name: The jungler's champion.
            side: Their side.
            team: Their team.
            best: Their likeliest path.
            move_speed: Their move speed.
            ally_team: The team of the player on this machine, for the words.
            game_time_seconds: The game's clock.

        Returns:
            The path.
        """
        last_point, last_seconds = best.clears[-1] if best.clears else (fountain_of(team), 0.0)
        own_prefix = TEAM_PREFIX.get(team, "order")
        next_starts = {
            camp: max(
                last_seconds + travel_seconds(last_point, camp, move_speed),
                self._up_at(best, camp),
                game_time_seconds,
            )
            for camp in camps_of_game()
            if camp.startswith(own_prefix) and camp != last_point
        }
        next_camp = min(next_starts, key=lambda camp: next_starts[camp]) if next_starts else None
        return JunglePath(
            champion_name=champion_name,
            side=side,
            recent_camps=[
                camp_label(camp, ally_team) for camp, _ in best.clears[-RECENT_CAMP_COUNT:]
            ],
            last_cleared_at_game_time_seconds=last_seconds if best.clears else None,
            next_camp=camp_label(next_camp, ally_team) if next_camp is not None else None,
            next_camp_at_game_time_seconds=next_starts[next_camp]
            if next_camp is not None
            else None,
        )

    def _camp_timers(
        self,
        best: _Path,
        side: Literal["ally", "enemy"],
        ally_team: str,
        game_time_seconds: float,
    ) -> list[CampTimer]:
        """Return the camps a path cleared that are not back yet.

        Args:
            best: The jungler's likeliest path.
            side: The jungler's side.
            ally_team: The team of the player on this machine, for the words.
            game_time_seconds: The game's clock.

        Returns:
            One timer for each camp, from its last clear.
        """
        last_clears = dict(best.clears)
        return [
            CampTimer(
                camp=camp,
                label=camp_label(camp, ally_team),
                cleared_by=side,
                respawns_at_game_time_seconds=cleared_at + self._respawn_seconds(camp_kind(camp)),
            )
            for camp, cleared_at in last_clears.items()
            if cleared_at + self._respawn_seconds(camp_kind(camp)) > game_time_seconds
        ]


def camp_label(camp: str, ally_team: str) -> str:
    """Return a camp in words, from the side of the player on this machine.

    Args:
        camp: The camp's point name.
        ally_team: Their team.

    Returns:
        Such as "their raptors", "your blue" or "top scuttle".
    """
    kind = camp_kind(camp)
    if camp in SCUTTLES:
        return CAMP_WORDS[kind]
    whose = "your" if camp.startswith(TEAM_PREFIX.get(ally_team, "order")) else "their"
    return f"{whose} {CAMP_WORDS[kind]}"
