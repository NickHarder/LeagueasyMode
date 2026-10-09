/**
 * What the engine sends the overlay: the TypeScript side of `src/leagueasymode/overlay_state.py`.
 *
 * `overlay/web/overlay_state.schema.json` is that contract's JSON Schema, which a Python test keeps
 * current; a change to it shows up in review beside this file, which must change with it.
 */

export type DragonObjective = "dragon" | "elder_dragon";
export type DragonStatus = "not_spawned" | "respawning" | "alive";
export type Side = "ally" | "enemy";

/** The next dragon or Elder Dragon: when it spawns, and the race for the soul. */
export interface DragonTimer {
  readonly objective: DragonObjective;
  readonly status: DragonStatus;
  readonly spawns_at_game_time_seconds: number;
  readonly ally_dragon_count: number;
  readonly enemy_dragon_count: number;
  readonly soul_type: string | null;
  readonly soul_holder: Side | null;
}

export type EpicObjective = "baron" | "rift_herald" | "voidgrubs";
export type ObjectiveStatus = "not_spawned" | "respawning" | "alive" | "gone";
export type Lane = "top" | "mid" | "bot";

/** The next spawn of an epic monster other than the dragons. */
export interface ObjectiveTimer {
  readonly objective: EpicObjective;
  readonly status: ObjectiveStatus;
  readonly spawns_at_game_time_seconds: number | null;
  readonly is_rule_verified: boolean;
}

/** A team's Baron or Elder buff, and when it runs out. */
export interface BuffTimer {
  readonly buff: "baron" | "elder";
  readonly holder: Side;
  readonly ends_at_game_time_seconds: number;
}

/** A destroyed inhibitor, and when it comes back. */
export interface InhibitorTimer {
  readonly side: Side;
  readonly lane: Lane;
  readonly respawns_at_game_time_seconds: number;
}

/** One side's lane that has lost a turret: how many, and whether its inhibitor is open. Exact. */
export interface LaneStructures {
  readonly side: Side;
  readonly lane: Lane;
  readonly turrets_down: number;
  readonly is_inhibitor_exposed: boolean;
}

/**
 * A player's combat stats: exact for the player on this machine, from the game; for the others an
 * estimate from the champion's base stats, level and items, without runes, passives or buffs.
 */
export interface CombatStats {
  readonly source: "exact" | "estimate";
  readonly health: number;
  readonly armor: number;
  readonly magic_resist: number;
  readonly attack_damage: number;
  readonly ability_power: number;
  readonly attack_speed: number;
  readonly move_speed: number;
}

/** A player's rank in one ranked queue this season. */
export interface RankedStanding {
  readonly queue: "solo" | "flex";
  readonly tier: string;
  readonly division: string;
  readonly league_points: number;
  readonly wins: number;
  readonly losses: number;
}

/** What a player's record says before the game: rank, recent form, and the champion and role. */
export interface PlayerIntel {
  readonly ranked: RankedStanding | null;
  readonly recent_game_count: number;
  readonly recent_win_count: number;
  readonly streak: number;
  readonly champion_game_count: number;
  readonly champion_win_count: number;
  readonly usual_position: string;
  readonly is_off_role: boolean;
}

/** A spell the player marked an enemy as having used, and when it is back: an estimate. */
export interface CooldownTimer {
  readonly cooldown_id: string;
  readonly champion_name: string;
  readonly spell: "flash" | "summoner" | "ultimate";
  readonly spell_name: string;
  readonly label: string;
  readonly marked_at_game_time_seconds: number;
  readonly ready_at_game_time_seconds: number;
}

/**
 * A player's gold: earned this game and unspent. Exact for the player on this machine; for the
 * others an estimate, with a band that holds the truth about 4 times in 5.
 */
export interface GoldEstimate {
  readonly source: "exact" | "estimate";
  readonly total_gold: number;
  readonly unspent_gold: number;
  readonly band_gold: number;
}

/**
 * How far a player is to their next level, and when they reach the next of 6, 11 and 16: an
 * estimate for every player, with a band that holds the truth about 4 times in 5.
 */
export interface LevelEstimate {
  readonly experience: number;
  readonly band_experience: number;
  readonly progress_to_next_level: number | null;
  readonly next_power_level: number | null;
  readonly power_level_at_game_time_seconds: number | null;
  readonly power_level_band_seconds: number | null;
}

/** A player's last trip to base: when they shopped, and when they are back where they play. */
export interface BackEstimate {
  readonly shopped_at_game_time_seconds: number;
  readonly returns_at_game_time_seconds: number;
}

/** A player's likely next finished item, what it still costs them, and when they can buy it. */
export interface NextItemEstimate {
  readonly item_id: number;
  readonly item_name: string;
  readonly likelihood: number;
  readonly remaining_gold: number;
  readonly chance_to_afford: number | null;
  readonly affordable_at_game_time_seconds: number | null;
}

/** A moment a player's place was known, or nearly: what pinned it, when, and where. */
export interface PositionClue {
  readonly kind: "fountain" | "objective" | "turret" | "lane" | "jungle";
  readonly game_time_seconds: number;
  readonly place: string;
  readonly point_name: string | null;
  readonly region: string;
}

/** The chance a player is in one region of the map, with the region in words. */
export interface RegionChance {
  readonly region: string;
  readonly label: string;
  readonly chance: number;
  readonly x_position: number;
  readonly y_position: number;
}

/** Where a player likely is now, and how soon they could be in each lane: an estimate. */
export interface PositionEstimate {
  readonly regions: readonly RegionChance[];
  readonly away_chance: number;
  readonly unseen_seconds: number | null;
  readonly reach_top_seconds: number;
  readonly reach_mid_seconds: number;
  readonly reach_bot_seconds: number;
}

/** One player as the scoreboard shows them: side, role, level, and when they are back. */
export interface PlayerCard {
  readonly champion_name: string;
  readonly side: Side;
  readonly is_you: boolean;
  readonly position: string;
  readonly role: string;
  readonly role_confidence: "given" | "likely" | "guess" | "unknown";
  readonly level: number;
  readonly is_dead: boolean;
  readonly respawns_at_game_time_seconds: number | null;
  readonly item_gold: number | null;
  readonly finished_item_names: readonly string[];
  readonly combat_stats: CombatStats | null;
  readonly intel: PlayerIntel | null;
  readonly gold: GoldEstimate | null;
  readonly level_estimate: LevelEstimate | null;
  readonly last_back: BackEstimate | null;
  readonly next_item: NextItemEstimate | null;
  readonly last_clue: PositionClue | null;
  readonly location: PositionEstimate | null;
}

/** What each team's items are worth: gold earned and spent, not gold in hand. */
export interface TeamItemGold {
  readonly ally_item_gold: number;
  readonly enemy_item_gold: number;
}

/** What each team has earned this game: estimated, but for the player's own gold. */
export interface TeamGold {
  readonly ally_total_gold: number;
  readonly enemy_total_gold: number;
  readonly lead_band_gold: number;
}

/** More of the enemy team is dead than of the player's, until the respawn that evens it. */
export interface NumbersWindow {
  readonly ally_dead_count: number;
  readonly enemy_dead_count: number;
  readonly ends_at_game_time_seconds: number;
}

export type CalloutKind =
  | "numbers_window"
  | "level_spike"
  | "level_soon"
  | "objective_soon"
  | "item_spike"
  | "item_soon"
  | "cooldown_ready"
  | "went_back"
  | "missing"
  | "inhibitor_open"
  | "suggestion";

/** A short notice shown for a few seconds when something happens; never an instruction. */
export interface Callout {
  readonly callout_id: string;
  readonly kind: CalloutKind;
  readonly text: string;
  readonly shown_until_game_time_seconds: number;
}

/** A jungle camp a jungler likely cleared, and when it is back: an estimate. */
export interface CampTimer {
  readonly camp: string;
  readonly label: string;
  readonly cleared_by: Side;
  readonly respawns_at_game_time_seconds: number;
  readonly x_position: number;
  readonly y_position: number;
}

/** A jungler's likely clear: the camps lately, and their likely next camp. */
export interface JunglePath {
  readonly champion_name: string;
  readonly side: Side;
  readonly recent_camps: readonly string[];
  readonly last_cleared_at_game_time_seconds: number | null;
  readonly next_camp: string | null;
  readonly next_camp_at_game_time_seconds: number | null;
}

/** Where a player's control ward likely is: placed when their count dropped, where they were. */
export interface WardEstimate {
  readonly champion_name: string;
  readonly side: Side;
  readonly placed_at_game_time_seconds: number;
  readonly region: string;
  readonly label: string;
  readonly chance: number;
  readonly x_position: number;
  readonly y_position: number;
}

/** Where League draws its minimap, from League's own settings. */
export interface MinimapLayout {
  readonly scale: number;
  readonly is_flipped: boolean;
}

/** An even fight now, every living player at full health: an estimate. */
export interface FightEstimate {
  readonly ally_chance: number;
  readonly ally_fighters: number;
  readonly enemy_fighters: number;
  readonly ally_physical_share: number;
  readonly enemy_physical_share: number;
}

/** A monster up or soon: how long the player's team takes, and whether the enemy can come. */
export interface ObjectiveContest {
  readonly objective: "dragon" | "elder_dragon" | "baron";
  readonly kill_seconds: number;
  readonly ally_fighters: number;
  readonly contest_chance: number;
  readonly likeliest_contester: string | null;
  readonly likeliest_chance: number;
}

/** What a hundred gold of one defensive stat buys the player now, against the enemy's damage. */
export interface DefenseValue {
  readonly stat: "armor" | "magic_resist" | "health";
  readonly effective_health_per_hundred_gold: number;
}

/** Facts about the player's build and pace, from their own exact numbers. */
export interface YouPanel {
  readonly defenses: readonly DefenseValue[];
  readonly enemy_physical_share: number | null;
  readonly unspent_gold: number;
  readonly holding_gold_seconds: number | null;
  readonly creep_score_per_minute: number | null;
  readonly usual_creep_score_per_minute: number | null;
}

/** One thing moving the win chance, from the player's side: above 0 for their team. */
export interface WinReason {
  readonly label: string;
  readonly effect: number;
}

/** The chance the player's team wins, and the two things moving it most: an estimate. */
export interface WinChance {
  readonly ally_chance: number;
  readonly reasons: readonly WinReason[];
}

/** What the player chose to see, from the settings page; everything shows by default. */
export interface OverlayPreferences {
  readonly show_win_chance: boolean;
  readonly show_fight_chance: boolean;
  readonly show_contests: boolean;
  readonly show_you_panel: boolean;
  readonly show_minimap: boolean;
  readonly show_enemy_estimates: boolean;
  readonly show_callouts: boolean;
  readonly show_suggestions: boolean;
  readonly speak_callouts: boolean;
}

/** The preferences' names, in the settings page's order. */
export const PREFERENCE_NAMES = [
  "show_win_chance",
  "show_fight_chance",
  "show_contests",
  "show_you_panel",
  "show_minimap",
  "show_enemy_estimates",
  "show_callouts",
  "show_suggestions",
  "speak_callouts",
] as const satisfies readonly (keyof OverlayPreferences)[];

/** The widgets the player can move; the minimap layer stays over League's minimap. */
export const MOVABLE_WIDGETS = ["objective_strip", "callouts", "enemy_strip", "you_panel"] as const;

export type MovableWidget = (typeof MOVABLE_WIDGETS)[number];

/** How far the player moved a widget, as shares of the overlay's width and height. */
export interface WidgetOffset {
  readonly x_share: number;
  readonly y_share: number;
}

/** Where the player moved the widgets; a widget not named is in its usual place. */
export interface OverlayLayout {
  readonly offsets: Readonly<Partial<Record<MovableWidget, WidgetOffset>>>;
}

/** Everything the overlay shows at one moment. */
export interface OverlayState {
  readonly is_game_running: boolean;
  readonly game_time_seconds: number | null;
  readonly dragon: DragonTimer | null;
  readonly objectives: readonly ObjectiveTimer[];
  readonly buffs: readonly BuffTimer[];
  readonly inhibitors: readonly InhibitorTimer[];
  readonly structures: readonly LaneStructures[];
  readonly players: readonly PlayerCard[];
  readonly numbers_window: NumbersWindow | null;
  readonly team_item_gold: TeamItemGold | null;
  readonly team_gold: TeamGold | null;
  readonly cooldowns: readonly CooldownTimer[];
  readonly jungle_paths: readonly JunglePath[];
  readonly camp_timers: readonly CampTimer[];
  readonly control_wards: readonly WardEstimate[];
  readonly minimap: MinimapLayout | null;
  readonly win_chance: WinChance | null;
  readonly fight: FightEstimate | null;
  readonly contests: readonly ObjectiveContest[];
  readonly you: YouPanel | null;
  readonly preferences: OverlayPreferences;
  readonly layout: OverlayLayout;
  readonly callouts: readonly Callout[];
}

const DRAGON_OBJECTIVES: ReadonlySet<string> = new Set(["dragon", "elder_dragon"]);
const DRAGON_STATUSES: ReadonlySet<string> = new Set(["not_spawned", "respawning", "alive"]);
const SIDES: ReadonlySet<string> = new Set(["ally", "enemy"]);
const EPIC_OBJECTIVES: ReadonlySet<string> = new Set(["baron", "rift_herald", "voidgrubs"]);
const OBJECTIVE_STATUSES: ReadonlySet<string> = new Set(["not_spawned", "respawning", "alive", "gone"]);
const BUFFS: ReadonlySet<string> = new Set(["baron", "elder"]);
const LANES: ReadonlySet<string> = new Set(["top", "mid", "bot"]);
const ROLE_CONFIDENCES: ReadonlySet<string> = new Set(["given", "likely", "guess", "unknown"]);
const CALLOUT_KINDS: ReadonlySet<string> = new Set([
  "numbers_window",
  "level_spike",
  "level_soon",
  "objective_soon",
  "item_spike",
  "item_soon",
  "cooldown_ready",
  "went_back",
  "missing",
  "inhibitor_open",
  "suggestion",
]);
const MARKED_SPELLS: ReadonlySet<string> = new Set(["flash", "summoner", "ultimate"]);

/** Return whether a value is a plain object, so that its fields can be read. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Return whether a value is a number or null. */
function isNumberOrNull(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

/** Return whether a value is a dragon timer as the engine sends it. */
export function isDragonTimer(value: unknown): value is DragonTimer {
  if (!isRecord(value)) {
    return false;
  }
  const objective = value["objective"];
  const status = value["status"];
  const soulType = value["soul_type"];
  const soulHolder = value["soul_holder"];
  return (
    typeof objective === "string" &&
    DRAGON_OBJECTIVES.has(objective) &&
    typeof status === "string" &&
    DRAGON_STATUSES.has(status) &&
    typeof value["spawns_at_game_time_seconds"] === "number" &&
    typeof value["ally_dragon_count"] === "number" &&
    typeof value["enemy_dragon_count"] === "number" &&
    (soulType === null || typeof soulType === "string") &&
    (soulHolder === null || (typeof soulHolder === "string" && SIDES.has(soulHolder)))
  );
}

/** Return whether a value is a string from a known set. */
function isOneOf(value: unknown, allowed: ReadonlySet<string>): value is string {
  return typeof value === "string" && allowed.has(value);
}

/** Return whether a value is an array whose every item passes a check. */
function isArrayOf<Item>(value: unknown, isItem: (item: unknown) => item is Item): value is readonly Item[] {
  return Array.isArray(value) && value.every((item: unknown) => isItem(item));
}

/** Return whether a value is an epic monster's timer as the engine sends it. */
export function isObjectiveTimer(value: unknown): value is ObjectiveTimer {
  return (
    isRecord(value) &&
    isOneOf(value["objective"], EPIC_OBJECTIVES) &&
    isOneOf(value["status"], OBJECTIVE_STATUSES) &&
    isNumberOrNull(value["spawns_at_game_time_seconds"]) &&
    typeof value["is_rule_verified"] === "boolean"
  );
}

/** Return whether a value is a buff's timer as the engine sends it. */
export function isBuffTimer(value: unknown): value is BuffTimer {
  return (
    isRecord(value) &&
    isOneOf(value["buff"], BUFFS) &&
    isOneOf(value["holder"], SIDES) &&
    typeof value["ends_at_game_time_seconds"] === "number"
  );
}

/** Return whether a value is an inhibitor's timer as the engine sends it. */
export function isInhibitorTimer(value: unknown): value is InhibitorTimer {
  return (
    isRecord(value) &&
    isOneOf(value["side"], SIDES) &&
    isOneOf(value["lane"], LANES) &&
    typeof value["respawns_at_game_time_seconds"] === "number"
  );
}

function isLaneStructures(value: unknown): value is LaneStructures {
  return (
    isRecord(value) &&
    isOneOf(value["side"], SIDES) &&
    isOneOf(value["lane"], LANES) &&
    typeof value["turrets_down"] === "number" &&
    typeof value["is_inhibitor_exposed"] === "boolean"
  );
}

const COMBAT_STAT_NAMES = [
  "health",
  "armor",
  "magic_resist",
  "attack_damage",
  "ability_power",
  "attack_speed",
  "move_speed",
] as const;
const COMBAT_STAT_SOURCES: ReadonlySet<string> = new Set(["exact", "estimate"]);

/** Return whether a value is a player's combat stats as the engine sends them. */
export function isCombatStats(value: unknown): value is CombatStats {
  return (
    isRecord(value) &&
    isOneOf(value["source"], COMBAT_STAT_SOURCES) &&
    COMBAT_STAT_NAMES.every((statName) => typeof value[statName] === "number")
  );
}

const RANKED_QUEUES: ReadonlySet<string> = new Set(["solo", "flex"]);

/** Return whether a value is a player's rank as the engine sends it. */
export function isRankedStanding(value: unknown): value is RankedStanding {
  return (
    isRecord(value) &&
    isOneOf(value["queue"], RANKED_QUEUES) &&
    typeof value["tier"] === "string" &&
    typeof value["division"] === "string" &&
    typeof value["league_points"] === "number" &&
    typeof value["wins"] === "number" &&
    typeof value["losses"] === "number"
  );
}

/** Return whether a value is a player's intel as the engine sends it. */
export function isPlayerIntel(value: unknown): value is PlayerIntel {
  return (
    isRecord(value) &&
    (value["ranked"] === null || isRankedStanding(value["ranked"])) &&
    typeof value["recent_game_count"] === "number" &&
    typeof value["recent_win_count"] === "number" &&
    typeof value["streak"] === "number" &&
    typeof value["champion_game_count"] === "number" &&
    typeof value["champion_win_count"] === "number" &&
    typeof value["usual_position"] === "string" &&
    typeof value["is_off_role"] === "boolean"
  );
}

/** Return whether a value is a player's gold as the engine sends it. */
export function isGoldEstimate(value: unknown): value is GoldEstimate {
  return (
    isRecord(value) &&
    isOneOf(value["source"], COMBAT_STAT_SOURCES) &&
    typeof value["total_gold"] === "number" &&
    typeof value["unspent_gold"] === "number" &&
    typeof value["band_gold"] === "number"
  );
}

/** Return whether a value is a player's experience as the engine sends it. */
export function isLevelEstimate(value: unknown): value is LevelEstimate {
  return (
    isRecord(value) &&
    typeof value["experience"] === "number" &&
    typeof value["band_experience"] === "number" &&
    isNumberOrNull(value["progress_to_next_level"]) &&
    isNumberOrNull(value["next_power_level"]) &&
    isNumberOrNull(value["power_level_at_game_time_seconds"]) &&
    isNumberOrNull(value["power_level_band_seconds"])
  );
}

/** Return whether a value is a player's last trip to base as the engine sends it. */
export function isBackEstimate(value: unknown): value is BackEstimate {
  return (
    isRecord(value) &&
    typeof value["shopped_at_game_time_seconds"] === "number" &&
    typeof value["returns_at_game_time_seconds"] === "number"
  );
}

/** Return whether a value is a player's next item as the engine sends it. */
export function isNextItemEstimate(value: unknown): value is NextItemEstimate {
  return (
    isRecord(value) &&
    typeof value["item_id"] === "number" &&
    typeof value["item_name"] === "string" &&
    typeof value["likelihood"] === "number" &&
    typeof value["remaining_gold"] === "number" &&
    isNumberOrNull(value["chance_to_afford"]) &&
    isNumberOrNull(value["affordable_at_game_time_seconds"])
  );
}

const CLUE_KINDS: ReadonlySet<string> = new Set(["fountain", "objective", "turret", "lane", "jungle"]);

/** Return whether a value is a clue to a player's place as the engine sends it. */
export function isPositionClue(value: unknown): value is PositionClue {
  return (
    isRecord(value) &&
    isOneOf(value["kind"], CLUE_KINDS) &&
    typeof value["game_time_seconds"] === "number" &&
    typeof value["place"] === "string" &&
    (value["point_name"] === null || typeof value["point_name"] === "string") &&
    typeof value["region"] === "string"
  );
}

/** Return whether a value is a region's chance as the engine sends it. */
export function isRegionChance(value: unknown): value is RegionChance {
  return (
    isRecord(value) &&
    typeof value["region"] === "string" &&
    typeof value["label"] === "string" &&
    typeof value["chance"] === "number" &&
    typeof value["x_position"] === "number" &&
    typeof value["y_position"] === "number"
  );
}

/** Return whether a value is a player's position as the engine sends it. */
export function isPositionEstimate(value: unknown): value is PositionEstimate {
  return (
    isRecord(value) &&
    isArrayOf(value["regions"], isRegionChance) &&
    typeof value["away_chance"] === "number" &&
    isNumberOrNull(value["unseen_seconds"]) &&
    typeof value["reach_top_seconds"] === "number" &&
    typeof value["reach_mid_seconds"] === "number" &&
    typeof value["reach_bot_seconds"] === "number"
  );
}

/** Return whether a value is a player's card as the engine sends it. */
export function isPlayerCard(value: unknown): value is PlayerCard {
  return (
    isRecord(value) &&
    typeof value["champion_name"] === "string" &&
    isOneOf(value["side"], SIDES) &&
    typeof value["is_you"] === "boolean" &&
    typeof value["position"] === "string" &&
    typeof value["role"] === "string" &&
    isOneOf(value["role_confidence"], ROLE_CONFIDENCES) &&
    typeof value["level"] === "number" &&
    typeof value["is_dead"] === "boolean" &&
    isNumberOrNull(value["respawns_at_game_time_seconds"]) &&
    isNumberOrNull(value["item_gold"]) &&
    isArrayOf(value["finished_item_names"], (name: unknown): name is string => typeof name === "string") &&
    (value["combat_stats"] === null || isCombatStats(value["combat_stats"])) &&
    (value["intel"] === null || isPlayerIntel(value["intel"])) &&
    (value["gold"] === null || isGoldEstimate(value["gold"])) &&
    (value["level_estimate"] === null || isLevelEstimate(value["level_estimate"])) &&
    (value["last_back"] === null || isBackEstimate(value["last_back"])) &&
    (value["next_item"] === null || isNextItemEstimate(value["next_item"])) &&
    (value["last_clue"] === null || isPositionClue(value["last_clue"])) &&
    (value["location"] === null || isPositionEstimate(value["location"]))
  );
}

/** Return whether a value is each team's item gold as the engine sends it. */
export function isTeamItemGold(value: unknown): value is TeamItemGold {
  return (
    isRecord(value) &&
    typeof value["ally_item_gold"] === "number" &&
    typeof value["enemy_item_gold"] === "number"
  );
}

/** Return whether a value is each team's gold as the engine sends it. */
export function isTeamGold(value: unknown): value is TeamGold {
  return (
    isRecord(value) &&
    typeof value["ally_total_gold"] === "number" &&
    typeof value["enemy_total_gold"] === "number" &&
    typeof value["lead_band_gold"] === "number"
  );
}

/** Return whether a value is a numbers window as the engine sends it. */
export function isNumbersWindow(value: unknown): value is NumbersWindow {
  return (
    isRecord(value) &&
    typeof value["ally_dead_count"] === "number" &&
    typeof value["enemy_dead_count"] === "number" &&
    typeof value["ends_at_game_time_seconds"] === "number"
  );
}

/** Return whether a value is a callout as the engine sends it. */
export function isCallout(value: unknown): value is Callout {
  return (
    isRecord(value) &&
    typeof value["callout_id"] === "string" &&
    isOneOf(value["kind"], CALLOUT_KINDS) &&
    typeof value["text"] === "string" &&
    typeof value["shown_until_game_time_seconds"] === "number"
  );
}

/** Return whether a value is a marked cooldown as the engine sends it. */
export function isCooldownTimer(value: unknown): value is CooldownTimer {
  return (
    isRecord(value) &&
    typeof value["cooldown_id"] === "string" &&
    typeof value["champion_name"] === "string" &&
    isOneOf(value["spell"], MARKED_SPELLS) &&
    typeof value["spell_name"] === "string" &&
    typeof value["label"] === "string" &&
    typeof value["marked_at_game_time_seconds"] === "number" &&
    typeof value["ready_at_game_time_seconds"] === "number"
  );
}

/** Return whether a value is a camp's timer as the engine sends it. */
export function isCampTimer(value: unknown): value is CampTimer {
  return (
    isRecord(value) &&
    typeof value["camp"] === "string" &&
    typeof value["label"] === "string" &&
    isOneOf(value["cleared_by"], SIDES) &&
    typeof value["respawns_at_game_time_seconds"] === "number" &&
    typeof value["x_position"] === "number" &&
    typeof value["y_position"] === "number"
  );
}

/** Return whether a value is a jungler's path as the engine sends it. */
export function isJunglePath(value: unknown): value is JunglePath {
  return (
    isRecord(value) &&
    typeof value["champion_name"] === "string" &&
    isOneOf(value["side"], SIDES) &&
    isArrayOf(value["recent_camps"], (camp: unknown): camp is string => typeof camp === "string") &&
    isNumberOrNull(value["last_cleared_at_game_time_seconds"]) &&
    (value["next_camp"] === null || typeof value["next_camp"] === "string") &&
    isNumberOrNull(value["next_camp_at_game_time_seconds"])
  );
}

/** Return whether a value is a control ward's estimate as the engine sends it. */
export function isWardEstimate(value: unknown): value is WardEstimate {
  return (
    isRecord(value) &&
    typeof value["champion_name"] === "string" &&
    isOneOf(value["side"], SIDES) &&
    typeof value["placed_at_game_time_seconds"] === "number" &&
    typeof value["region"] === "string" &&
    typeof value["label"] === "string" &&
    typeof value["chance"] === "number" &&
    typeof value["x_position"] === "number" &&
    typeof value["y_position"] === "number"
  );
}

/** Return whether a value is where League draws its minimap as the engine sends it. */
export function isMinimapLayout(value: unknown): value is MinimapLayout {
  return isRecord(value) && typeof value["scale"] === "number" && typeof value["is_flipped"] === "boolean";
}

/** Return whether a value is one reason of the win chance as the engine sends it. */
export function isWinReason(value: unknown): value is WinReason {
  return isRecord(value) && typeof value["label"] === "string" && typeof value["effect"] === "number";
}

/** Return whether a value is the win chance as the engine sends it. */
export function isWinChance(value: unknown): value is WinChance {
  return isRecord(value) && typeof value["ally_chance"] === "number" && isArrayOf(value["reasons"], isWinReason);
}

/** Return whether a value is an even fight's estimate as the engine sends it. */
export function isFightEstimate(value: unknown): value is FightEstimate {
  return (
    isRecord(value) &&
    typeof value["ally_chance"] === "number" &&
    typeof value["ally_fighters"] === "number" &&
    typeof value["enemy_fighters"] === "number" &&
    typeof value["ally_physical_share"] === "number" &&
    typeof value["enemy_physical_share"] === "number"
  );
}

const CONTESTED_OBJECTIVES: ReadonlySet<string> = new Set(["dragon", "elder_dragon", "baron"]);

/** Return whether a value is a monster's contest as the engine sends it. */
export function isObjectiveContest(value: unknown): value is ObjectiveContest {
  return (
    isRecord(value) &&
    isOneOf(value["objective"], CONTESTED_OBJECTIVES) &&
    typeof value["kill_seconds"] === "number" &&
    typeof value["ally_fighters"] === "number" &&
    typeof value["contest_chance"] === "number" &&
    (value["likeliest_contester"] === null || typeof value["likeliest_contester"] === "string") &&
    typeof value["likeliest_chance"] === "number"
  );
}

const DEFENSIVE_STATS: ReadonlySet<string> = new Set(["armor", "magic_resist", "health"]);

/** Return whether a value is one defensive stat's value as the engine sends it. */
export function isDefenseValue(value: unknown): value is DefenseValue {
  return (
    isRecord(value) &&
    isOneOf(value["stat"], DEFENSIVE_STATS) &&
    typeof value["effective_health_per_hundred_gold"] === "number"
  );
}

/** Return whether a value is the You panel as the engine sends it. */
export function isYouPanel(value: unknown): value is YouPanel {
  return (
    isRecord(value) &&
    isArrayOf(value["defenses"], isDefenseValue) &&
    isNumberOrNull(value["enemy_physical_share"]) &&
    typeof value["unspent_gold"] === "number" &&
    isNumberOrNull(value["holding_gold_seconds"]) &&
    isNumberOrNull(value["creep_score_per_minute"]) &&
    isNumberOrNull(value["usual_creep_score_per_minute"])
  );
}

/** Return whether a value is the player's preferences as the engine sends them. */
export function isOverlayPreferences(value: unknown): value is OverlayPreferences {
  return isRecord(value) && PREFERENCE_NAMES.every((name) => typeof value[name] === "boolean");
}

function isWidgetOffset(value: unknown): value is WidgetOffset {
  return (
    isRecord(value) &&
    typeof value["x_share"] === "number" &&
    typeof value["y_share"] === "number" &&
    Math.abs(value["x_share"]) <= 1 &&
    Math.abs(value["y_share"]) <= 1
  );
}

/** Return whether a value is a layout as the engine sends it. */
export function isOverlayLayout(value: unknown): value is OverlayLayout {
  if (!isRecord(value) || !isRecord(value["offsets"])) {
    return false;
  }
  const offsets = value["offsets"];
  const movable: ReadonlySet<string> = new Set(MOVABLE_WIDGETS);
  return Object.entries(offsets).every(([widget, offset]) => movable.has(widget) && isWidgetOffset(offset));
}

/** Return whether a value is an overlay state as the engine sends it. */
export function isOverlayState(value: unknown): value is OverlayState {
  if (!isRecord(value)) {
    return false;
  }
  const dragon = value["dragon"];
  return (
    typeof value["is_game_running"] === "boolean" &&
    isNumberOrNull(value["game_time_seconds"]) &&
    (dragon === null || isDragonTimer(dragon)) &&
    isArrayOf(value["objectives"], isObjectiveTimer) &&
    isArrayOf(value["buffs"], isBuffTimer) &&
    isArrayOf(value["inhibitors"], isInhibitorTimer) &&
    isArrayOf(value["structures"], isLaneStructures) &&
    isArrayOf(value["players"], isPlayerCard) &&
    (value["numbers_window"] === null || isNumbersWindow(value["numbers_window"])) &&
    (value["team_item_gold"] === null || isTeamItemGold(value["team_item_gold"])) &&
    (value["team_gold"] === null || isTeamGold(value["team_gold"])) &&
    isArrayOf(value["cooldowns"], isCooldownTimer) &&
    isArrayOf(value["jungle_paths"], isJunglePath) &&
    isArrayOf(value["camp_timers"], isCampTimer) &&
    isArrayOf(value["control_wards"], isWardEstimate) &&
    (value["minimap"] === null || isMinimapLayout(value["minimap"])) &&
    (value["win_chance"] === null || isWinChance(value["win_chance"])) &&
    (value["fight"] === null || isFightEstimate(value["fight"])) &&
    isArrayOf(value["contests"], isObjectiveContest) &&
    (value["you"] === null || isYouPanel(value["you"])) &&
    isOverlayPreferences(value["preferences"]) &&
    isOverlayLayout(value["layout"]) &&
    isArrayOf(value["callouts"], isCallout)
  );
}
