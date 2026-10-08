/**
 * The overlay's widgets: listen to the engine's stream of states and draw them.
 *
 * The engine sends a state about twice a second. Between two, the countdown is moved on from the
 * time the last one arrived, so it ticks smoothly; it is never moved on by more than a couple of
 * seconds, so a paused or stalled game does not run its timers down.
 */
import { isOverlayState } from "./state.js";
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
/** Draw every widget. */
function render() {
    renderDragonWidget(performance.now());
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
