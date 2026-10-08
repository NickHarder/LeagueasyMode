"""What the engine tells the overlay: the contract between the Python engine and the widgets.

The overlay's widgets read this as JSON from `/state` and `/events`; `overlay/web/src/state.ts`
declares the same shape for TypeScript. The contract's JSON Schema is kept beside it in
`overlay/web/overlay_state.schema.json`, and a test fails when the two differ, so a change here
shows up in review next to the TypeScript that has to follow it.
"""

import json
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class OverlayState(BaseModel):
    """Everything the overlay shows at one moment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_game_running: bool
    game_time_seconds: float | None = None
    dragon: DragonTimer | None = None


if __name__ == "__main__":
    # `python -m leagueasymode.overlay_state` prints the contract's JSON Schema, which is kept in
    # overlay/web/overlay_state.schema.json beside the TypeScript that mirrors it.
    sys.stdout.write(json.dumps(OverlayState.model_json_schema(), indent=2) + "\n")
