/**
 * The case file in the post-game window (phase 11.3): the last game's verdict, its lane board,
 * the lines with their exhibits, and the closing line to paste. The player picks whom it roasts
 * (the whole team, the enemy team, a lane, or any one of the ten players), the spice, "Prove it",
 * and another take; each pick asks `/case` again. Nothing here sends anything to chat.
 */
import { DEFAULT_CHOICE, casePath, isCaseView, } from "./case_state.js";
// The spice levels, as `leagueasymode.roast.case_view.SPICE_NAMES` names them.
const SPICE_LEVELS = [
    [1, "Honor-eligible"],
    [2, "Salty"],
    [3, "Tilted"],
    [4, "Chat-Restricted Speedrun"],
];
const LANES = [
    ["TOP", "Top"],
    ["JUNGLE", "Jungle"],
    ["MIDDLE", "Mid"],
    ["BOTTOM", "Bot"],
    ["UTILITY", "Support"],
];
const OUTCOME_NAMES = {
    won: "won",
    even: "even",
    lost: "lost",
    gap: "gap",
};
const SOURCE_NAMES = {
    game: "the game's details",
    timeline: "the timeline",
    live: "the live game",
    computation: "worked out here",
};
// How soon the window asks again while Claude's take is being written.
const CLAUDE_TAKE_RECHECK_MILLISECONDS = 1500;
// How soon the window asks again while the case is the quick one, for the full case.
const QUICK_CASE_RECHECK_MILLISECONDS = 15000;
// How long a copy button says "Copied".
const COPIED_MILLISECONDS = 2000;
const QUICK_CASE_TEXT = "A quick case from the end-of-game scoreboard. The full case, with the lanes, replaces it when the match timeline comes.";
const NO_CASE_TEXT = "No case for this game: its details have not come yet, or it was not two teams of five.";
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
/** Return a target's chip text for a player: their champion, "(you)" for the defendant, ★ for a friend. */
export function playerChipText(player) {
    const champion = player.is_friend ? `${player.champion} ★` : player.champion;
    return player.is_defendant ? `${champion} (you)` : champion;
}
/** A chip for one value of a choice: a target ("data-target") or a spice level ("data-spice"). */
function chipElement(text, choiceName, value, onPress) {
    const chip = htmlElement("button", "case-chip", text);
    chip.type = "button";
    chip.dataset[choiceName] = value;
    chip.setAttribute("aria-pressed", "false");
    chip.addEventListener("click", onPress);
    return chip;
}
function chipRowElement(label, chips) {
    const row = htmlElement("div", "case-chip-row");
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", label);
    row.append(htmlElement("span", "case-chip-label", label), ...chips);
    return row;
}
function lineElement(line, openExhibits) {
    const item = htmlElement("li", "");
    for (const part of line.parts) {
        if (part.letter === null) {
            item.append(document.createTextNode(part.text));
            continue;
        }
        item.append(htmlElement("span", "case-cited", part.text), letterElement(part.letter, openExhibits));
    }
    return item;
}
function letterElement(letter, openExhibits) {
    const link = htmlElement("a", "case-letter", letter);
    link.href = `#case-exhibit-${letter}`;
    link.setAttribute("aria-label", `Exhibit ${letter}`);
    link.addEventListener("click", openExhibits);
    const superscript = htmlElement("sup", "");
    superscript.append(link);
    return superscript;
}
function goldCellElement(gold, letter, openExhibits) {
    const cell = htmlElement("td", "case-number", gold ?? "–");
    if (gold !== null && letter !== null) {
        cell.append(letterElement(letter, openExhibits));
    }
    return cell;
}
function boardElement(view, openExhibits) {
    const table = htmlElement("table", "case-board");
    const caption = htmlElement("caption", "", "Each lane against its opponent at 14:00, by our thresholds");
    const head = htmlElement("tr", "");
    for (const heading of ["Lane", "Ours", "Theirs", "Gold", "CS", "Outcome"]) {
        const cell = htmlElement("th", "", heading);
        cell.scope = "col";
        head.append(cell);
    }
    const rows = view.board.map((lane) => {
        const row = htmlElement("tr", "");
        row.dataset["outcome"] = lane.outcome;
        const laneName = LANES.find(([position]) => position === lane.position)?.[1] ?? lane.position;
        row.append(htmlElement("th", "", laneName), htmlElement("td", "", lane.ally_champion), htmlElement("td", "", lane.enemy_champion), goldCellElement(lane.gold_difference, lane.letter, openExhibits), htmlElement("td", "case-number", lane.cs_difference ?? "–"), htmlElement("td", "case-outcome", OUTCOME_NAMES[lane.outcome] ?? lane.outcome));
        return row;
    });
    table.append(caption, head, ...rows);
    return table;
}
function exhibitElement(exhibit) {
    const item = htmlElement("li", "case-exhibit");
    item.id = `case-exhibit-${exhibit.letter}`;
    const value = [exhibit.display, exhibit.unit].filter((part) => part !== "").join(" ");
    const source = htmlElement("span", "case-exhibit-source");
    source.append(document.createTextNode(`${SOURCE_NAMES[exhibit.source_kind] ?? exhibit.source_kind}: `), htmlElement("code", "", exhibit.source));
    item.append(htmlElement("span", "case-exhibit-letter", exhibit.letter), htmlElement("span", "case-exhibit-label", exhibit.label), htmlElement("span", "case-exhibit-value", value), source);
    return item;
}
function exhibitsElement(view) {
    const details = htmlElement("details", "case-exhibits");
    const cited = view.exhibits.filter((exhibit) => !exhibit.supporting);
    const supporting = view.exhibits.filter((exhibit) => exhibit.supporting);
    const list = htmlElement("ol", "case-exhibit-list");
    list.append(...cited.map(exhibitElement));
    details.append(htmlElement("summary", "", `Exhibits (${String(view.exhibits.length)})`), list);
    if (supporting.length > 0) {
        const fold = htmlElement("details", "case-supporting");
        const supportingList = htmlElement("ol", "case-exhibit-list");
        supportingList.append(...supporting.map(exhibitElement));
        fold.append(htmlElement("summary", "", `Supporting exhibits (${String(supporting.length)})`), supportingList);
        details.append(fold);
    }
    return details;
}
/** Draw Claude's take of the closing line (phase 11.8), or that it is being written; null when off. */
function claudeTakeElement(view) {
    if (view.claude_take === null && !view.claude_take_pending) {
        return null;
    }
    const take = htmlElement("figure", "case-claude-take");
    if (view.claude_take === null) {
        take.append(htmlElement("p", "case-claude-take-label", "Claude is rewording the closing line…"));
        return take;
    }
    take.append(htmlElement("p", "case-claude-take-label", "Claude's take · not one of your approved lines · ⌃⌥C copies this one"), htmlElement("blockquote", "case-closing-line", view.claude_take), htmlElement("figcaption", "case-closing-caption", `${String(view.claude_take.length)} / ${String(view.closing_line_limit)} characters`));
    return take;
}
/** Draw the case's verdict, board, lines, closing line and exhibits. */
/** A button that copies a line for chat, to paste with ⌘V; it says when it has. */
function copyButtonElement(line) {
    const button = htmlElement("button", "case-copy", "Copy");
    button.type = "button";
    button.setAttribute("aria-label", `Copy: ${line}`);
    button.addEventListener("click", () => {
        void copyText(line).then((isCopied) => {
            button.textContent = isCopied ? "Copied" : "Select it to copy";
            window.setTimeout(() => {
                button.textContent = "Copy";
            }, COPIED_MILLISECONDS);
        });
    });
    return button;
}
/** Copies text to the clipboard; false when the browser refuses. */
async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    }
    catch {
        return false;
    }
}
export function renderCaseBody(body, view) {
    const verdict = htmlElement("div", "case-verdict");
    verdict.dataset["acquitted"] = String(view.acquitted);
    verdict.append(htmlElement("p", "case-stamp", view.verdict_title), htmlElement("p", "case-verdict-summary", view.verdict_summary));
    const exhibits = exhibitsElement(view);
    const openExhibits = () => {
        exhibits.open = true;
        for (const fold of exhibits.querySelectorAll("details")) {
            fold.open = true;
        }
    };
    const lines = htmlElement("ol", "case-lines");
    lines.append(...view.lines.map((line) => lineElement(line, openExhibits)));
    const closing = htmlElement("figure", "case-closing");
    closing.append(htmlElement("blockquote", "case-closing-line", view.closing_line), copyButtonElement(view.closing_line), htmlElement("figcaption", "case-closing-caption", `${String(view.closing_line.length)} / ${String(view.closing_line_limit)} characters · paste it yourself; nothing is sent to chat`));
    const otherOptions = view.closing_options.slice(1);
    if (otherOptions.length > 0) {
        const options = htmlElement("ul", "case-options");
        options.setAttribute("aria-label", "More lines for chat");
        options.append(...otherOptions.map((option) => {
            const item = htmlElement("li", "case-option");
            item.append(htmlElement("span", "case-option-line", option), copyButtonElement(option));
            return item;
        }));
        closing.append(options);
    }
    const parts = view.is_quick ? [htmlElement("p", "case-quick", QUICK_CASE_TEXT), verdict] : [verdict];
    const claudeTake = claudeTakeElement(view);
    if (view.board.length > 0) {
        parts.push(boardElement(view, openExhibits));
    }
    parts.push(view.lines.length > 0 ? lines : htmlElement("p", "case-empty", "No line fits this target."), closing);
    if (claudeTake !== null) {
        parts.push(claudeTake);
    }
    if (view.risk_warning !== null) {
        const warning = htmlElement("p", "case-risk", view.risk_warning);
        warning.setAttribute("role", "note");
        parts.push(warning);
    }
    parts.push(exhibits);
    body.replaceChildren(...parts);
}
/** The case section: its controls are drawn once, from the first case; each pick redraws the body. */
export function caseSectionElement(fetchCase) {
    const section = htmlElement("section", "summary-section case-file");
    const controls = htmlElement("div", "case-controls");
    const body = htmlElement("div", "case-body");
    body.setAttribute("aria-live", "polite");
    section.append(htmlElement("h2", "", "The case"), controls, body);
    let choice = DEFAULT_CHOICE;
    let latestRequest = 0;
    let hasControls = false;
    const choose = (change) => {
        const isNewTake = change.take !== undefined;
        choice = { ...choice, ...change, take: isNewTake ? (change.take ?? 0) : 0 };
        void load();
    };
    const drawControls = (view) => {
        const targetChip = (text, target) => chipElement(text, "target", target, () => {
            choose({ target });
        });
        const playerChips = (side) => view.players
            .filter((player) => player.side === side)
            .map((player) => targetChip(playerChipText(player), `player:${String(player.participant_id)}`));
        const prove = htmlElement("input", "");
        prove.type = "checkbox";
        prove.checked = choice.prove;
        prove.addEventListener("change", () => {
            choose({ prove: prove.checked });
        });
        const proveLabel = htmlElement("label", "case-prove");
        proveLabel.append(prove, document.createTextNode(" Prove it: each against their lane opponent"));
        const anotherTake = htmlElement("button", "case-take", "Another take");
        anotherTake.type = "button";
        anotherTake.addEventListener("click", () => {
            choose({ take: choice.take + 1 });
        });
        const actions = htmlElement("div", "case-actions");
        actions.append(proveLabel, anotherTake);
        controls.replaceChildren(chipRowElement("Roast", [targetChip("Our team", "team"), targetChip("Their team", "enemy")]), chipRowElement("Lane", LANES.map(([position, name]) => targetChip(name, `lane:${position}`))), chipRowElement("Ours", playerChips("ally")), chipRowElement("Theirs", playerChips("enemy")), chipRowElement("Spice", SPICE_LEVELS.map(([level, name]) => chipElement(`${String(level)} ${name}`, "spice", String(level), () => {
            choose({ spice: level });
        }))), actions);
        hasControls = true;
    };
    const markChoice = () => {
        for (const chip of controls.querySelectorAll(".case-chip")) {
            const isPressed = chip.dataset["target"] === choice.target || chip.dataset["spice"] === String(choice.spice);
            chip.setAttribute("aria-pressed", String(isPressed));
        }
    };
    const load = async () => {
        const request = ++latestRequest;
        const answer = await fetchCase(casePath(choice));
        if (request !== latestRequest) {
            return;
        }
        if (!isCaseView(answer)) {
            body.replaceChildren(htmlElement("p", "case-empty", hasControls ? "Could not build this case." : NO_CASE_TEXT));
            return;
        }
        if (!hasControls) {
            drawControls(answer);
        }
        markChoice();
        renderCaseBody(body, answer);
        // Ask again for the same choice until Claude's take arrives, or the full case replaces the
        // quick one; a new pick replaces this.
        const recheckMilliseconds = answer.claude_take_pending
            ? CLAUDE_TAKE_RECHECK_MILLISECONDS
            : answer.is_quick
                ? QUICK_CASE_RECHECK_MILLISECONDS
                : null;
        if (recheckMilliseconds !== null) {
            window.setTimeout(() => {
                if (request === latestRequest) {
                    void load();
                }
            }, recheckMilliseconds);
        }
    };
    void load();
    return section;
}
