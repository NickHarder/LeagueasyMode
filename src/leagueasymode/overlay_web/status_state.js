/**
 * What the engine sees, part by part, and the report a test sends back. Mirrors
 * `leagueasymode.engine_status` (`overlay/web/engine_status.schema.json`).
 */
export const STATE_NAMES = {
    ok: "OK",
    waiting: "Waiting",
    problem: "Problem",
    off: "Off",
};
function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
function isArrayOf(value, isItem) {
    return Array.isArray(value) && value.every(isItem);
}
function isString(value) {
    return typeof value === "string";
}
function isPartState(value) {
    return typeof value === "string" && Object.hasOwn(STATE_NAMES, value);
}
function isStatusPart(value) {
    return (isRecord(value) &&
        typeof value["key"] === "string" &&
        typeof value["title"] === "string" &&
        isPartState(value["state"]) &&
        typeof value["detail"] === "string" &&
        (value["updated_at"] === null || typeof value["updated_at"] === "string"));
}
function isSeenEvent(value) {
    return (isRecord(value) &&
        typeof value["name"] === "string" &&
        typeof value["count"] === "number" &&
        typeof value["is_read"] === "boolean");
}
/** Return whether a value is the engine's status as it sends it. */
export function isEngineStatus(value) {
    return (isRecord(value) &&
        typeof value["version"] === "string" &&
        typeof value["platform"] === "string" &&
        typeof value["python_version"] === "string" &&
        typeof value["started_at"] === "string" &&
        typeof value["reported_at"] === "string" &&
        isArrayOf(value["parts"], isStatusPart) &&
        isArrayOf(value["events"], isSeenEvent) &&
        isArrayOf(value["unreadable_fields"], isString));
}
/** Return a time as "21:30:00 UTC", from the engine's ISO 8601 text. */
export function utcTimeText(isoText) {
    const time = new Date(isoText);
    return Number.isNaN(time.getTime()) ? isoText : `${time.toISOString().slice(11, 19)} UTC`;
}
/** Return the event's line: its name, how often it came, and whether no estimator reads it. */
export function eventText(event) {
    return `${event.name} ×${String(event.count)}${event.is_read ? "" : " (no estimator reads it)"}`;
}
/** Return the report as text to paste into a message. Like the engine's status, it names no player. */
export function statusReport(status) {
    const lines = [
        `LeagueasyMode ${status.version} · ${status.platform} · Python ${status.python_version}`,
        `Started ${utcTimeText(status.started_at)} · reported ${utcTimeText(status.reported_at)}`,
        "",
        ...status.parts.map((part) => `[${STATE_NAMES[part.state]}] ${part.title}: ${part.detail}`),
        "",
        `Feed events: ${status.events.length > 0 ? status.events.map(eventText).join(", ") : "none yet"}`,
        `Fields not read: ${status.unreadable_fields.length > 0 ? status.unreadable_fields.join("; ") : "none"}`,
    ];
    return lines.join("\n");
}
