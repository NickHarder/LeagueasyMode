"""The roast's hand-set thresholds, which `tuning.json` can change (`tuning.py`)."""

from pydantic import BaseModel, ConfigDict, Field


class LaneRules(BaseModel):
    """When a lane counts as won, lost or a gap, by gold against its opponent at 14:00."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    won_gold: int = Field(default=500, ge=1)
    gap_gold: int = Field(default=1500, ge=1)


class VerdictRules(BaseModel):
    """The counts the verdict's rules turn on (roast/verdict.py)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    smurf_kills: int = Field(default=10, ge=1)
    smurf_distinct_victims: int = Field(default=4, ge=1)
    guilty_held_lanes: int = Field(default=3, ge=1)
    team_diff_lost_lanes: int = Field(default=2, ge=1)


class MomentRules(BaseModel):
    """When a friend's game hands over a moment (roast/moments.py, phase 11.6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # The deaths to the lane opponent with no help that each make a moment.
    solo_death_counts: tuple[int, ...] = (2, 3)
    # A death this long or less before the enemy takes a dragon, the Elder or Baron.
    before_objective_seconds: float = Field(default=60.0, gt=0)
    # Creep score behind the lane opponent at 10:00 and at 14:00.
    creep_behind_at_ten: int = Field(default=20, ge=1)
    creep_behind_at_fourteen: int = Field(default=30, ge=1)
    # Kills by the lane opponent on the friend, while the friend has none.
    opponent_kills_without_reply: int = Field(default=3, ge=1)
    # How long a moment shows on the overlay, in game seconds.
    shown_seconds: float = Field(default=8.0, gt=0)


class TeamCallRules(BaseModel):
    """When the team gets a call (roast/team_calls.py, phase 11.9)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # At most one call this often, in game seconds.
    least_gap_seconds: float = Field(default=60.0, gt=0)
    # A death this recently is a fight still on, and a call waits for it to end, as the callouts do
    # (`CalloutRules.fight_quiet_seconds`).
    fight_quiet_seconds: float = Field(default=8.0, ge=0)
    # An epic monster spawning this soon, from the first figure to the second.
    objective_soon_from_seconds: float = Field(default=60.0, ge=0)
    objective_soon_until_seconds: float = Field(default=90.0, gt=0)
    # This many enemies dead, each for at least this much longer, with this many of us alive.
    enemies_down_count: int = Field(default=2, ge=1)
    enemies_down_seconds: float = Field(default=20.0, gt=0)
    enemies_down_allies_alive: int = Field(default=3, ge=1)
    # A fight lost: this many of us dead at once, and fewer of them.
    fight_lost_allies_dead: int = Field(default=3, ge=1)
    # A teammate's deaths within this long.
    death_streak_deaths: int = Field(default=3, ge=2)
    death_streak_seconds: float = Field(default=240.0, gt=0)
    # Behind by at least this much estimated gold, with at least this win chance.
    behind_gold: int = Field(default=2000, ge=1)
    winnable_chance: float = Field(default=0.35, ge=0.0, le=1.0)
    # How long a call shows on the overlay, in game seconds.
    shown_seconds: float = Field(default=8.0, gt=0)


class RoastRules(BaseModel):
    """Every hand-set threshold of the roast."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lanes: LaneRules = Field(default_factory=LaneRules)
    verdict: VerdictRules = Field(default_factory=VerdictRules)
    moments: MomentRules = Field(default_factory=MomentRules)
    team_calls: TeamCallRules = Field(default_factory=TeamCallRules)
    # The longest line chat takes; Riot publishes none, so it is a guess until measured in a game.
    chat_line_max_characters: int = Field(default=140, ge=20)
