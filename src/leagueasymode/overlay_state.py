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


class RankedStanding(BaseModel):
    """A player's rank in one ranked queue this season."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    queue: Literal["solo", "flex"]
    # As the client names it: "IRON" to "CHALLENGER"; the division "I" to "IV".
    tier: str
    division: str
    league_points: int
    wins: int
    losses: int


class PlayerIntel(BaseModel):
    """What a player's record says before the game: rank, recent form, and the champion and role.

    From the League client's ranked stats and match history for the player. The recent games are
    those on Summoner's Rift, remakes left out.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Solo queue's rank, or flex's when solo has none; None when unranked or unknown.
    ranked: RankedStanding | None
    recent_game_count: int
    recent_win_count: int
    # Wins in a row from the latest game when positive, losses when negative.
    streak: int
    champion_game_count: int
    champion_win_count: int
    # The position most of their recent games were in, when one clearly is; empty otherwise.
    usual_position: str
    # Whether this game's position is not their usual one.
    is_off_role: bool


class GoldEstimate(BaseModel):
    """A player's gold: what they have earned this game, and what they hold unspent.

    Exact for the player on this machine, whose gold the game gives; their total adds what they
    own and what they drank, placed or lost on a sale. For the others an estimate
    (`inference/gold.py`), with a band that holds the truth about 4 times in 5.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["exact", "estimate"]
    # Earned this game, the starting gold included.
    total_gold: int
    unspent_gold: int
    # Half the band's width, in gold; 0 when exact.
    band_gold: int


class LevelEstimate(BaseModel):
    """How far a player is to their next level, and when they reach the next of 6, 11 and 16.

    An estimate for every player, yours included: the scoreboard gives levels, not experience.
    Each level-up seen pins a player's experience; between them it grows at their own rate
    (`inference/experience.py`), with a band that holds the truth about 4 times in 5.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Earned this game.
    experience: int
    band_experience: int
    # From 0 to 1; None from level 18.
    progress_to_next_level: float | None
    # 6, 11 or 16, the next level that ranks up an ultimate; None past 16.
    next_power_level: int | None
    power_level_at_game_time_seconds: float | None
    # Half the band of that time, in seconds.
    power_level_band_seconds: float | None


class BackEstimate(BaseModel):
    """A player's last trip to base: when they shopped, and when they are back where they play.

    Inferred (`inference/backs.py`): buying needs the fountain, so a purchase made alive is a trip
    to base; the way back is an estimate, the walk from the fountain at their move speed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    shopped_at_game_time_seconds: float
    # When they are back in their lane, or in their jungle.
    returns_at_game_time_seconds: float


class NextItemEstimate(BaseModel):
    """A player's likely next finished item, what it still costs them, and when they can buy it.

    An estimate (`inference/build_path.py`), from the components they hold, their champion's
    class and what they built on it lately.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: int
    item_name: str
    # Its share of the chance among every finished item they might buy next, from 0 to 1.
    likelihood: float
    # Its price less the components they hold toward it.
    remaining_gold: int
    # The chance they hold that much now, and when they will at their income so far; None while
    # their gold is not followed.
    chance_to_afford: float | None
    affordable_at_game_time_seconds: float | None


class PositionClue(BaseModel):
    """A moment a player's place was known, or nearly: what pinned it, when, and where.

    Inferred from the feed and the scoreboard (`inference/clues.py`): an objective's takers were
    at it, a respawn or a trip to base is in base, creep score rising is in a lane or the jungle.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["fountain", "objective", "turret", "lane", "jungle"]
    game_time_seconds: float
    # Where, in words: "at Dragon", "at the top outer turret", "in base", "in the mid lane".
    place: str
    # The map's point (`inference/rift_map.py`), when the clue names one.
    point_name: str | None
    # The map's region, or "order_jungle" or "chaos_jungle" for somewhere in a team's jungle.
    region: str


class RegionChance(BaseModel):
    """The chance a player is in one region of the map."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # The map's region (`inference/rift_map.py`), and in words from the player's side: "bot
    # lane", "their top jungle", "your base".
    region: str
    label: str
    chance: float
    # The region's middle, in the game's coordinates (x to the right, y up, from the blue
    # team's corner), for the minimap.
    x_position: float
    y_position: float


class PositionEstimate(BaseModel):
    """Where a player likely is now, and how soon they could be in each lane.

    An estimate (`inference/positions.py`), from their latest clue, their move speed and where a
    player of their role spends their time; it widens as the clue ages.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # The likeliest regions, most likely first, at most three.
    regions: list[RegionChance]
    # The chance they are away from where they play: their lane, or their jungle.
    away_chance: float
    # Since their latest clue; None without one.
    unseen_seconds: float | None
    # The soonest they could be in the middle of each lane; 0 when they could be there now.
    reach_top_seconds: float
    reach_mid_seconds: float
    reach_bot_seconds: float


class PlayerCard(BaseModel):
    """One player as the scoreboard shows them: side, role, level, and when they are back."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    champion_name: str
    side: Literal["ally", "enemy"]
    # Whether this is the player on this machine.
    is_you: bool = False
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
    # None until the League client has answered for this player.
    intel: PlayerIntel | None = None
    # None while the engine does not follow the game's gold.
    gold: GoldEstimate | None = None
    # None while the engine does not follow the players' experience.
    level_estimate: LevelEstimate | None = None
    # None until they are seen going back.
    last_back: BackEstimate | None = None
    # None while the patch's items are unknown, or no finished item is left for them.
    next_item: NextItemEstimate | None = None
    # The latest clue to where they are; None until there is one.
    last_clue: PositionClue | None = None
    # Where they likely are; None while dead, or while positions are not estimated.
    location: PositionEstimate | None = None


class TeamItemGold(BaseModel):
    """What each team's items are worth: gold earned and spent, not gold in hand."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ally_item_gold: int
    enemy_item_gold: int


class TeamGold(BaseModel):
    """What each team has earned this game: estimated, but for the player's own gold."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ally_total_gold: int
    enemy_total_gold: int
    # Half the band of the lead (ally minus enemy), in gold.
    lead_band_gold: int


class NumbersWindow(BaseModel):
    """More of the enemy team is dead than of the player's, until the respawn that evens it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ally_dead_count: int
    enemy_dead_count: int
    ends_at_game_time_seconds: float


class CooldownTimer(BaseModel):
    """A spell the player marked an enemy as having used, and when it is back.

    An estimate: the cooldown is the patch's, at the rank the enemy's level gives, shortened by
    the haste their items give; runes and other haste are not known, so it may be back sooner.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Stable for one mark, so that the widget and the callouts can tell marks apart.
    cooldown_id: str
    champion_name: str
    spell: Literal["flash", "summoner", "ultimate"]
    # The spell's name ("Flash", "Teleport", or "ultimate"), and the widget's short label for it.
    spell_name: str
    label: str
    marked_at_game_time_seconds: float
    ready_at_game_time_seconds: float


type CalloutKind = Literal[
    "numbers_window",
    "level_spike",
    "level_soon",
    "objective_soon",
    "item_spike",
    "item_soon",
    "cooldown_ready",
    "went_back",
    "missing",
    "suggestion",
]


class CampTimer(BaseModel):
    """A jungle camp a jungler likely cleared, and when it is back.

    An estimate (`inference/jungle_path.py`): which camps were cleared, and when, comes from the
    jungler's likely path.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # The map's point (`inference/rift_map.py`), and in words from your side: "their raptors".
    camp: str
    label: str
    cleared_by: Literal["ally", "enemy"]
    respawns_at_game_time_seconds: float
    # The camp, in the game's coordinates, for the minimap.
    x_position: float
    y_position: float


class JunglePath(BaseModel):
    """A jungler's likely clear: the camps lately, which side they are on, and the next camp."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    champion_name: str
    side: Literal["ally", "enemy"]
    # The last few camps in words, oldest first.
    recent_camps: list[str]
    last_cleared_at_game_time_seconds: float | None
    next_camp: str | None
    next_camp_at_game_time_seconds: float | None


class WardEstimate(BaseModel):
    """Where a player's control ward likely is: placed when their count dropped, where they were.

    An estimate (`inference/wards.py`): the moment is known from the inventory, the place is the
    position estimate's likeliest region then. Each player has one control ward down at a time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    champion_name: str
    side: Literal["ally", "enemy"]
    placed_at_game_time_seconds: float
    # The map's region, in words from your side, and the chance it is there.
    region: str
    label: str
    chance: float
    # The region's middle, in the game's coordinates, for the minimap.
    x_position: float
    y_position: float


class MinimapLayout(BaseModel):
    """Where League draws its minimap, from League's own settings (`game.cfg`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # League's minimap scale setting, 1 by default.
    scale: float
    # Whether the minimap is on the left (League's "flip minimap"); on the right otherwise.
    is_flipped: bool


class FightEstimate(BaseModel):
    """An even fight now: every living player of both teams, at full health, all at once.

    An estimate (`inference/fights.py`): each team's damage times its health against the other's
    damage, from the combat stats, as Lanchester's square law has it; hand-set until refit.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ally_chance: float
    ally_fighters: int
    enemy_fighters: int
    # The share of each team's damage that is physical, the rest magic.
    ally_physical_share: float
    enemy_physical_share: float


class ObjectiveContest(BaseModel):
    """A monster up or soon: how long the player's team takes, and whether the enemy can come.

    An estimate (`inference/contests.py`): the monster's health over the living team's damage,
    against each enemy's chance to reach its pit before it dies.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: Literal["dragon", "elder_dragon", "baron"]
    # From when it is up, with every living ally on it.
    kill_seconds: float
    ally_fighters: int
    # The chance at least one enemy reaches its pit before it dies, counting the wait for its
    # spawn; and the enemy likeliest to, with their chance.
    contest_chance: float
    likeliest_contester: str | None
    likeliest_chance: float


class DefenseValue(BaseModel):
    """What a hundred gold of one defensive stat buys you now, against the enemy's damage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    stat: Literal["armor", "magic_resist", "health"]
    effective_health_per_hundred_gold: float


class YouPanel(BaseModel):
    """Facts about your build and pace (`inference/you.py`), from your own exact numbers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Armor, magic resist and health, the one that buys the most effective health first; empty
    # while the enemy's damage is unknown.
    defenses: list[DefenseValue]
    # The share of the enemy's damage that is physical; None while unknown.
    enemy_physical_share: float | None
    unspent_gold: int
    # How long your unspent gold has stayed at the threshold or more while alive; None while not.
    holding_gold_seconds: float | None
    # Your creep score a minute this game, from 3:00; and over your recent games, when known.
    creep_score_per_minute: float | None
    usual_creep_score_per_minute: float | None


class WinReason(BaseModel):
    """One thing moving the win chance, from the player's side."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Such as "gold +2.1k", "their Baron" or "5v3".
    label: str
    # Its pull on the log-odds of a win: above 0 for the player's team, below for the other.
    effect: float


class WinChance(BaseModel):
    """The chance the player's team wins, and the two things moving it most.

    An estimate (`inference/win_chance.py`): a logistic model over the gold lead, levels,
    structures, monsters and players alive, with hand-set weights until refit on recorded games.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ally_chance: float
    reasons: list[WinReason]


class Callout(BaseModel):
    """A short notice shown for a few seconds when something happens.

    Most state a fact; a suggestion names an action.
    """

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
    team_gold: TeamGold | None = None
    cooldowns: list[CooldownTimer] = Field(default_factory=list)
    jungle_paths: list[JunglePath] = Field(default_factory=list)
    camp_timers: list[CampTimer] = Field(default_factory=list)
    control_wards: list[WardEstimate] = Field(default_factory=list)
    # None while League's settings are not known; the minimap layer then takes the default place.
    minimap: MinimapLayout | None = None
    win_chance: WinChance | None = None
    # None while any living player's combat stats are unknown.
    fight: FightEstimate | None = None
    contests: list[ObjectiveContest] = Field(default_factory=list)
    # None while the engine does not follow you, or when spectating.
    you: YouPanel | None = None
    callouts: list[Callout] = Field(default_factory=list)


if __name__ == "__main__":
    # `python -m leagueasymode.overlay_state` prints the contract's JSON Schema, which is kept in
    # overlay/web/overlay_state.schema.json beside the TypeScript that mirrors it.
    sys.stdout.write(json.dumps(OverlayState.model_json_schema(), indent=2) + "\n")
