/**
 * What the engine sends the overlay: the TypeScript side of `src/leagueasymode/overlay_state.py`.
 *
 * `overlay/web/overlay_state.schema.json` is that contract's JSON Schema, which a Python test keeps
 * current; a change to it shows up in review beside this file, which must change with it.
 */
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
];
/** The widgets the player can move; the minimap layer stays over League's minimap. */
export const MOVABLE_WIDGETS = ["objective_strip", "callouts", "enemy_strip", "you_panel"];
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
    "level_soon",
    "objective_soon",
    "item_spike",
    "item_soon",
    "cooldown_ready",
    "went_back",
    "missing",
    "jungle_start",
    "inhibitor_open",
    "suggestion",
]);
const START_SIDES = new Set(["blue", "red"]);
const MAP_HALVES = new Set(["top", "bot"]);
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
function isLaneStructures(value) {
    return (isRecord(value) &&
        isOneOf(value["side"], SIDES) &&
        isOneOf(value["lane"], LANES) &&
        typeof value["turrets_down"] === "number" &&
        typeof value["is_inhibitor_exposed"] === "boolean");
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
        typeof value["is_off_role"] === "boolean" &&
        (value["jungle_start_side"] === null || isOneOf(value["jungle_start_side"], START_SIDES)) &&
        (value["jungle_start_half"] === null || isOneOf(value["jungle_start_half"], MAP_HALVES)) &&
        typeof value["jungle_start_count"] === "number" &&
        typeof value["jungle_start_games"] === "number");
}
/** Return whether a value is a player's gold as the engine sends it. */
export function isGoldEstimate(value) {
    return (isRecord(value) &&
        isOneOf(value["source"], COMBAT_STAT_SOURCES) &&
        typeof value["total_gold"] === "number" &&
        typeof value["unspent_gold"] === "number" &&
        typeof value["band_gold"] === "number");
}
/** Return whether a value is a player's experience as the engine sends it. */
export function isLevelEstimate(value) {
    return (isRecord(value) &&
        typeof value["experience"] === "number" &&
        typeof value["band_experience"] === "number" &&
        isNumberOrNull(value["progress_to_next_level"]) &&
        isNumberOrNull(value["next_power_level"]) &&
        isNumberOrNull(value["power_level_at_game_time_seconds"]) &&
        isNumberOrNull(value["power_level_band_seconds"]));
}
/** Return whether a value is a player's last trip to base as the engine sends it. */
export function isBackEstimate(value) {
    return (isRecord(value) &&
        typeof value["shopped_at_game_time_seconds"] === "number" &&
        typeof value["returns_at_game_time_seconds"] === "number");
}
/** Return whether a value is a player's next item as the engine sends it. */
export function isNextItemEstimate(value) {
    return (isRecord(value) &&
        typeof value["item_id"] === "number" &&
        typeof value["item_name"] === "string" &&
        typeof value["likelihood"] === "number" &&
        typeof value["remaining_gold"] === "number" &&
        isNumberOrNull(value["chance_to_afford"]) &&
        isNumberOrNull(value["affordable_at_game_time_seconds"]));
}
const CLUE_KINDS = new Set(["fountain", "objective", "turret", "lane", "jungle"]);
/** Return whether a value is a clue to a player's place as the engine sends it. */
export function isPositionClue(value) {
    return (isRecord(value) &&
        isOneOf(value["kind"], CLUE_KINDS) &&
        typeof value["game_time_seconds"] === "number" &&
        typeof value["place"] === "string" &&
        (value["point_name"] === null || typeof value["point_name"] === "string") &&
        typeof value["region"] === "string");
}
/** Return whether a value is a region's chance as the engine sends it. */
export function isRegionChance(value) {
    return (isRecord(value) &&
        typeof value["region"] === "string" &&
        typeof value["label"] === "string" &&
        typeof value["chance"] === "number" &&
        typeof value["x_position"] === "number" &&
        typeof value["y_position"] === "number");
}
/** Return whether a value is a player's position as the engine sends it. */
export function isPositionEstimate(value) {
    return (isRecord(value) &&
        isArrayOf(value["regions"], isRegionChance) &&
        typeof value["away_chance"] === "number" &&
        isNumberOrNull(value["unseen_seconds"]) &&
        typeof value["reach_top_seconds"] === "number" &&
        typeof value["reach_mid_seconds"] === "number" &&
        typeof value["reach_bot_seconds"] === "number");
}
/** Return whether a value is a player's card as the engine sends it. */
export function isPlayerCard(value) {
    return (isRecord(value) &&
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
        isArrayOf(value["finished_item_names"], (name) => typeof name === "string") &&
        (value["combat_stats"] === null || isCombatStats(value["combat_stats"])) &&
        (value["intel"] === null || isPlayerIntel(value["intel"])) &&
        (value["gold"] === null || isGoldEstimate(value["gold"])) &&
        (value["level_estimate"] === null || isLevelEstimate(value["level_estimate"])) &&
        (value["last_back"] === null || isBackEstimate(value["last_back"])) &&
        (value["next_item"] === null || isNextItemEstimate(value["next_item"])) &&
        (value["last_clue"] === null || isPositionClue(value["last_clue"])) &&
        (value["location"] === null || isPositionEstimate(value["location"])));
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
/** Return whether a value is a camp's timer as the engine sends it. */
export function isCampTimer(value) {
    return (isRecord(value) &&
        typeof value["camp"] === "string" &&
        typeof value["label"] === "string" &&
        isOneOf(value["cleared_by"], SIDES) &&
        typeof value["respawns_at_game_time_seconds"] === "number" &&
        typeof value["x_position"] === "number" &&
        typeof value["y_position"] === "number");
}
/** Return whether a value is a jungler's path as the engine sends it. */
export function isJunglePath(value) {
    return (isRecord(value) &&
        typeof value["champion_name"] === "string" &&
        isOneOf(value["side"], SIDES) &&
        isArrayOf(value["recent_camps"], (camp) => typeof camp === "string") &&
        isNumberOrNull(value["last_cleared_at_game_time_seconds"]) &&
        (value["next_camp"] === null || typeof value["next_camp"] === "string") &&
        isNumberOrNull(value["next_camp_at_game_time_seconds"]));
}
/** Return whether a value is a control ward's estimate as the engine sends it. */
export function isWardEstimate(value) {
    return (isRecord(value) &&
        typeof value["champion_name"] === "string" &&
        isOneOf(value["side"], SIDES) &&
        typeof value["placed_at_game_time_seconds"] === "number" &&
        typeof value["region"] === "string" &&
        typeof value["label"] === "string" &&
        typeof value["chance"] === "number" &&
        typeof value["x_position"] === "number" &&
        typeof value["y_position"] === "number");
}
/** Return whether a value is where League draws its minimap as the engine sends it. */
export function isMinimapLayout(value) {
    return isRecord(value) && typeof value["scale"] === "number" && typeof value["is_flipped"] === "boolean";
}
/** Return whether a value is one reason of the win chance as the engine sends it. */
export function isWinReason(value) {
    return isRecord(value) && typeof value["label"] === "string" && typeof value["effect"] === "number";
}
/** Return whether a value is the win chance as the engine sends it. */
export function isWinChance(value) {
    return isRecord(value) && typeof value["ally_chance"] === "number" && isArrayOf(value["reasons"], isWinReason);
}
/** Return whether a value is an even fight's estimate as the engine sends it. */
export function isFightEstimate(value) {
    return (isRecord(value) &&
        typeof value["ally_chance"] === "number" &&
        typeof value["ally_fighters"] === "number" &&
        typeof value["enemy_fighters"] === "number" &&
        typeof value["ally_physical_share"] === "number" &&
        typeof value["enemy_physical_share"] === "number");
}
const CONTESTED_OBJECTIVES = new Set(["dragon", "elder_dragon", "baron"]);
/** Return whether a value is a monster's contest as the engine sends it. */
export function isObjectiveContest(value) {
    return (isRecord(value) &&
        isOneOf(value["objective"], CONTESTED_OBJECTIVES) &&
        typeof value["kill_seconds"] === "number" &&
        typeof value["ally_fighters"] === "number" &&
        typeof value["contest_chance"] === "number" &&
        (value["likeliest_contester"] === null || typeof value["likeliest_contester"] === "string") &&
        typeof value["likeliest_chance"] === "number");
}
const DEFENSIVE_STATS = new Set(["armor", "magic_resist", "health"]);
/** Return whether a value is one defensive stat's value as the engine sends it. */
export function isDefenseValue(value) {
    return (isRecord(value) &&
        isOneOf(value["stat"], DEFENSIVE_STATS) &&
        typeof value["effective_health_per_hundred_gold"] === "number");
}
/** Return whether a value is the You panel as the engine sends it. */
export function isYouPanel(value) {
    return (isRecord(value) &&
        isArrayOf(value["defenses"], isDefenseValue) &&
        isNumberOrNull(value["enemy_physical_share"]) &&
        typeof value["unspent_gold"] === "number" &&
        isNumberOrNull(value["holding_gold_seconds"]) &&
        isNumberOrNull(value["creep_score_per_minute"]) &&
        isNumberOrNull(value["usual_creep_score_per_minute"]));
}
/** Return whether a value is the player's preferences as the engine sends them. */
export function isOverlayPreferences(value) {
    return isRecord(value) && PREFERENCE_NAMES.every((name) => typeof value[name] === "boolean");
}
function isWidgetOffset(value) {
    return (isRecord(value) &&
        typeof value["x_share"] === "number" &&
        typeof value["y_share"] === "number" &&
        Math.abs(value["x_share"]) <= 1 &&
        Math.abs(value["y_share"]) <= 1);
}
/** Return whether a value is a layout as the engine sends it. */
export function isOverlayLayout(value) {
    if (!isRecord(value) || !isRecord(value["offsets"])) {
        return false;
    }
    const offsets = value["offsets"];
    const movable = new Set(MOVABLE_WIDGETS);
    return Object.entries(offsets).every(([widget, offset]) => movable.has(widget) && isWidgetOffset(offset));
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
        isArrayOf(value["callouts"], isCallout));
}
