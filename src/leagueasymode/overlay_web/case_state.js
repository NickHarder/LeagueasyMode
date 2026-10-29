/**
 * What the engine tells the post-game window about the last game's case: mirrors
 * `leagueasymode.roast.case_view` (`overlay/web/roast_case.schema.json`), and the query `/case`
 * takes.
 */
export const DEFAULT_CHOICE = { target: "team", spice: 2, prove: false, take: 0 };
const SIDES = new Set(["ally", "enemy"]);
const SOURCE_KINDS = new Set(["game", "timeline", "live", "computation"]);
function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
function isArrayOf(value, isItem) {
    return Array.isArray(value) && value.every(isItem);
}
function isTextOrNull(value) {
    return value === null || typeof value === "string";
}
function isCasePlayer(value) {
    return (isRecord(value) &&
        typeof value["participant_id"] === "number" &&
        typeof value["champion"] === "string" &&
        typeof value["position"] === "string" &&
        typeof value["side"] === "string" &&
        SIDES.has(value["side"]) &&
        typeof value["is_defendant"] === "boolean" &&
        typeof value["is_friend"] === "boolean");
}
function isViewPart(value) {
    return isRecord(value) && typeof value["text"] === "string" && isTextOrNull(value["letter"]);
}
function isViewLine(value) {
    return isRecord(value) && isArrayOf(value["parts"], isViewPart);
}
function isViewLane(value) {
    return (isRecord(value) &&
        typeof value["position"] === "string" &&
        typeof value["ally_champion"] === "string" &&
        typeof value["enemy_champion"] === "string" &&
        typeof value["outcome"] === "string" &&
        isTextOrNull(value["gold_difference"]) &&
        isTextOrNull(value["cs_difference"]) &&
        isTextOrNull(value["letter"]));
}
function isViewExhibit(value) {
    return (isRecord(value) &&
        typeof value["letter"] === "string" &&
        typeof value["label"] === "string" &&
        typeof value["display"] === "string" &&
        typeof value["unit"] === "string" &&
        typeof value["source"] === "string" &&
        typeof value["source_kind"] === "string" &&
        SOURCE_KINDS.has(value["source_kind"]) &&
        typeof value["supporting"] === "boolean");
}
/** Return whether a value is a case as `/case` sends it. */
export function isCaseView(value) {
    if (!isRecord(value)) {
        return false;
    }
    const acquitted = value["acquitted"];
    return (typeof value["game_id"] === "number" &&
        isArrayOf(value["players"], isCasePlayer) &&
        typeof value["target"] === "string" &&
        typeof value["spice"] === "number" &&
        typeof value["spice_name"] === "string" &&
        typeof value["prove"] === "boolean" &&
        typeof value["take"] === "number" &&
        typeof value["verdict_title"] === "string" &&
        typeof value["verdict_summary"] === "string" &&
        (acquitted === null || typeof acquitted === "boolean") &&
        isArrayOf(value["board"], isViewLane) &&
        isArrayOf(value["lines"], isViewLine) &&
        typeof value["closing_line"] === "string" &&
        typeof value["closing_line_limit"] === "number" &&
        isTextOrNull(value["risk_warning"]) &&
        isArrayOf(value["exhibits"], isViewExhibit));
}
/** Return the path that asks `/case` for a choice. */
export function casePath(choice) {
    const query = new URLSearchParams({
        target: choice.target,
        spice: String(choice.spice),
        prove: choice.prove ? "1" : "0",
        take: String(choice.take),
    });
    return `/case?${query.toString()}`;
}
