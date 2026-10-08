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


class CombatStats(BaseModel):
    """A player's combat stats.

    Exact for the player on this machine, whose stats the game gives in full. For the others an
    estimate: the champion's base stats grown to their level, plus their items' stats, at this
    patch's numbers; runes, passives, stacks and buffs are not counted.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["exact", "estimate"]
    health: float
    armor: float
    magic_resist: float
    attack_damage: float
    ability_power: float
    attack_speed: float
    move_speed: float


class PlayerCard(BaseModel):
    """One player as the scoreboard shows them: side, role, level, and when they are back."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    champion_name: str
    side: Literal["ally", "enemy"]
    # As the game names it ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"); empty when the queue
    # assigns none.
    position: str
    # The position when the game gives it, otherwise estimator 1's guess, and how sure that is.
    role: str = ""
    role_confidence: Literal["given", "likely", "guess", "unknown"] = "unknown"
    level: int
    is_dead: bool
    respawns_at_game_time_seconds: float | None
    # The patch price of everything in the inventory; None until the item catalog is known.
    item_gold: int | None = None
    finished_item_names: list[str] = Field(default_factory=list)
    # None until the patch's stats are known, except for the player on this machine.
    combat_stats: CombatStats | None = None


class TeamItemGold(BaseModel):
    """What each team's items are worth: gold earned and spent, not gold in hand."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ally_item_gold: int
    enemy_item_gold: int


class NumbersWindow(BaseModel):
    """More of the enemy team is dead than of the player's, until the respawn that evens it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ally_dead_count: int
    enemy_dead_count: int
    ends_at_game_time_seconds: float


type CalloutKind = Literal["numbers_window", "level_spike", "objective_soon", "item_spike"]


class Callout(BaseModel):
    """A short notice shown for a few seconds when something happens; never an instruction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Stable for one happening, so that the widget does not show it twice.
    callout_id: str
    kind: CalloutKind
    text: str
    shown_until_game_time_seconds: float


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
    team_item_gold: TeamItemGold | None = None
    callouts: list[Callout] = Field(default_factory=list)


if __name__ == "__main__":
    # `python -m leagueasymode.overlay_state` prints the contract's JSON Schema, which is kept in
    # overlay/web/overlay_state.schema.json beside the TypeScript that mirrors it.
    sys.stdout.write(json.dumps(OverlayState.model_json_schema(), indent=2) + "\n")
