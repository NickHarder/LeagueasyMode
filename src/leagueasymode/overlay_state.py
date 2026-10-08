"""What the engine tells the overlay: the contract between the Python engine and the widgets.

The overlay's widgets read this as JSON from `/state` and `/events`; `overlay/web/src/state.ts`
declares the same shape for TypeScript. The contract's JSON Schema is kept beside it in
`overlay/web/overlay_state.schema.json`, and a test fails when the two differ, so a change here
shows up in review next to the TypeScript that has to follow it.
"""

import json
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DragonTimer(BaseModel):
    """The next dragon or Elder Dragon: when it spawns, and the race for the soul.

    Every value restates the kill feed and the map; nothing here is estimated.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: Literal["dragon", "elder_dragon"]
    status: Literal["not_spawned", "respawning", "alive"]
    spawns_at_game_time_seconds: float
    ally_dragon_count: int
    enemy_dragon_count: int
    soul_type: str | None
    soul_holder: Literal["ally", "enemy"] | None


class ObjectiveTimer(BaseModel):
    """The next spawn of an epic monster other than the dragons.

    `is_rule_verified` is false while its spawn rule is not yet confirmed for this season, so the
    widget can mark the timer as provisional.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: Literal["baron", "rift_herald", "voidgrubs"]
    status: Literal["not_spawned", "respawning", "alive", "gone"]
    spawns_at_game_time_seconds: float | None
    is_rule_verified: bool


class BuffTimer(BaseModel):
    """A team's Baron or Elder buff, and when it runs out."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    buff: Literal["baron", "elder"]
    holder: Literal["ally", "enemy"]
    ends_at_game_time_seconds: float


class InhibitorTimer(BaseModel):
    """A destroyed inhibitor, and when it comes back."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    side: Literal["ally", "enemy"]
    lane: Literal["top", "mid", "bot"]
    respawns_at_game_time_seconds: float


class PlayerCard(BaseModel):
    """One player as the scoreboard shows them: side, role, level, and when they are back."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    champion_name: str
    side: Literal["ally", "enemy"]
    # As the game names it ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"); empty when the queue
    # assigns none.
    position: str
    level: int
    is_dead: bool
    respawns_at_game_time_seconds: float | None


class NumbersWindow(BaseModel):
    """More of the enemy team is dead than of the player's, until the respawn that evens it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ally_dead_count: int
    enemy_dead_count: int
    ends_at_game_time_seconds: float


class OverlayState(BaseModel):
    """Everything the overlay shows at one moment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_game_running: bool
    game_time_seconds: float | None = None
    dragon: DragonTimer | None = None
    objectives: list[ObjectiveTimer] = Field(default_factory=list)
    buffs: list[BuffTimer] = Field(default_factory=list)
    inhibitors: list[InhibitorTimer] = Field(default_factory=list)
    players: list[PlayerCard] = Field(default_factory=list)
    numbers_window: NumbersWindow | None = None


if __name__ == "__main__":
    # `python -m leagueasymode.overlay_state` prints the contract's JSON Schema, which is kept in
    # overlay/web/overlay_state.schema.json beside the TypeScript that mirrors it.
    sys.stdout.write(json.dumps(OverlayState.model_json_schema(), indent=2) + "\n")
