"""Hidden experience (estimator 4): how far each player is to their next level, and to 6, 11, 16.

The scoreboard gives every player's level and nobody's experience, yours included. A level-up
seen pins a player's experience at that moment: they have just what the level takes. Between
level-ups it grows at their own rate, measured on each level-up seen and weighed against the rate
before it; until one is seen, a prior for their role stands in: a solo laner's, a duo laner's
(two share a lane's experience), or a jungler's. It grows only while they are alive, and never
leaves the level the scoreboard gives. Kill experience and time spent in base are not counted
apart: the measured rate holds them on average.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from leagueasymode.game_state import GameSnapshot, ScoreboardPlayer
from leagueasymode.inference.gold import (
    BAND_STANDARD_DEVIATIONS,
    NEW_GAME_SLACK_SECONDS,
    PlayerKey,
    player_key,
)
from leagueasymode.inference.roles import assign_roles
from leagueasymode.overlay_state import LevelEstimate

type LaneKind = Literal["solo", "duo", "jungle"]

# The levels that rank up an ultimate.
POWER_LEVELS: Final = (6, 11, 16)
# No progress is shown from this level: the next is out of reach but for the top lane's quest.
LEVEL_CAP: Final = 18
LANE_KIND_BY_ROLE: Final[Mapping[str, LaneKind]] = {
    "TOP": "solo",
    "MIDDLE": "solo",
    "JUNGLE": "jungle",
    "BOTTOM": "duo",
    "UTILITY": "duo",
}
# A value known only to lie somewhere in a range has this share of the range as its spread.
UNIFORM_SPREAD_SHARE: Final = 1 / math.sqrt(12)


@dataclass(frozen=True)
class ExperienceRules:
    """When experience starts, the prior rates by role, and how sure a rate is."""

    # Minions reach the lanes, and the jungle's camps are up, at about 1:30.
    starts_at_seconds: float = 90.0
    # Experience a second while alive, before a level-up is seen: a solo laner reaches 6 at about
    # 6:15, a duo laner at about 8:15, a jungler at about 6:45. A first guess, to fit on
    # recordings.
    solo_rate: float = 8.5
    duo_rate: float = 6.0
    jungle_rate: float = 8.0
    # How unsure a rate is, as a share of it: the prior, and one measured on a level-up.
    prior_rate_uncertainty: float = 0.3
    measured_rate_uncertainty: float = 0.2
    # A level-up's measured rate weighs this much against the rate before it.
    measured_rate_weight: float = 0.6


EXPERIENCE_RULES: Final = ExperienceRules()


@dataclass(frozen=True)
class _Anchor:
    """The last moment a player's experience was estimated afresh."""

    # The player's time alive since experience started, at that moment.
    alive_seconds: float
    experience: float
    variance: float


@dataclass
class _PlayerExperience:
    """What the tracker remembers of one player between answers."""

    level: int
    anchor: _Anchor
    rate: float
    rate_uncertainty: float
    observed_at_seconds: float
    alive_seconds: float
    # Their time alive when they reached their level, when that was seen.
    level_reached_alive_seconds: float | None


def experience_to_reach(level: int) -> int:
    """Return the experience a champion needs for a level: 280 for 2, then 100 more each level.

    Args:
        level: The level.

    Returns:
        The experience from the game's start; 0 for level 1.
    """
    steps = level - 1
    return 180 * steps + 50 * steps * level


class ExperienceTracker:
    """Follows every player's experience through a game, one answer of the game's API after another.

    A game time well before the last one seen starts a new game, and the tracker over.
    """

    def __init__(self, rules: ExperienceRules = EXPERIENCE_RULES) -> None:
        """Start with no game.

        Args:
            rules: The rates and how sure they are.
        """
        self.rules: Final = rules
        self._players: Final[dict[PlayerKey, _PlayerExperience]] = {}
        self._last_game_time_seconds = 0.0

    def update(self, snapshot: GameSnapshot) -> dict[PlayerKey, LevelEstimate]:
        """Take in one answer of the game's API, and return every player's experience.

        Args:
            snapshot: The game's state.

        Returns:
            Each player's experience, by key.
        """
        game_time_seconds = snapshot.game_data.game_time_seconds
        if game_time_seconds < self._last_game_time_seconds - NEW_GAME_SLACK_SECONDS:
            self._players.clear()
        self._last_game_time_seconds = game_time_seconds
        estimates: dict[PlayerKey, LevelEstimate] = {}
        for player, role_guess in zip(snapshot.players, assign_roles(snapshot), strict=True):
            key = player_key(player)
            known = self._players.get(key)
            state = (
                self._first_sight(
                    player.level, self._prior_rate(role_guess.role), game_time_seconds
                )
                if known is None or player.level < known.level
                else self._follow(known, player, game_time_seconds)
            )
            self._players[key] = state
            estimates[key] = self._estimate(state, player, game_time_seconds)
        return estimates

    def _prior_rate(self, role: str) -> float:
        """Return the experience a second of a player in a role, before a level-up is seen.

        Args:
            role: The role, given or worked out; empty when unknown, taken as a solo lane.

        Returns:
            The rate.
        """
        lane_kind = LANE_KIND_BY_ROLE.get(role, "solo")
        if lane_kind == "jungle":
            return self.rules.jungle_rate
        return self.rules.duo_rate if lane_kind == "duo" else self.rules.solo_rate

    def _first_sight(
        self, level: int, prior_rate: float, game_time_seconds: float
    ) -> _PlayerExperience:
        """Return what is known of a player seen for the first time.

        At level 1 their experience is known: none. Above it, they are somewhere in their level:
        at the prior rate's estimate when that falls inside it, and halfway through it when it
        does not, since the prior is then wrong for them.

        Args:
            level: Their level.
            prior_rate: The rate of their role.
            game_time_seconds: The game's clock.

        Returns:
            Their state.
        """
        alive_seconds = max(0.0, game_time_seconds - self.rules.starts_at_seconds)
        level_floor = experience_to_reach(level)
        level_ceiling = experience_to_reach(level + 1)
        prior_experience = prior_rate * alive_seconds
        if level <= 1:
            anchor = _Anchor(alive_seconds=0.0, experience=0.0, variance=0.0)
        else:
            anchor = _Anchor(
                alive_seconds=alive_seconds,
                experience=(
                    prior_experience
                    if level_floor <= prior_experience < level_ceiling
                    else (level_floor + level_ceiling) / 2
                ),
                variance=((level_ceiling - level_floor) * UNIFORM_SPREAD_SHARE) ** 2,
            )
        return _PlayerExperience(
            level=level,
            anchor=anchor,
            rate=prior_rate,
            rate_uncertainty=self.rules.prior_rate_uncertainty,
            observed_at_seconds=game_time_seconds,
            alive_seconds=alive_seconds,
            level_reached_alive_seconds=0.0 if level <= 1 else None,
        )

    def _follow(
        self, state: _PlayerExperience, player: ScoreboardPlayer, game_time_seconds: float
    ) -> _PlayerExperience:
        """Count a player's time alive since the last answer, and take in a level-up.

        A level-up pins the experience; when the one before it was seen too, the experience
        between the two over the time alive between them is a measured rate.

        Args:
            state: The player's state.
            player: The player now.
            game_time_seconds: The game's clock.

        Returns:
            The same state, brought up to date.
        """
        counted_from_seconds = max(state.observed_at_seconds, self.rules.starts_at_seconds)
        if not player.is_dead:
            state.alive_seconds += max(0.0, game_time_seconds - counted_from_seconds)
        state.observed_at_seconds = game_time_seconds
        if player.level == state.level:
            return state
        reached_alive_seconds = state.level_reached_alive_seconds
        alive_between_seconds = (
            state.alive_seconds - reached_alive_seconds
            if reached_alive_seconds is not None
            else 0.0
        )
        if alive_between_seconds > 0:
            gained_experience = experience_to_reach(player.level) - experience_to_reach(state.level)
            weight = self.rules.measured_rate_weight
            state.rate = (
                weight * gained_experience / alive_between_seconds + (1 - weight) * state.rate
            )
            state.rate_uncertainty = self.rules.measured_rate_uncertainty
        state.level = player.level
        state.level_reached_alive_seconds = state.alive_seconds
        state.anchor = _Anchor(
            alive_seconds=state.alive_seconds,
            experience=float(experience_to_reach(player.level)),
            variance=0.0,
        )
        return state

    def _estimate(
        self, state: _PlayerExperience, player: ScoreboardPlayer, game_time_seconds: float
    ) -> LevelEstimate:
        """Return a player's experience, and when they reach their next power level.

        Args:
            state: The player's state.
            player: The player now, for when a dead one respawns.
            game_time_seconds: The game's clock.

        Returns:
            Their experience.
        """
        level_floor = experience_to_reach(state.level)
        level_ceiling = experience_to_reach(state.level + 1)
        alive_since_anchor_seconds = state.alive_seconds - state.anchor.alive_seconds
        grown_experience = state.anchor.experience + state.rate * alive_since_anchor_seconds
        experience = min(max(grown_experience, level_floor), level_ceiling - 1)
        band_experience = BAND_STANDARD_DEVIATIONS * math.sqrt(
            state.anchor.variance
            + (state.rate_uncertainty * state.rate * alive_since_anchor_seconds) ** 2
        )
        next_power_level = next((level for level in POWER_LEVELS if level > state.level), None)
        is_power_level_timed = next_power_level is not None and state.rate > 0
        respawns_at_seconds = game_time_seconds + (
            max(player.respawn_timer_seconds, 0.0) if player.is_dead else 0.0
        )
        grows_from_seconds = max(respawns_at_seconds, self.rules.starts_at_seconds)
        return LevelEstimate(
            experience=round(experience),
            band_experience=round(band_experience),
            progress_to_next_level=(
                (experience - level_floor) / (level_ceiling - level_floor)
                if state.level < LEVEL_CAP
                else None
            ),
            next_power_level=next_power_level,
            power_level_at_game_time_seconds=(
                grows_from_seconds
                + (experience_to_reach(next_power_level) - experience) / state.rate
                if next_power_level is not None and is_power_level_timed
                else None
            ),
            power_level_band_seconds=(
                band_experience / state.rate if is_power_level_timed else None
            ),
        )
