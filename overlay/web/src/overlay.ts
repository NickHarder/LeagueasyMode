/**
 * The overlay's widgets: listen to the engine's stream of states and draw them.
 *
 * The engine sends a state about twice a second. Between two, the countdown is moved on from the
 * time the last one arrived, so it ticks smoothly; it is never moved on by more than a couple of
 * seconds, so a paused or stalled game does not run its timers down.
 */

import {
  type BuffTimer,
  type DragonTimer,
  type InhibitorTimer,
  type ObjectiveTimer,
  type OverlayState,
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
// A timer whose rule is not yet confirmed for this season is shown with this mark.
const PROVISIONAL_MARK = "~";

/** One small pill of the objective strip: its words, its time, and how it is styled. */
interface Pill {
  readonly label: string;
  readonly timeText: string;
  readonly kind: "objective" | "buff" | "inhibitor";
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

/** Return every pill to show beside the dragon, in a steady order. */
function stripPills(state: OverlayState, gameTimeSeconds: number): Pill[] {
  const candidatePills = [
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

/** Draw every widget. */
function render(): void {
  const nowMilliseconds = performance.now();
  renderDragonWidget(nowMilliseconds);
  renderObjectivePills(nowMilliseconds);
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
