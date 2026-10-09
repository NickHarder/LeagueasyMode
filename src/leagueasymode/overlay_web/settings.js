/**
 * The settings page: what the overlay shows. Each change is saved at once and reaches the overlay
 * with its next state; the engine keeps it in `preferences.json` for the next run.
 */
import { PREFERENCE_NAMES, isOverlayPreferences } from "./state.js";
// The header the server asks of a change, which a page elsewhere cannot send.
const REQUEST_HEADER = "X-LeagueasyMode-Request";
const REQUEST_VALUE = "preferences";
const DESCRIPTIONS = {
    show_win_chance: ["Win chance", "Your team's chance to win, and what moves it most, at the top of the enemy strip."],
    show_fight_chance: ["Fight chance", "The chance your team wins an even fight now, and how much of their damage is physical."],
    show_contests: ["Objective contests", "How long your team takes on a monster that is up, and whether the enemy can come."],
    show_you_panel: ["You panel", "What to build against their damage, how long you have held your gold, and your CS pace."],
    show_minimap: ["Minimap layer", "Where each enemy likely is, the camps down and their control wards, over League's minimap."],
    show_enemy_estimates: [
        "Enemy estimates",
        "Each enemy's unspent gold, next item, last trip to base and likely place; the camps down and their wards.",
    ],
    show_callouts: ["Callouts", "Short notices when something happens, such as an enemy reaching level 6."],
    show_suggestions: ["Suggestions", "Callouts that name an action, such as “take it”."],
};
function htmlElement(name, className, text) {
    const element = document.createElement(name);
    if (className !== "") {
        element.className = className;
    }
    if (text !== undefined) {
        element.textContent = text;
    }
    return element;
}
/** Return the preferences the form shows now. */
function chosenPreferences(form) {
    const chosen = {};
    for (const name of PREFERENCE_NAMES) {
        const input = form.elements.namedItem(name);
        chosen[name] = input instanceof HTMLInputElement && input.checked;
    }
    return chosen;
}
async function save(form, status) {
    status.textContent = "Saving…";
    status.dataset["state"] = "saving";
    try {
        const response = await fetch("/preferences", {
            method: "PUT",
            headers: { "Content-Type": "application/json", [REQUEST_HEADER]: REQUEST_VALUE },
            body: JSON.stringify(chosenPreferences(form)),
        });
        status.textContent = response.ok ? "Saved" : `Not saved: the engine answered ${String(response.status)}`;
        status.dataset["state"] = response.ok ? "saved" : "failed";
    }
    catch {
        status.textContent = "Not saved: the engine is not running";
        status.dataset["state"] = "failed";
    }
}
/** Draw the form, one switch for each preference. */
export function renderSettings(root, preferences) {
    const form = htmlElement("form", "settings-form");
    const status = htmlElement("p", "settings-status");
    status.setAttribute("role", "status");
    for (const name of PREFERENCE_NAMES) {
        const [title, description] = DESCRIPTIONS[name];
        const label = htmlElement("label", "settings-row");
        const input = htmlElement("input", "");
        input.type = "checkbox";
        input.name = name;
        input.checked = preferences[name];
        input.addEventListener("change", () => {
            void save(form, status);
        });
        // The switch is named by its title alone; its description is read after it.
        const titleElement = htmlElement("strong", "", title);
        titleElement.id = `${name}-title`;
        const descriptionElement = htmlElement("span", "settings-description", description);
        descriptionElement.id = `${name}-description`;
        input.setAttribute("aria-labelledby", titleElement.id);
        input.setAttribute("aria-describedby", descriptionElement.id);
        const text = htmlElement("span", "settings-text");
        text.append(titleElement, descriptionElement);
        label.append(input, text);
        form.append(label);
    }
    root.replaceChildren(htmlElement("h1", "summary-result", "What the overlay shows"), htmlElement("p", "summary-detail", "Each change shows at once, and is kept for the next game."), form, status);
}
async function start() {
    const root = document.getElementById("settings");
    if (root === null) {
        return;
    }
    try {
        const response = await fetch("/preferences");
        const preferences = response.ok ? await response.json() : null;
        if (isOverlayPreferences(preferences)) {
            renderSettings(root, preferences);
            return;
        }
    }
    catch {
        // Shown below: the engine is not running.
    }
    root.replaceChildren(htmlElement("h1", "summary-result", "Settings"), htmlElement("p", "summary-detail", "The engine is not running; start LeagueasyMode and open this page again."));
}
void start();
