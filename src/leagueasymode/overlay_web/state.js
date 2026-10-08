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
        isArrayOf(value["inhibitors"], isInhibitorTimer));
}
