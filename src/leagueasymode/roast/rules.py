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


class RoastRules(BaseModel):
    """Every hand-set threshold of the roast."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lanes: LaneRules = Field(default_factory=LaneRules)
    verdict: VerdictRules = Field(default_factory=VerdictRules)
    # The longest line chat takes; Riot publishes none, so it is a guess until measured in a game.
    chat_line_max_characters: int = Field(default=140, ge=20)
