/**
 * What the engine tells the post-game window: the last game reconstructed, and the accuracy
 * history. Mirrors `leagueasymode.game_summary` (`overlay/web/game_summary.schema.json`) and the
 * accuracy history's lines (`leagueasymode.accuracy_history`).
 */
const SIDES = new Set(["ally", "enemy"]);
const RESULTS = new Set(["win", "loss"]);
function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
function isArrayOf(value, isItem) {
    return Array.isArray(value) && value.every(isItem);
}
function isString(value) {
    return typeof value === "string";
}
function isSummaryPoint(value) {
    return isRecord(value) && typeof value["minute"] === "number" && typeof value["value"] === "number";
}
function isSummaryMoment(value) {
    return (isRecord(value) &&
        typeof value["game_time_seconds"] === "number" &&
        typeof value["kind"] === "string" &&
        typeof value["side"] === "string" &&
        SIDES.has(value["side"]) &&
        typeof value["text"] === "string");
}
function isWinSwing(value) {
    return (isRecord(value) &&
        typeof value["minute"] === "number" &&
        typeof value["change"] === "number" &&
        isArrayOf(value["moments"], isString));
}
function isScoreLine(value) {
    return (isRecord(value) &&
        typeof value["estimator"] === "string" &&
        typeof value["measure"] === "string" &&
        typeof value["sample_count"] === "number" &&
        typeof value["value"] === "number");
}
function isSummaryScore(value) {
    return isScoreLine(value) && isRecord(value) && typeof value["text"] === "string";
}
/** Return whether a value is the last game's summary as the engine sends it. */
export function isGameSummary(value) {
    if (!isRecord(value)) {
        return false;
    }
    const result = value["result"];
    const championName = value["champion_name"];
    return (typeof value["recording_name"] === "string" &&
        (result === null || (typeof result === "string" && RESULTS.has(result))) &&
        (championName === null || typeof championName === "string") &&
        typeof value["duration_seconds"] === "number" &&
        isArrayOf(value["win_chance"], isSummaryPoint) &&
        isArrayOf(value["gold_lead_estimated"], isSummaryPoint) &&
        isArrayOf(value["gold_lead_true"], isSummaryPoint) &&
        isArrayOf(value["moments"], isSummaryMoment) &&
        isArrayOf(value["swings"], isWinSwing) &&
        isArrayOf(value["scores"], isSummaryScore));
}
function isGameAccuracy(value) {
    return isRecord(value) && typeof value["recording_name"] === "string" && isArrayOf(value["scores"], isScoreLine);
}
/** Return the games of the accuracy history as the engine sends them; none when unreadable. */
export function accuracyGamesOf(value) {
    return isRecord(value) && isArrayOf(value["games"], isGameAccuracy) ? value["games"] : [];
}
