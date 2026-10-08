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

/** One player as the scoreboard shows them: side, role, level, and when they are back. */
export interface PlayerCard {
  readonly champion_name: string;
  readonly side: Side;
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
  | "objective_soon"
  | "item_spike"
  | "cooldown_ready"
  | "suggestion";

/** A short notice shown for a few seconds when something happens; never an instruction. */
export interface Callout {
  readonly callout_id: string;
  readonly kind: CalloutKind;
  readonly text: string;
  readonly shown_until_game_time_seconds: number;
}

/** Everything the overlay shows at one moment. */
export interface OverlayState {
  readonly is_game_running: boolean;
  readonly game_time_seconds: number | null;
  readonly dragon: DragonTimer | null;
  readonly objectives: readonly ObjectiveTimer[];
  readonly buffs: readonly BuffTimer[];
  readonly inhibitors: readonly InhibitorTimer[];
  readonly players: readonly PlayerCard[];
  readonly numbers_window: NumbersWindow | null;
  readonly team_item_gold: TeamItemGold | null;
  readonly team_gold: TeamGold | null;
  readonly cooldowns: readonly CooldownTimer[];
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
  "objective_soon",
  "item_spike",
  "cooldown_ready",
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

/** Return whether a value is a player's card as the engine sends it. */
export function isPlayerCard(value: unknown): value is PlayerCard {
  return (
    isRecord(value) &&
    typeof value["champion_name"] === "string" &&
    isOneOf(value["side"], SIDES) &&
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
    (value["gold"] === null || isGoldEstimate(value["gold"]))
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
    isArrayOf(value["players"], isPlayerCard) &&
    (value["numbers_window"] === null || isNumbersWindow(value["numbers_window"])) &&
    (value["team_item_gold"] === null || isTeamItemGold(value["team_item_gold"])) &&
    (value["team_gold"] === null || isTeamGold(value["team_gold"])) &&
    isArrayOf(value["cooldowns"], isCooldownTimer) &&
    isArrayOf(value["callouts"], isCallout)
  );
}
