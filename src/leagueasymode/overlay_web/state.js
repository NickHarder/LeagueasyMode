/**
 * What the engine sends the overlay: the TypeScript side of `src/leagueasymode/overlay_state.py`.
 *
 * `overlay/web/overlay_state.schema.json` is that contract's JSON Schema, which a Python test keeps
 * current; a change to it shows up in review beside this file, which must change with it.
 */
const DRAGON_OBJECTIVES = new Set(["dragon", "elder_dragon"]);
const DRAGON_STATUSES = new Set(["not_spawned", "respawning", "alive"]);
const SIDES = new Set(["ally", "enemy"]);
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
/** Return whether a value is an overlay state as the engine sends it. */
export function isOverlayState(value) {
    if (!isRecord(value)) {
        return false;
    }
    const dragon = value["dragon"];
    return (typeof value["is_game_running"] === "boolean" &&
        isNumberOrNull(value["game_time_seconds"]) &&
        (dragon === null || isDragonTimer(dragon)));
}
