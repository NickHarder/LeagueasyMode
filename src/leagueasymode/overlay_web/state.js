/**
 * What the engine sends the overlay: the TypeScript side of `src/leagueasymode/overlay_state.py`.
 *
 * `overlay/web/overlay_state.schema.json` is that contract's JSON Schema, which a Python test keeps
 * current; a change to it shows up in review beside this file, which must change with it.
 */
const DRAGON_OBJECTIVES = new Set(["dragon", "elder_dragon"]);
const DRAGON_STATUSES = new Set(["not_spawned", "respawning", "alive"]);
const SIDES = new Set(["ally", "enemy"]);
const EPIC_OBJECTIVES = new Set(["baron", "rift_herald", "voidgrubs"]);
const OBJECTIVE_STATUSES = new Set(["not_spawned", "respawning", "alive", "gone"]);
const BUFFS = new Set(["baron", "elder"]);
const LANES = new Set(["top", "mid", "bot"]);
const ROLE_CONFIDENCES = new Set(["given", "likely", "guess", "unknown"]);
const CALLOUT_KINDS = new Set([
    "numbers_window",
    "level_spike",
    "objective_soon",
    "item_spike",
    "cooldown_ready",
    "suggestion",
]);
const MARKED_SPELLS = new Set(["flash", "summoner", "ultimate"]);
/** Return whether a value is a plain object, so that its fields can be read. */
function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
/** Return whether a value is a number or null. */
function isNumberOrNull(value) {
    return value === null || typeof value === "number";
}
/** Return whether a value is a dragon timer as the engine sends it. */
export function isDragonTimer(value) {
    if (!isRecord(value)) {
        return false;
    }
    const objective = value["objective"];
    const status = value["status"];
    const soulType = value["soul_type"];
    const soulHolder = value["soul_holder"];
    return (typeof objective === "string" &&
        DRAGON_OBJECTIVES.has(objective) &&
        typeof status === "string" &&
        DRAGON_STATUSES.has(status) &&
        typeof value["spawns_at_game_time_seconds"] === "number" &&
        typeof value["ally_dragon_count"] === "number" &&
        typeof value["enemy_dragon_count"] === "number" &&
        (soulType === null || typeof soulType === "string") &&
        (soulHolder === null || (typeof soulHolder === "string" && SIDES.has(soulHolder))));
}
/** Return whether a value is a string from a known set. */
function isOneOf(value, allowed) {
    return typeof value === "string" && allowed.has(value);
}
/** Return whether a value is an array whose every item passes a check. */
function isArrayOf(value, isItem) {
    return Array.isArray(value) && value.every((item) => isItem(item));
}
/** Return whether a value is an epic monster's timer as the engine sends it. */
export function isObjectiveTimer(value) {
    return (isRecord(value) &&
        isOneOf(value["objective"], EPIC_OBJECTIVES) &&
        isOneOf(value["status"], OBJECTIVE_STATUSES) &&
        isNumberOrNull(value["spawns_at_game_time_seconds"]) &&
        typeof value["is_rule_verified"] === "boolean");
}
/** Return whether a value is a buff's timer as the engine sends it. */
export function isBuffTimer(value) {
    return (isRecord(value) &&
        isOneOf(value["buff"], BUFFS) &&
        isOneOf(value["holder"], SIDES) &&
        typeof value["ends_at_game_time_seconds"] === "number");
}
/** Return whether a value is an inhibitor's timer as the engine sends it. */
export function isInhibitorTimer(value) {
    return (isRecord(value) &&
        isOneOf(value["side"], SIDES) &&
        isOneOf(value["lane"], LANES) &&
        typeof value["respawns_at_game_time_seconds"] === "number");
}
const COMBAT_STAT_NAMES = [
    "health",
    "armor",
    "magic_resist",
    "attack_damage",
    "ability_power",
    "attack_speed",
    "move_speed",
];
const COMBAT_STAT_SOURCES = new Set(["exact", "estimate"]);
/** Return whether a value is a player's combat stats as the engine sends them. */
export function isCombatStats(value) {
    return (isRecord(value) &&
        isOneOf(value["source"], COMBAT_STAT_SOURCES) &&
        COMBAT_STAT_NAMES.every((statName) => typeof value[statName] === "number"));
}
const RANKED_QUEUES = new Set(["solo", "flex"]);
/** Return whether a value is a player's rank as the engine sends it. */
export function isRankedStanding(value) {
    return (isRecord(value) &&
        isOneOf(value["queue"], RANKED_QUEUES) &&
        typeof value["tier"] === "string" &&
        typeof value["division"] === "string" &&
        typeof value["league_points"] === "number" &&
        typeof value["wins"] === "number" &&
        typeof value["losses"] === "number");
}
/** Return whether a value is a player's intel as the engine sends it. */
export function isPlayerIntel(value) {
    return (isRecord(value) &&
        (value["ranked"] === null || isRankedStanding(value["ranked"])) &&
        typeof value["recent_game_count"] === "number" &&
        typeof value["recent_win_count"] === "number" &&
        typeof value["streak"] === "number" &&
        typeof value["champion_game_count"] === "number" &&
        typeof value["champion_win_count"] === "number" &&
        typeof value["usual_position"] === "string" &&
        typeof value["is_off_role"] === "boolean");
}
/** Return whether a value is a player's gold as the engine sends it. */
export function isGoldEstimate(value) {
    return (isRecord(value) &&
        isOneOf(value["source"], COMBAT_STAT_SOURCES) &&
        typeof value["total_gold"] === "number" &&
        typeof value["unspent_gold"] === "number" &&
        typeof value["band_gold"] === "number");
}
/** Return whether a value is a player's card as the engine sends it. */
export function isPlayerCard(value) {
    return (isRecord(value) &&
        typeof value["champion_name"] === "string" &&
        isOneOf(value["side"], SIDES) &&
        typeof value["position"] === "string" &&
        typeof value["role"] === "string" &&
        isOneOf(value["role_confidence"], ROLE_CONFIDENCES) &&
        typeof value["level"] === "number" &&
        typeof value["is_dead"] === "boolean" &&
        isNumberOrNull(value["respawns_at_game_time_seconds"]) &&
        isNumberOrNull(value["item_gold"]) &&
        isArrayOf(value["finished_item_names"], (name) => typeof name === "string") &&
        (value["combat_stats"] === null || isCombatStats(value["combat_stats"])) &&
        (value["intel"] === null || isPlayerIntel(value["intel"])) &&
        (value["gold"] === null || isGoldEstimate(value["gold"])));
}
/** Return whether a value is each team's item gold as the engine sends it. */
export function isTeamItemGold(value) {
    return (isRecord(value) &&
        typeof value["ally_item_gold"] === "number" &&
        typeof value["enemy_item_gold"] === "number");
}
/** Return whether a value is each team's gold as the engine sends it. */
export function isTeamGold(value) {
    return (isRecord(value) &&
        typeof value["ally_total_gold"] === "number" &&
        typeof value["enemy_total_gold"] === "number" &&
        typeof value["lead_band_gold"] === "number");
}
/** Return whether a value is a numbers window as the engine sends it. */
export function isNumbersWindow(value) {
    return (isRecord(value) &&
        typeof value["ally_dead_count"] === "number" &&
        typeof value["enemy_dead_count"] === "number" &&
        typeof value["ends_at_game_time_seconds"] === "number");
}
/** Return whether a value is a callout as the engine sends it. */
export function isCallout(value) {
    return (isRecord(value) &&
        typeof value["callout_id"] === "string" &&
        isOneOf(value["kind"], CALLOUT_KINDS) &&
        typeof value["text"] === "string" &&
        typeof value["shown_until_game_time_seconds"] === "number");
}
/** Return whether a value is a marked cooldown as the engine sends it. */
export function isCooldownTimer(value) {
    return (isRecord(value) &&
        typeof value["cooldown_id"] === "string" &&
        typeof value["champion_name"] === "string" &&
        isOneOf(value["spell"], MARKED_SPELLS) &&
        typeof value["spell_name"] === "string" &&
        typeof value["label"] === "string" &&
        typeof value["marked_at_game_time_seconds"] === "number" &&
        typeof value["ready_at_game_time_seconds"] === "number");
}
/** Return whether a value is an overlay state as the engine sends it. */
export function isOverlayState(value) {
    if (!isRecord(value)) {
        return false;
    }
    const dragon = value["dragon"];
    return (typeof value["is_game_running"] === "boolean" &&
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
        isArrayOf(value["callouts"], isCallout));
}
