/**
 * The overlay's widgets: listen to the engine's stream of states and draw them.
 *
 * The engine sends a state about twice a second. Between two, the countdown is moved on from the
 * time the last one arrived, so it ticks smoothly; it is never moved on by more than a couple of
 * seconds, so a paused or stalled game does not run its timers down.
 */

import {
  type BackEstimate,
  type BuffTimer,
  type Callout,
  type CombatStats,
  type CooldownTimer,
  type DragonTimer,
  type GoldEstimate,
  type InhibitorTimer,
  type LevelEstimate,
  type NextItemEstimate,
  type NumbersWindow,
  type ObjectiveTimer,
  type OverlayState,
  type PlayerCard,
  type PlayerIntel,
  type PositionClue,
  type PositionEstimate,
  type RankedStanding,
  isOverlayState,
} from "./state.js";

const EVENTS_PATH = "/events";
const RENDER_INTERVAL_MILLISECONDS = 250;
const LONGEST_EXTRAPOLATION_SECONDS = 2;
const MILLISECONDS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
const SOUL_COLORS: Readonly<Record<string, string>> = {
  Infernal: "#ff6b3d",
  Ocean: "#3fb6e8",
  Mountain: "#c49a5a",
  Cloud: "#b9d3e6",
  Hextech: "#4fd6c8",
  Chemtech: "#9bd13f",
};
const NEUTRAL_DRAGON_COLOR = "#d8b65a";
// An epic monster shows once it is this close to spawning, or up.
const UPCOMING_OBJECTIVE_SECONDS = 90;
const OBJECTIVE_NAMES: Readonly<Record<ObjectiveTimer["objective"], string>> = {
  baron: "Baron",
  rift_herald: "Herald",
  voidgrubs: "Voidgrubs",
};
const BUFF_NAMES: Readonly<Record<BuffTimer["buff"], string>> = {
  baron: "Baron buff",
  elder: "Elder buff",
};
const LANE_NAMES: Readonly<Record<InhibitorTimer["lane"], string>> = {
  top: "top",
  mid: "mid",
  bot: "bot",
};
const ONE_THOUSAND = 1000;
// A next item less likely than this is shown as a guess, with "?".
const LIKELY_NEXT_ITEM = 0.5;
// From this chance an enemy is taken to be able to afford their next item.
const LIKELY_TO_AFFORD = 0.75;
const PERCENT = 100;
// An enemy's likely place is shown once they have been unseen this long.
const LOCATION_SHOWN_AFTER_SECONDS = 10;
// An enemy's latest clue to their place is shown for this long after it.
const CLUE_SHOWN_SECONDS = 120;
// An enemy's last trip to base is shown for this long after they shopped.
const BACK_SHOWN_SECONDS = 90;
// An enemy's next power level (6, 11, 16) is shown once it is estimated this close.
const POWER_LEVEL_SHOWN_SECONDS = 90;
// A band narrower than this rounds to nothing at one decimal of a thousand, so it is left out.
const SMALLEST_BAND_SHOWN_GOLD = 50;
const ROLE_ORDER: readonly string[] = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"];
const ROLE_SHORT_NAMES: Readonly<Record<string, string>> = {
  TOP: "TOP",
  JUNGLE: "JGL",
  MIDDLE: "MID",
  BOTTOM: "BOT",
  UTILITY: "SUP",
};
// A timer whose rule is not yet confirmed for this season is shown with this mark.
const PROVISIONAL_MARK = "~";

/** One small pill of the objective strip: its words, its time, and how it is styled. */
interface Pill {
  readonly label: string;
  readonly timeText: string;
  readonly kind: "numbers" | "objective" | "buff" | "inhibitor";
  readonly side: "ally" | "enemy" | "neutral";
  readonly isUp: boolean;
}

/** A state from the engine, and when it arrived on this page's clock. */
interface ReceivedState {
  readonly state: OverlayState;
  readonly receivedAtMilliseconds: number;
}

let latestReceivedState: ReceivedState | null = null;

/** Return the game's clock now, moved on from the last state by at most a couple of seconds. */
function currentGameTimeSeconds(received: ReceivedState, nowMilliseconds: number): number | null {
  const reportedGameTimeSeconds = received.state.game_time_seconds;
  if (reportedGameTimeSeconds === null) {
    return null;
  }
  const elapsedSeconds = (nowMilliseconds - received.receivedAtMilliseconds) / MILLISECONDS_PER_SECOND;
  return reportedGameTimeSeconds + Math.min(Math.max(elapsedSeconds, 0), LONGEST_EXTRAPOLATION_SECONDS);
}

/** Return a duration as minutes and seconds, rounded up: 61.2 seconds is "1:02". */
export function formatCountdown(remainingSeconds: number): string {
  const wholeSeconds = Math.max(0, Math.ceil(remainingSeconds));
  const minutes = Math.floor(wholeSeconds / SECONDS_PER_MINUTE);
  const seconds = wholeSeconds % SECONDS_PER_MINUTE;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/** Return the small line under the timer: the dragons each side has, and the soul. */
function dragonDetail(dragon: DragonTimer): string {
  const countText = `${dragon.ally_dragon_count}–${dragon.enemy_dragon_count}`;
  if (dragon.soul_holder !== null) {
    const holderText = dragon.soul_holder === "ally" ? "Your" : "Enemy";
    const soulText = dragon.soul_type === null ? "soul" : `${dragon.soul_type} soul`;
    return `${countText} · ${holderText} ${soulText}`;
  }
  if (dragon.soul_type !== null) {
    return `${countText} · ${dragon.soul_type} rift`;
  }
  return countText;
}

/** Return an element of the page by its id, failing loudly if the page lacks it. */
function requireElement(elementId: string): HTMLElement {
  const element = document.getElementById(elementId);
  if (element === null) {
    throw new Error(`the overlay page has no #${elementId}`);
  }
  return element;
}

/** Draw the dragon widget for the latest state, or hide it when no game runs. */
function renderDragonWidget(nowMilliseconds: number): void {
  const widget = requireElement("dragon-widget");
  const received = latestReceivedState;
  const dragon = received?.state.dragon ?? null;
  const gameTimeSeconds = received === null ? null : currentGameTimeSeconds(received, nowMilliseconds);
  if (received === null || !received.state.is_game_running || dragon === null || gameTimeSeconds === null) {
    widget.hidden = true;
    return;
  }
  const remainingSeconds = dragon.spawns_at_game_time_seconds - gameTimeSeconds;
  const isUp = remainingSeconds <= 0;
  widget.hidden = false;
  widget.dataset["state"] = isUp ? "alive" : "waiting";
  requireElement("dragon-label").textContent = dragon.objective === "elder_dragon" ? "Elder" : "Dragon";
  requireElement("dragon-time").textContent = isUp ? "up" : formatCountdown(remainingSeconds);
  requireElement("dragon-detail").textContent = dragonDetail(dragon);
  requireElement("dragon-icon").style.backgroundColor =
    (dragon.soul_type !== null ? SOUL_COLORS[dragon.soul_type] : undefined) ?? NEUTRAL_DRAGON_COLOR;
}

/** Return the pill for an epic monster, or null when it is gone or not yet close. */
export function objectivePill(timer: ObjectiveTimer, gameTimeSeconds: number): Pill | null {
  const spawnsAtSeconds = timer.spawns_at_game_time_seconds;
  if (timer.status === "gone" || spawnsAtSeconds === null) {
    return null;
  }
  const remainingSeconds = spawnsAtSeconds - gameTimeSeconds;
  if (remainingSeconds > UPCOMING_OBJECTIVE_SECONDS) {
    return null;
  }
  const isUp = remainingSeconds <= 0;
  const provisionalMark = timer.is_rule_verified ? "" : PROVISIONAL_MARK;
  return {
    label: OBJECTIVE_NAMES[timer.objective],
    timeText: isUp ? "up" : `${provisionalMark}${formatCountdown(remainingSeconds)}`,
    kind: "objective",
    side: "neutral",
    isUp,
  };
}

/** Return the pill for a running buff, or null once it has run out. */
export function buffPill(timer: BuffTimer, gameTimeSeconds: number): Pill | null {
  const remainingSeconds = timer.ends_at_game_time_seconds - gameTimeSeconds;
  if (remainingSeconds <= 0) {
    return null;
  }
  const holderText = timer.holder === "ally" ? "Your" : "Enemy";
  return {
    label: `${holderText} ${BUFF_NAMES[timer.buff].toLowerCase()}`,
    timeText: formatCountdown(remainingSeconds),
    kind: "buff",
    side: timer.holder,
    isUp: false,
  };
}

/** Return the pill for a destroyed inhibitor, or null once it is back. */
export function inhibitorPill(timer: InhibitorTimer, gameTimeSeconds: number): Pill | null {
  const remainingSeconds = timer.respawns_at_game_time_seconds - gameTimeSeconds;
  if (remainingSeconds <= 0) {
    return null;
  }
  const sideText = timer.side === "ally" ? "Your" : "Enemy";
  return {
    label: `${sideText} ${LANE_NAMES[timer.lane]} inhib`,
    timeText: formatCountdown(remainingSeconds),
    kind: "inhibitor",
    side: timer.side,
    isUp: false,
  };
}

/** Return the pill for a numbers window, or null once it has closed. */
export function numbersPill(window: NumbersWindow, gameTimeSeconds: number): Pill | null {
  const remainingSeconds = window.ends_at_game_time_seconds - gameTimeSeconds;
  if (remainingSeconds <= 0) {
    return null;
  }
  const enemyText = window.enemy_dead_count === 1 ? "enemy" : "enemies";
  return {
    label: `${window.enemy_dead_count} ${enemyText} down (${window.ally_dead_count} of yours)`,
    timeText: formatCountdown(remainingSeconds),
    kind: "numbers",
    side: "ally",
    isUp: false,
  };
}

/** Return every pill to show beside the dragon, in a steady order. */
function stripPills(state: OverlayState, gameTimeSeconds: number): Pill[] {
  const candidatePills = [
    state.numbers_window === null ? null : numbersPill(state.numbers_window, gameTimeSeconds),
    ...state.objectives.map((timer) => objectivePill(timer, gameTimeSeconds)),
    ...state.buffs.map((timer) => buffPill(timer, gameTimeSeconds)),
    ...state.inhibitors.map((timer) => inhibitorPill(timer, gameTimeSeconds)),
  ];
  return candidatePills.filter((pill): pill is Pill => pill !== null);
}

/** Return the element that draws one pill. */
function pillElement(pill: Pill): HTMLElement {
  const element = document.createElement("span");
  element.className = "pill";
  element.dataset["kind"] = pill.kind;
  element.dataset["side"] = pill.side;
  element.dataset["state"] = pill.isUp ? "alive" : "waiting";
  const labelElement = document.createElement("span");
  labelElement.className = "pill-label";
  labelElement.textContent = pill.label;
  const timeElement = document.createElement("span");
  timeElement.className = "pill-time";
  timeElement.textContent = pill.timeText;
  element.append(labelElement, timeElement);
  return element;
}

/** Draw the pills beside the dragon: other monsters, buffs and inhibitors. */
function renderObjectivePills(nowMilliseconds: number): void {
  const pillRow = requireElement("objective-pills");
  const received = latestReceivedState;
  const gameTimeSeconds = received === null ? null : currentGameTimeSeconds(received, nowMilliseconds);
  if (received === null || !received.state.is_game_running || gameTimeSeconds === null) {
    pillRow.replaceChildren();
    return;
  }
  pillRow.replaceChildren(...stripPills(received.state, gameTimeSeconds).map(pillElement));
}

/** Return gold in thousands with one decimal: 3400 is "3.4k". */
export function formatGold(gold: number): string {
  return formatThousands(gold);
}

/** Return a number in thousands with one decimal: "3.4k". */
export function formatThousands(amount: number): string {
  return `${(amount / ONE_THOUSAND).toFixed(1)}k`;
}

/** Return a team's item-gold lead with its sign: "+1.2k", "−0.8k", or "even". */
export function formatGoldLead(leadGold: number): string {
  const roundedLead = Math.round(leadGold / 100) * 100;
  if (roundedLead === 0) {
    return "even";
  }
  return roundedLead > 0 ? `+${formatGold(roundedLead)}` : `\u2212${formatGold(-roundedLead)}`;
}

/** Return a band of gold to add after an amount: " ±0.3k", or nothing when it is too narrow. */
export function formatBand(bandGold: number): string {
  return bandGold >= SMALLEST_BAND_SHOWN_GOLD ? ` \u00b1${formatThousands(bandGold)}` : "";
}

/** Return what an enemy holds unspent, with its band: "1.4k ±0.3k unspent". */
export function formatUnspentGold(gold: GoldEstimate): string {
  return `${formatThousands(gold.unspent_gold)}${formatBand(gold.band_gold)} unspent`;
}

/**
 * Return when an enemy reaches their next power level, "6 in ~0:35", or null when that is not
 * known or more than 90 seconds away.
 */
export function formatPowerLevelSoon(estimate: LevelEstimate, gameTimeSeconds: number): string | null {
  const reachesAtSeconds = estimate.power_level_at_game_time_seconds;
  if (estimate.next_power_level === null || reachesAtSeconds === null) {
    return null;
  }
  const remainingSeconds = reachesAtSeconds - gameTimeSeconds;
  if (remainingSeconds > POWER_LEVEL_SHOWN_SECONDS) {
    return null;
  }
  return remainingSeconds <= 0
    ? `${String(estimate.next_power_level)} any moment`
    : `${String(estimate.next_power_level)} in ~${formatCountdown(remainingSeconds)}`;
}

/**
 * Return an enemy's last trip to base, "went back 7:42 · returns ~0:24", or null once it is 90
 * seconds old.
 */
export function formatLastBack(back: BackEstimate, gameTimeSeconds: number): string | null {
  if (gameTimeSeconds - back.shopped_at_game_time_seconds > BACK_SHOWN_SECONDS) {
    return null;
  }
  const shoppedText = `went back ${formatCountdown(back.shopped_at_game_time_seconds)}`;
  const returnsInSeconds = back.returns_at_game_time_seconds - gameTimeSeconds;
  return returnsInSeconds > 0
    ? `${shoppedText} \u00b7 returns ~${formatCountdown(returnsInSeconds)}`
    : shoppedText;
}

/** Return an enemy's likely next item: "next Infinity Edge · 2.1k left · 40% now". */
export function formatNextItem(estimate: NextItemEstimate): string {
  const guessMark = estimate.likelihood < LIKELY_NEXT_ITEM ? "?" : "";
  const parts = [
    `next ${estimate.item_name}${guessMark}`,
    `${formatThousands(estimate.remaining_gold)} left`,
  ];
  if (estimate.chance_to_afford !== null) {
    parts.push(`${String(Math.round(estimate.chance_to_afford * PERCENT))}% now`);
  }
  return parts.join(" \u00b7 ");
}

/** Return an enemy's latest clue to their place, "at Dragon 0:40 ago", or null once it is old. */
export function formatLastClue(clue: PositionClue, gameTimeSeconds: number): string | null {
  const ageSeconds = gameTimeSeconds - clue.game_time_seconds;
  if (ageSeconds > CLUE_SHOWN_SECONDS) {
    return null;
  }
  return `${clue.place} ${formatCountdown(ageSeconds)} ago`;
}

/** Return where an unseen enemy likely is, "likely bot lane 60% · unseen 0:25", or null. */
export function formatLocation(location: PositionEstimate): string | null {
  const likeliest = location.regions[0];
  const unseenSeconds = location.unseen_seconds;
  if (likeliest === undefined || unseenSeconds === null || unseenSeconds < LOCATION_SHOWN_AFTER_SECONDS) {
    return null;
  }
  const chanceText = `${String(Math.round(likeliest.chance * PERCENT))}%`;
  return `likely ${likeliest.label} ${chanceText} \u00b7 unseen ${formatCountdown(unseenSeconds)}`;
}

/** Return a header of the enemy strip: a label and the player's team's lead, colored by side. */
function leadElement(className: string, label: string, leadGold: number, valueText: string): HTMLElement {
  const header = document.createElement("div");
  header.className = `item-lead ${className}`;
  header.dataset["lead"] = leadGold > 0 ? "ally" : leadGold < 0 ? "enemy" : "even";
  const labelElement = document.createElement("span");
  labelElement.textContent = label;
  const valueElement = document.createElement("span");
  valueElement.className = "item-lead-value";
  valueElement.textContent = valueText;
  header.append(labelElement, valueElement);
  return header;
}

/** Return the enemy strip's headers: the item-gold lead and the estimated gold lead, when known. */
function leadElements(state: OverlayState): HTMLElement[] {
  const headers: HTMLElement[] = [];
  const itemGold = state.team_item_gold;
  if (itemGold !== null) {
    const itemLeadGold = itemGold.ally_item_gold - itemGold.enemy_item_gold;
    headers.push(leadElement("items", "Item gold", itemLeadGold, formatGoldLead(itemLeadGold)));
  }
  const teamGold = state.team_gold;
  if (teamGold !== null) {
    const goldLead = teamGold.ally_total_gold - teamGold.enemy_total_gold;
    const valueText = `${formatGoldLead(goldLead)}${formatBand(teamGold.lead_band_gold)}`;
    headers.push(leadElement("gold-lead", "Gold", goldLead, valueText));
  }
  return headers;
}

/** Return the line of an enemy's defensive stats: "1.3k HP · 59 AR · 39 MR". */
export function formatDefensiveStats(stats: CombatStats): string {
  const healthText = `${formatThousands(stats.health)} HP`;
  return [healthText, `${Math.round(stats.armor)} AR`, `${Math.round(stats.magic_resist)} MR`].join(" · ");
}

const TIER_SHORT_NAMES: Readonly<Record<string, string>> = {
  IRON: "I",
  BRONZE: "B",
  SILVER: "S",
  GOLD: "G",
  PLATINUM: "P",
  EMERALD: "E",
  DIAMOND: "D",
  MASTER: "M",
  GRANDMASTER: "GM",
  CHALLENGER: "C",
};
const DIVISION_NUMBERS: Readonly<Record<string, string>> = { I: "1", II: "2", III: "3", IV: "4" };
const APEX_TIERS: ReadonlySet<string> = new Set(["MASTER", "GRANDMASTER", "CHALLENGER"]);
// A streak this long is worth naming.
const NOTABLE_STREAK = 3;
// With this many recent games and none on the champion, it is new to them.
const GAMES_TO_CALL_A_CHAMPION_NEW = 10;

/** Return a rank in short: "P4" for Platinum IV, "M 120" for Master with 120 LP. */
export function formatRank(ranked: RankedStanding | null): string {
  if (ranked === null) {
    return "Unranked";
  }
  const tierName = TIER_SHORT_NAMES[ranked.tier] ?? ranked.tier;
  if (APEX_TIERS.has(ranked.tier)) {
    return `${tierName} ${String(ranked.league_points)}`;
  }
  return `${tierName}${DIVISION_NUMBERS[ranked.division] ?? ""}`;
}

/** Return a player's record in one line: "P4 · 3–2 W3 · 3 on champ · off-role (MID)". */
export function formatIntel(intel: PlayerIntel): string {
  const parts = [formatRank(intel.ranked)];
  if (intel.recent_game_count > 0) {
    const lossCount = intel.recent_game_count - intel.recent_win_count;
    const streakText =
      Math.abs(intel.streak) >= NOTABLE_STREAK
        ? ` ${intel.streak > 0 ? "W" : "L"}${String(Math.abs(intel.streak))}`
        : "";
    parts.push(`${String(intel.recent_win_count)}\u2013${String(lossCount)}${streakText}`);
  }
  if (intel.champion_game_count > 0) {
    parts.push(`${String(intel.champion_game_count)} on champ`);
  } else if (intel.recent_game_count >= GAMES_TO_CALL_A_CHAMPION_NEW) {
    parts.push("new on champ");
  }
  if (intel.is_off_role) {
    parts.push(`off-role (${ROLE_SHORT_NAMES[intel.usual_position] ?? intel.usual_position})`);
  }
  return parts.join(" \u00b7 ");
}

/** Return the row that draws one enemy: champion, level, item gold, the death timer and stats. */
function enemyRowElement(
  card: PlayerCard,
  gameTimeSeconds: number,
  cooldowns: readonly CooldownTimer[],
): HTMLElement {
  const row = document.createElement("div");
  row.className = "enemy-row";
  row.dataset["dead"] = card.is_dead ? "true" : "false";
  const roleElement = document.createElement("span");
  roleElement.className = "enemy-role";
  roleElement.dataset["confidence"] = card.role_confidence;
  const roleName = ROLE_SHORT_NAMES[card.role] ?? "";
  roleElement.textContent = card.role_confidence === "guess" && roleName !== "" ? `${roleName}?` : roleName;
  const nameElement = document.createElement("span");
  nameElement.className = "enemy-name";
  nameElement.textContent = card.champion_name;
  const levelElement = document.createElement("span");
  levelElement.className = "enemy-level";
  levelElement.textContent = String(card.level);
  const goldElement = document.createElement("span");
  goldElement.className = "enemy-gold";
  goldElement.textContent = card.item_gold === null ? "" : formatGold(card.item_gold);
  row.append(roleElement, nameElement, levelElement, goldElement);
  const respawnsAtSeconds = card.respawns_at_game_time_seconds;
  if (card.is_dead && respawnsAtSeconds !== null) {
    const respawnElement = document.createElement("span");
    respawnElement.className = "enemy-respawn";
    respawnElement.textContent = formatCountdown(respawnsAtSeconds - gameTimeSeconds);
    row.append(respawnElement);
  }
  const runningCooldowns = cooldowns.filter(
    (timer) =>
      timer.champion_name === card.champion_name && timer.ready_at_game_time_seconds > gameTimeSeconds,
  );
  if (runningCooldowns.length > 0) {
    const cooldownsElement = document.createElement("span");
    cooldownsElement.className = "enemy-cooldowns";
    cooldownsElement.replaceChildren(
      ...runningCooldowns.map((timer) => cooldownBadgeElement(timer, gameTimeSeconds)),
    );
    row.append(cooldownsElement);
  }
  if (card.intel !== null) {
    const intelElement = document.createElement("span");
    intelElement.className = "enemy-intel";
    intelElement.dataset["offRole"] = card.intel.is_off_role ? "true" : "false";
    intelElement.textContent = formatIntel(card.intel);
    row.append(intelElement);
  }
  if (card.combat_stats !== null) {
    const statsElement = document.createElement("span");
    statsElement.className = "enemy-stats";
    statsElement.dataset["source"] = card.combat_stats.source;
    statsElement.textContent = formatDefensiveStats(card.combat_stats);
    row.append(statsElement);
  }
  const powerLevelText =
    card.level_estimate === null ? null : formatPowerLevelSoon(card.level_estimate, gameTimeSeconds);
  if (powerLevelText !== null) {
    const powerLevelElement = document.createElement("span");
    powerLevelElement.className = "enemy-power-level";
    powerLevelElement.textContent = powerLevelText;
    row.append(powerLevelElement);
  }
  const locationText = card.location === null ? null : formatLocation(card.location);
  if (locationText !== null) {
    const locationElement = document.createElement("span");
    locationElement.className = "enemy-location";
    locationElement.textContent = locationText;
    row.append(locationElement);
  }
  const lastClueText =
    card.last_clue === null || card.is_dead ? null : formatLastClue(card.last_clue, gameTimeSeconds);
  if (lastClueText !== null) {
    const clueElement = document.createElement("span");
    clueElement.className = "enemy-seen";
    clueElement.dataset["kind"] = card.last_clue?.kind ?? "";
    clueElement.textContent = lastClueText;
    row.append(clueElement);
  }
  const lastBackText = card.last_back === null ? null : formatLastBack(card.last_back, gameTimeSeconds);
  if (lastBackText !== null) {
    const backElement = document.createElement("span");
    backElement.className = "enemy-back";
    backElement.textContent = lastBackText;
    row.append(backElement);
  }
  if (card.next_item !== null) {
    const nextItemElement = document.createElement("span");
    nextItemElement.className = "enemy-next-item";
    const chance = card.next_item.chance_to_afford;
    nextItemElement.dataset["likely"] = chance !== null && chance >= LIKELY_TO_AFFORD ? "true" : "false";
    nextItemElement.textContent = formatNextItem(card.next_item);
    row.append(nextItemElement);
  }
  if (card.gold !== null) {
    const unspentElement = document.createElement("span");
    unspentElement.className = "enemy-unspent";
    unspentElement.dataset["source"] = card.gold.source;
    unspentElement.textContent = formatUnspentGold(card.gold);
    row.append(unspentElement);
  }
  return row;
}

/** Return the badge of one marked spell: its label and the time until it is back, "F 4:12". */
function cooldownBadgeElement(timer: CooldownTimer, gameTimeSeconds: number): HTMLElement {
  const badge = document.createElement("span");
  badge.className = "cooldown-badge";
  badge.dataset["spell"] = timer.spell;
  badge.textContent = `${timer.label} ${formatCountdown(timer.ready_at_game_time_seconds - gameTimeSeconds)}`;
  return badge;
}

/** Return a card's place in role order, unknown roles last. */
function roleRank(card: PlayerCard): number {
  const rank = ROLE_ORDER.indexOf(card.role);
  return rank === -1 ? ROLE_ORDER.length : rank;
}

/** Draw the enemy strip: each enemy's champion, level and death timer. */
function renderEnemyStrip(nowMilliseconds: number): void {
  const strip = requireElement("enemy-strip");
  const received = latestReceivedState;
  const gameTimeSeconds = received === null ? null : currentGameTimeSeconds(received, nowMilliseconds);
  if (received === null || !received.state.is_game_running || gameTimeSeconds === null) {
    strip.hidden = true;
    strip.replaceChildren();
    return;
  }
  const enemyCards = [...received.state.players.filter((card) => card.side === "enemy")].sort(
    (first, second) => roleRank(first) - roleRank(second),
  );
  strip.hidden = enemyCards.length === 0;
  const rows = enemyCards.map((card) =>
    enemyRowElement(card, gameTimeSeconds, received.state.cooldowns),
  );
  strip.replaceChildren(...leadElements(received.state), ...rows);
}

/** Return the element that draws one callout. */
function calloutElement(callout: Callout): HTMLElement {
  const element = document.createElement("div");
  element.className = "callout";
  element.dataset["calloutId"] = callout.callout_id;
  element.dataset["kind"] = callout.kind;
  element.textContent = callout.text;
  return element;
}

/**
 * Draw the callouts still to be shown. Each element is kept from one render to the next by its id,
 * so that its entrance plays once and not at every render.
 */
function renderCallouts(nowMilliseconds: number): void {
  const list = requireElement("callouts");
  const received = latestReceivedState;
  const gameTimeSeconds = received === null ? null : currentGameTimeSeconds(received, nowMilliseconds);
  const shownCallouts =
    received === null || gameTimeSeconds === null || !received.state.is_game_running
      ? []
      : received.state.callouts.filter((callout) => callout.shown_until_game_time_seconds > gameTimeSeconds);
  const shownIds = new Set(shownCallouts.map((callout) => callout.callout_id));
  for (const child of Array.from(list.children)) {
    if (child instanceof HTMLElement && !shownIds.has(child.dataset["calloutId"] ?? "")) {
      child.remove();
    }
  }
  const presentIds = new Set(
    Array.from(list.children).map((child) => (child instanceof HTMLElement ? (child.dataset["calloutId"] ?? "") : "")),
  );
  for (const callout of shownCallouts) {
    if (!presentIds.has(callout.callout_id)) {
      list.append(calloutElement(callout));
    }
  }
}

/** Draw every widget. */
function render(): void {
  const nowMilliseconds = performance.now();
  renderDragonWidget(nowMilliseconds);
  renderObjectivePills(nowMilliseconds);
  renderEnemyStrip(nowMilliseconds);
  renderCallouts(nowMilliseconds);
}

/** Listen to the engine; the browser reconnects by itself when the stream drops. */
function listenToEngine(): void {
  const stateStream = new EventSource(EVENTS_PATH);
  stateStream.addEventListener("message", (message: MessageEvent<string>) => {
    const parsedState: unknown = JSON.parse(message.data);
    if (!isOverlayState(parsedState)) {
      return;
    }
    latestReceivedState = { state: parsedState, receivedAtMilliseconds: performance.now() };
    render();
  });
}

listenToEngine();
window.setInterval(render, RENDER_INTERVAL_MILLISECONDS);
