/**
 * The overlay's widgets: listen to the engine's stream of states and draw them.
 *
 * The engine sends a state about twice a second. Between two, the countdown is moved on from the
 * time the last one arrived, so it ticks smoothly; it is never moved on by more than a couple of
 * seconds, so a paused or stalled game does not run its timers down.
 */
import { isOverlayState, } from "./state.js";
const EVENTS_PATH = "/events";
const RENDER_INTERVAL_MILLISECONDS = 250;
const LONGEST_EXTRAPOLATION_SECONDS = 2;
const MILLISECONDS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
const SOUL_COLORS = {
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
const OBJECTIVE_NAMES = {
    baron: "Baron",
    rift_herald: "Herald",
    voidgrubs: "Voidgrubs",
};
const BUFF_NAMES = {
    baron: "Baron buff",
    elder: "Elder buff",
};
const LANE_NAMES = {
    top: "top",
    mid: "mid",
    bot: "bot",
};
const GOLD_PER_THOUSAND = 1000;
// A timer whose rule is not yet confirmed for this season is shown with this mark.
const PROVISIONAL_MARK = "~";
let latestReceivedState = null;
/** Return the game's clock now, moved on from the last state by at most a couple of seconds. */
function currentGameTimeSeconds(received, nowMilliseconds) {
    const reportedGameTimeSeconds = received.state.game_time_seconds;
    if (reportedGameTimeSeconds === null) {
        return null;
    }
    const elapsedSeconds = (nowMilliseconds - received.receivedAtMilliseconds) / MILLISECONDS_PER_SECOND;
    return reportedGameTimeSeconds + Math.min(Math.max(elapsedSeconds, 0), LONGEST_EXTRAPOLATION_SECONDS);
}
/** Return a duration as minutes and seconds, rounded up: 61.2 seconds is "1:02". */
export function formatCountdown(remainingSeconds) {
    const wholeSeconds = Math.max(0, Math.ceil(remainingSeconds));
    const minutes = Math.floor(wholeSeconds / SECONDS_PER_MINUTE);
    const seconds = wholeSeconds % SECONDS_PER_MINUTE;
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
/** Return the small line under the timer: the dragons each side has, and the soul. */
function dragonDetail(dragon) {
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
function requireElement(elementId) {
    const element = document.getElementById(elementId);
    if (element === null) {
        throw new Error(`the overlay page has no #${elementId}`);
    }
    return element;
}
/** Draw the dragon widget for the latest state, or hide it when no game runs. */
function renderDragonWidget(nowMilliseconds) {
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
export function objectivePill(timer, gameTimeSeconds) {
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
export function buffPill(timer, gameTimeSeconds) {
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
export function inhibitorPill(timer, gameTimeSeconds) {
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
export function numbersPill(window, gameTimeSeconds) {
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
function stripPills(state, gameTimeSeconds) {
    const candidatePills = [
        state.numbers_window === null ? null : numbersPill(state.numbers_window, gameTimeSeconds),
        ...state.objectives.map((timer) => objectivePill(timer, gameTimeSeconds)),
        ...state.buffs.map((timer) => buffPill(timer, gameTimeSeconds)),
        ...state.inhibitors.map((timer) => inhibitorPill(timer, gameTimeSeconds)),
    ];
    return candidatePills.filter((pill) => pill !== null);
}
/** Return the element that draws one pill. */
function pillElement(pill) {
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
function renderObjectivePills(nowMilliseconds) {
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
export function formatGold(gold) {
    return `${(gold / GOLD_PER_THOUSAND).toFixed(1)}k`;
}
/** Return a team's item-gold lead with its sign: "+1.2k", "−0.8k", or "even". */
export function formatGoldLead(leadGold) {
    const roundedLead = Math.round(leadGold / 100) * 100;
    if (roundedLead === 0) {
        return "even";
    }
    return roundedLead > 0 ? `+${formatGold(roundedLead)}` : `\u2212${formatGold(-roundedLead)}`;
}
/** Return the enemy strip's header: the player's team's item-gold lead, when it is known. */
function itemLeadElement(state) {
    const teamGold = state.team_item_gold;
    if (teamGold === null) {
        return null;
    }
    const leadGold = teamGold.ally_item_gold - teamGold.enemy_item_gold;
    const header = document.createElement("div");
    header.className = "item-lead";
    header.dataset["lead"] = leadGold > 0 ? "ally" : leadGold < 0 ? "enemy" : "even";
    const labelElement = document.createElement("span");
    labelElement.textContent = "Item gold";
    const valueElement = document.createElement("span");
    valueElement.className = "item-lead-value";
    valueElement.textContent = formatGoldLead(leadGold);
    header.append(labelElement, valueElement);
    return header;
}
/** Return the row that draws one enemy: champion, level, item gold, and the death timer. */
function enemyRowElement(card, gameTimeSeconds) {
    const row = document.createElement("div");
    row.className = "enemy-row";
    row.dataset["dead"] = card.is_dead ? "true" : "false";
    const nameElement = document.createElement("span");
    nameElement.className = "enemy-name";
    nameElement.textContent = card.champion_name;
    const levelElement = document.createElement("span");
    levelElement.className = "enemy-level";
    levelElement.textContent = String(card.level);
    const goldElement = document.createElement("span");
    goldElement.className = "enemy-gold";
    goldElement.textContent = card.item_gold === null ? "" : formatGold(card.item_gold);
    row.append(nameElement, levelElement, goldElement);
    const respawnsAtSeconds = card.respawns_at_game_time_seconds;
    if (card.is_dead && respawnsAtSeconds !== null) {
        const respawnElement = document.createElement("span");
        respawnElement.className = "enemy-respawn";
        respawnElement.textContent = formatCountdown(respawnsAtSeconds - gameTimeSeconds);
        row.append(respawnElement);
    }
    return row;
}
/** Draw the enemy strip: each enemy's champion, level and death timer. */
function renderEnemyStrip(nowMilliseconds) {
    const strip = requireElement("enemy-strip");
    const received = latestReceivedState;
    const gameTimeSeconds = received === null ? null : currentGameTimeSeconds(received, nowMilliseconds);
    if (received === null || !received.state.is_game_running || gameTimeSeconds === null) {
        strip.hidden = true;
        strip.replaceChildren();
        return;
    }
    const enemyCards = received.state.players.filter((card) => card.side === "enemy");
    strip.hidden = enemyCards.length === 0;
    const header = itemLeadElement(received.state);
    const rows = enemyCards.map((card) => enemyRowElement(card, gameTimeSeconds));
    strip.replaceChildren(...(header === null ? rows : [header, ...rows]));
}
/** Return the element that draws one callout. */
function calloutElement(callout) {
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
function renderCallouts(nowMilliseconds) {
    const list = requireElement("callouts");
    const received = latestReceivedState;
    const gameTimeSeconds = received === null ? null : currentGameTimeSeconds(received, nowMilliseconds);
    const shownCallouts = received === null || gameTimeSeconds === null || !received.state.is_game_running
        ? []
        : received.state.callouts.filter((callout) => callout.shown_until_game_time_seconds > gameTimeSeconds);
    const shownIds = new Set(shownCallouts.map((callout) => callout.callout_id));
    for (const child of Array.from(list.children)) {
        if (child instanceof HTMLElement && !shownIds.has(child.dataset["calloutId"] ?? "")) {
            child.remove();
        }
    }
    const presentIds = new Set(Array.from(list.children).map((child) => (child instanceof HTMLElement ? (child.dataset["calloutId"] ?? "") : "")));
    for (const callout of shownCallouts) {
        if (!presentIds.has(callout.callout_id)) {
            list.append(calloutElement(callout));
        }
    }
}
/** Draw every widget. */
function render() {
    const nowMilliseconds = performance.now();
    renderDragonWidget(nowMilliseconds);
    renderObjectivePills(nowMilliseconds);
    renderEnemyStrip(nowMilliseconds);
    renderCallouts(nowMilliseconds);
}
/** Listen to the engine; the browser reconnects by itself when the stream drops. */
function listenToEngine() {
    const stateStream = new EventSource(EVENTS_PATH);
    stateStream.addEventListener("message", (message) => {
        const parsedState = JSON.parse(message.data);
        if (!isOverlayState(parsedState)) {
            return;
        }
        latestReceivedState = { state: parsedState, receivedAtMilliseconds: performance.now() };
        render();
    });
}
listenToEngine();
window.setInterval(render, RENDER_INTERVAL_MILLISECONDS);
