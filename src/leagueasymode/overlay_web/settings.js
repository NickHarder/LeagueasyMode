/**
 * The settings page: what the overlay shows, where, and the friends list. Each change of what
 * shows is saved at once and reaches the overlay with its next state; the engine keeps it in
 * `preferences.json` for the next run. The layout's sliders place and size each widget, and fit
 * the minimap layer, moving the overlay as they slide; the engine keeps them in `layout.json`,
 * as it does a drag in edit mode (layout slice L.2). The friends' Riot IDs are saved with their own button and
 * kept in `friends.json`; the overlay and the post-game case mark those players (phase 11.5).
 */
import { USUAL_MINIMAP_FIT, WIDGET_TITLES } from "./layout.js";
import { MAX_MINIMAP_FIT_SCALE, MAX_MINIMAP_NUDGE_SHARE, MAX_WIDGET_SCALE, MIN_MINIMAP_FIT_SCALE, MIN_WIDGET_SCALE, MOVABLE_WIDGETS, PREFERENCE_NAMES, isOverlayLayout, isOverlayPreferences, } from "./state.js";
// The header the server asks of a change, which a page elsewhere cannot send.
const REQUEST_HEADER = "X-LeagueasyMode-Request";
const REQUEST_VALUE = "preferences";
const FRIENDS_REQUEST_VALUE = "friends";
const CLAUDE_TAKE_REQUEST_VALUE = "claude-take";
const LAYOUT_REQUEST_VALUE = "layout";
// A slider's moves are sent once it rests this long, so the overlay follows without a request a step.
const LAYOUT_SAVE_DELAY_MILLISECONDS = 100;
const PERCENT = 100;
// Shares are kept to four decimals, as a drag in edit mode keeps them.
const SHARE_PRECISION = 10_000;
function isClaudeTakeAnswer(value) {
    if (typeof value !== "object" || value === null) {
        return false;
    }
    const record = value;
    const settings = record["settings"];
    if (typeof settings !== "object" || settings === null) {
        return false;
    }
    const settingsRecord = settings;
    return (typeof record["is_available"] === "boolean" &&
        typeof settingsRecord["enabled"] === "boolean" &&
        typeof settingsRecord["style"] === "string" &&
        typeof settingsRecord["model"] === "string");
}
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
    show_callouts: ["Callouts", "Short notices when something asks for action, such as a numbers advantage or an objective soon."],
    show_suggestions: ["Suggestions", "Callouts that name an action, such as “take it”."],
    show_moments: [
        "Moments about friends",
        "A line for chat when a friend's game hands over ammo, such as a second death to their lane opponent. Never on screen; ⌃⌥C copies the newest.",
    ],
    show_team_calls: [
        "Team calls",
        "Calm calls for the whole team, such as staying alive and warding before a dragon, to paste in team chat. Never on screen; ⌃⌥C copies the newest.",
    ],
    speak_callouts: ["Speak callouts", "Each new callout read aloud in macOS’s voice, as it shows. Off unless turned on."],
    detailed_enemy_rows: [
        "Detailed enemy rows",
        "Every line on each enemy’s row: rank and record all game, health, armor and magic resist, unspent gold, next item and likely place. Off: only what may change a decision now.",
    ],
    minimap_roamers_only: [
        "Minimap: jungler and roamers only",
        "Marks only the enemy jungler, and laners likely away from their lane, on the minimap layer; a laner holding their wave is left off. Off unless turned on.",
    ],
    details_on_hold: [
        "Details only while Tab or ⌥ is held",
        "At a glance, one short line an enemy and the newest two callouts; holding Tab or ⌥ Option shows the rest: win and fight chances, gold, the You panel, each enemy’s second line and the spell buttons. Off: always shown.",
    ],
    click_to_mark: [
        "Click to mark spells",
        "Buttons on each enemy’s row that start their Flash, other summoner spell or ultimate timer in one click, beside the ⌃⌥ shortcuts. The overlay takes the clicks on those buttons only. Off unless turned on.",
    ],
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
/** Return the Riot IDs typed in the friends box, one a line, blank lines left out. */
export function riotIdsOf(text) {
    return text
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line !== "");
}
function isFriendsList(value) {
    return (typeof value === "object" &&
        value !== null &&
        Array.isArray(value["riot_ids"]) &&
        value["riot_ids"].every((item) => typeof item === "string"));
}
async function saveFriends(box, status) {
    status.textContent = "Saving…";
    status.dataset["state"] = "saving";
    try {
        const response = await fetch("/friends", {
            method: "PUT",
            headers: { "Content-Type": "application/json", [REQUEST_HEADER]: FRIENDS_REQUEST_VALUE },
            body: JSON.stringify({ riot_ids: riotIdsOf(box.value) }),
        });
        const answer = await response.json();
        if (response.ok && isFriendsList(answer)) {
            box.value = answer.riot_ids.join("\n");
            status.textContent = `Saved: ${String(answer.riot_ids.length)} friends`;
            status.dataset["state"] = "saved";
            return;
        }
        const message = typeof answer === "object" && answer !== null && typeof answer["message"] === "string"
            ? String(answer["message"])
            : `the engine answered ${String(response.status)}`;
        status.textContent = `Not saved: ${message}`;
        status.dataset["state"] = "failed";
    }
    catch {
        status.textContent = "Not saved: the engine is not running";
        status.dataset["state"] = "failed";
    }
}
/** Draw the friends list: a box of Riot IDs, one a line, and its button. */
function friendsElement(riotIds) {
    const section = htmlElement("section", "settings-friends");
    const heading = htmlElement("h2", "", "Friends");
    heading.id = "friends-title";
    const description = htmlElement("p", "settings-description", "Their Riot IDs, one a line, as name#tag. The overlay marks them in a game and in the post-game case. Kept on this Mac only.");
    description.id = "friends-description";
    const box = htmlElement("textarea", "settings-friends-box");
    box.name = "friends";
    box.rows = 6;
    box.placeholder = "Name#TAG";
    box.spellcheck = false;
    box.value = riotIds.join("\n");
    box.setAttribute("aria-labelledby", heading.id);
    box.setAttribute("aria-describedby", description.id);
    const button = htmlElement("button", "settings-friends-save", "Save friends");
    button.type = "button";
    const status = htmlElement("p", "settings-friends-status");
    status.setAttribute("role", "status");
    button.addEventListener("click", () => {
        void saveFriends(box, status);
    });
    section.append(heading, description, box, button, status);
    return section;
}
function claudeTakeAvailabilityText(isAvailable) {
    return isAvailable
        ? "The claude command was found on this Mac."
        : "The claude command was not found on this Mac: install Claude Code and sign in, or set LEAGUEASYMODE_CLAUDE_COMMAND.";
}
async function saveClaudeTake(enabled, style, model, status) {
    status.textContent = "Saving…";
    status.dataset["state"] = "saving";
    try {
        const response = await fetch("/claude-take", {
            method: "PUT",
            headers: { "Content-Type": "application/json", [REQUEST_HEADER]: CLAUDE_TAKE_REQUEST_VALUE },
            body: JSON.stringify({ enabled: enabled.checked, style: style.value.trim(), model: model.value.trim() }),
        });
        const answer = await response.json();
        if (response.ok && isClaudeTakeAnswer(answer)) {
            status.textContent = `Saved. ${claudeTakeAvailabilityText(answer.is_available)}`;
            status.dataset["state"] = "saved";
            return;
        }
        status.textContent = `Not saved: the engine answered ${String(response.status)}`;
        status.dataset["state"] = "failed";
    }
    catch {
        status.textContent = "Not saved: the engine is not running";
        status.dataset["state"] = "failed";
    }
}
function claudeFieldElement(labelText, input) {
    const label = htmlElement("label", "settings-claude-field");
    label.append(htmlElement("span", "", labelText), input);
    return label;
}
/** Draw Claude's take's settings: on or off, the style, the model, and its button. */
function claudeTakeElement(answer) {
    const section = htmlElement("section", "settings-claude");
    const description = htmlElement("p", "settings-description", "Rewords the lines ⌃⌥C copies with the claude command on this Mac and your own Claude login, in your style. Only the wording and the style are sent: numbers and champions are filled back in here, and every line is checked again. Each line uses your Claude plan. Off unless turned on.");
    const enabled = htmlElement("input", "");
    enabled.type = "checkbox";
    enabled.name = "claude_take_enabled";
    enabled.checked = answer.settings.enabled;
    const enabledLabel = htmlElement("label", "settings-claude-field settings-claude-switch");
    enabledLabel.append(enabled, document.createTextNode(" Reword with Claude"));
    const style = htmlElement("input", "");
    style.type = "text";
    style.name = "claude_take_style";
    style.maxLength = 200;
    style.placeholder = "pirate, sports commentator, …";
    style.value = answer.settings.style;
    const model = htmlElement("input", "");
    model.type = "text";
    model.name = "claude_take_model";
    model.maxLength = 80;
    model.placeholder = "the claude command's default";
    model.value = answer.settings.model;
    const button = htmlElement("button", "settings-friends-save", "Save Claude's take");
    button.type = "button";
    const status = htmlElement("p", "settings-claude-status", claudeTakeAvailabilityText(answer.is_available));
    status.setAttribute("role", "status");
    button.addEventListener("click", () => {
        void saveClaudeTake(enabled, style, model, status);
    });
    section.append(htmlElement("h2", "", "Claude's take"), description, enabledLabel, claudeFieldElement("Style", style), claudeFieldElement("Model", model), button, status);
    return section;
}
function shareOfPercent(percent) {
    return Math.round((percent / PERCENT) * SHARE_PRECISION) / SHARE_PRECISION;
}
function percentText(percent) {
    return `${String(percent)}%`;
}
function sliderElement(id, visibleLabel, accessibleName, range, onSlide) {
    const row = htmlElement("div", "settings-slider");
    const label = htmlElement("label", "", visibleLabel);
    label.htmlFor = id;
    const input = htmlElement("input", "");
    input.type = "range";
    input.id = id;
    input.min = String(range.min);
    input.max = String(range.max);
    input.step = String(range.step);
    input.setAttribute("aria-label", accessibleName);
    const output = htmlElement("output", "");
    output.htmlFor.add(id);
    const setValue = (percent) => {
        input.value = String(percent);
        output.textContent = percentText(percent);
    };
    input.addEventListener("input", () => {
        const percent = Number(input.value);
        output.textContent = percentText(percent);
        onSlide(percent);
    });
    row.append(label, input, output);
    return { row, input, setValue };
}
/** Draw the layout's sliders: each widget's place and size, and the minimap layer's fit. */
function layoutElement(startLayout) {
    let layout = startLayout;
    let saveTimer;
    const section = htmlElement("section", "settings-layout");
    const status = htmlElement("p", "settings-layout-status");
    status.setAttribute("role", "status");
    const saveLayout = async () => {
        try {
            const response = await fetch("/layout", {
                method: "PUT",
                headers: { "Content-Type": "application/json", [REQUEST_HEADER]: LAYOUT_REQUEST_VALUE },
                body: JSON.stringify(layout),
            });
            status.textContent = response.ok ? "Saved" : `Not saved: the engine answered ${String(response.status)}`;
            status.dataset["state"] = response.ok ? "saved" : "failed";
        }
        catch {
            status.textContent = "Not saved: the engine is not running";
            status.dataset["state"] = "failed";
        }
    };
    const change = (changed) => {
        layout = changed;
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(() => {
            saveTimer = undefined;
            void saveLayout();
        }, LAYOUT_SAVE_DELAY_MILLISECONDS);
    };
    const setOffset = (widget, offset) => {
        const { [widget]: _previous, ...otherOffsets } = layout.offsets;
        const isUsualPlace = offset.x_share === 0 && offset.y_share === 0;
        change({ ...layout, offsets: isUsualPlace ? otherOffsets : { ...otherOffsets, [widget]: offset } });
    };
    const setScale = (widget, scale) => {
        const { [widget]: _previous, ...otherScales } = layout.scales;
        change({ ...layout, scales: scale === 1 ? otherScales : { ...otherScales, [widget]: scale } });
    };
    const setFit = (fit) => {
        change({ ...layout, minimap_fit: fit });
    };
    const refreshers = [];
    const widgetGroups = MOVABLE_WIDGETS.map((widget) => {
        const title = WIDGET_TITLES[widget];
        const placeRange = { min: -PERCENT, max: PERCENT, step: 0.5 };
        const offsetOf = () => layout.offsets[widget] ?? { x_share: 0, y_share: 0 };
        const across = sliderElement(`${widget}-x`, "X", `${title} X`, placeRange, (percent) => {
            setOffset(widget, { ...offsetOf(), x_share: shareOfPercent(percent) });
        });
        const down = sliderElement(`${widget}-y`, "Y", `${title} Y`, placeRange, (percent) => {
            setOffset(widget, { ...offsetOf(), y_share: shareOfPercent(percent) });
        });
        const sizeRange = { min: MIN_WIDGET_SCALE * PERCENT, max: MAX_WIDGET_SCALE * PERCENT, step: 1 };
        const size = sliderElement(`${widget}-size`, "Size", `${title} size`, sizeRange, (percent) => {
            setScale(widget, percent / PERCENT);
        });
        const refresh = () => {
            across.setValue(Math.round(offsetOf().x_share * PERCENT * 2) / 2);
            down.setValue(Math.round(offsetOf().y_share * PERCENT * 2) / 2);
            size.setValue(Math.round((layout.scales[widget] ?? 1) * PERCENT));
        };
        refreshers.push(refresh);
        const reset = htmlElement("button", "settings-layout-reset", "Reset");
        reset.type = "button";
        reset.setAttribute("aria-label", `Reset ${title}`);
        reset.addEventListener("click", () => {
            const { [widget]: _offset, ...otherOffsets } = layout.offsets;
            const { [widget]: _scale, ...otherScales } = layout.scales;
            change({ ...layout, offsets: otherOffsets, scales: otherScales });
            refresh();
        });
        const group = htmlElement("fieldset", "settings-layout-widget");
        group.append(htmlElement("legend", "", title), across.row, down.row, size.row, reset);
        return group;
    });
    const fitScaleRange = { min: MIN_MINIMAP_FIT_SCALE * PERCENT, max: MAX_MINIMAP_FIT_SCALE * PERCENT, step: 1 };
    const nudgeRange = { min: -MAX_MINIMAP_NUDGE_SHARE * PERCENT, max: MAX_MINIMAP_NUDGE_SHARE * PERCENT, step: 0.1 };
    const fitSize = sliderElement("minimap-size", "Size", "Minimap size", fitScaleRange, (percent) => {
        setFit({ ...layout.minimap_fit, scale: percent / PERCENT });
    });
    const fitAcross = sliderElement("minimap-x", "X", "Minimap X", nudgeRange, (percent) => {
        setFit({ ...layout.minimap_fit, x_share: shareOfPercent(percent) });
    });
    const fitDown = sliderElement("minimap-y", "Y", "Minimap Y", nudgeRange, (percent) => {
        setFit({ ...layout.minimap_fit, y_share: shareOfPercent(percent) });
    });
    const refreshFit = () => {
        fitSize.setValue(Math.round(layout.minimap_fit.scale * PERCENT));
        fitAcross.setValue(Math.round(layout.minimap_fit.x_share * PERCENT * 10) / 10);
        fitDown.setValue(Math.round(layout.minimap_fit.y_share * PERCENT * 10) / 10);
    };
    refreshers.push(refreshFit);
    const fitReset = htmlElement("button", "settings-layout-reset", "Reset");
    fitReset.type = "button";
    fitReset.setAttribute("aria-label", "Reset minimap fit");
    fitReset.addEventListener("click", () => {
        setFit(USUAL_MINIMAP_FIT);
        refreshFit();
    });
    const fitGroup = htmlElement("fieldset", "settings-layout-widget");
    fitGroup.append(htmlElement("legend", "", "Minimap layer"), htmlElement("p", "settings-description", "Fits the layer over League's minimap where the two do not line up."), fitSize.row, fitAcross.row, fitDown.row, fitReset);
    for (const refresh of refreshers) {
        refresh();
    }
    // Back on this page after a drag in edit mode: show where the widgets are now.
    window.addEventListener("focus", () => {
        void (async () => {
            try {
                const response = await fetch("/layout");
                const answer = response.ok ? await response.json() : null;
                if (isOverlayLayout(answer) && saveTimer === undefined) {
                    layout = answer;
                    for (const refresh of refreshers) {
                        refresh();
                    }
                }
            }
            catch {
                // The engine has stopped; the sliders stay as they are.
            }
        })();
    });
    section.append(htmlElement("h2", "", "Layout"), htmlElement("p", "settings-description", "Where each widget sits, as a share of League's window from its usual place, and its size. The overlay moves as you slide; dragging in Edit layout does the same."), ...widgetGroups, fitGroup, status);
    return section;
}
/** Draw the form, one switch for each preference, the layout, the friends list and Claude's take. */
export function renderSettings(root, preferences, friendRiotIds = [], claudeTake = null, layout = null) {
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
    root.replaceChildren(htmlElement("h1", "summary-result", "What the overlay shows"), htmlElement("p", "summary-detail", "Each change shows at once, and is kept for the next game."), form, status, ...(layout === null ? [] : [layoutElement(layout)]), friendsElement(friendRiotIds), ...(claudeTake === null ? [] : [claudeTakeElement(claudeTake)]));
}
async function start() {
    const root = document.getElementById("settings");
    if (root === null) {
        return;
    }
    try {
        const [response, friendsResponse, claudeResponse, layoutResponse] = await Promise.all([
            fetch("/preferences"),
            fetch("/friends"),
            fetch("/claude-take"),
            fetch("/layout"),
        ]);
        const preferences = response.ok ? await response.json() : null;
        const layout = layoutResponse.ok ? await layoutResponse.json() : null;
        const friends = friendsResponse.ok ? await friendsResponse.json() : null;
        const claudeTake = claudeResponse.ok ? await claudeResponse.json() : null;
        if (isOverlayPreferences(preferences)) {
            renderSettings(root, preferences, isFriendsList(friends) ? friends.riot_ids : [], isClaudeTakeAnswer(claudeTake) ? claudeTake : null, isOverlayLayout(layout) ? layout : null);
            return;
        }
    }
    catch {
        // Shown below: the engine is not running.
    }
    root.replaceChildren(htmlElement("h1", "summary-result", "Settings"), htmlElement("p", "summary-detail", "The engine is not running; start LeagueasyMode and open this page again."));
}
void start();
