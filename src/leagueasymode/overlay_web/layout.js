/**
 * Moving the widgets. In edit mode, which the macOS app turns on from its menu ("Edit layout"),
 * each movable widget is outlined and named, even an empty one, and can be dragged; where it is
 * dropped goes to the engine, which keeps it and sends it back with every state. Out of edit mode
 * the overlay lets clicks through to the game, and nothing moves.
 *
 * A widget's place is kept as shares of the overlay's width and height, so it stays put when the
 * overlay changes size, as when League's window does.
 */
import { MOVABLE_WIDGETS } from "./state.js";
const LAYOUT_PATH = "/layout";
// The header the server asks of a move, which a page elsewhere cannot send.
const REQUEST_HEADER = "X-LeagueasyMode-Request";
const REQUEST_VALUE = "layout";
const EDITING_CLASS = "editing-layout";
// Shares are kept to four decimals: a tenth of a point on the widest screens.
const SHARE_PRECISION = 10_000;
export const WIDGET_ELEMENT_IDS = {
    objective_strip: "objective-strip",
    callouts: "callouts",
    enemy_strip: "enemy-strip",
    you_panel: "you-panel",
};
const WIDGET_TITLES = {
    objective_strip: "Objectives",
    callouts: "Callouts",
    enemy_strip: "Enemy strip",
    you_panel: "You panel",
};
const USUAL_PLACE = { x_share: 0, y_share: 0 };
let currentOffsets = {};
let draggedWidget = null;
function shareOf(value) {
    return Math.round(Math.min(1, Math.max(-1, value)) * SHARE_PRECISION) / SHARE_PRECISION;
}
function placeWidget(widget, offset) {
    const element = document.getElementById(WIDGET_ELEMENT_IDS[widget]);
    if (element === null) {
        return;
    }
    const isUsualPlace = offset.x_share === 0 && offset.y_share === 0;
    element.style.translate = isUsualPlace
        ? ""
        : `${String(offset.x_share * 100)}vw ${String(offset.y_share * 100)}vh`;
}
/** Put each widget where the layout says, but the one being dragged. */
export function applyLayout(layout) {
    currentOffsets = { ...layout.offsets };
    for (const widget of MOVABLE_WIDGETS) {
        if (widget !== draggedWidget) {
            placeWidget(widget, layout.offsets[widget] ?? USUAL_PLACE);
        }
    }
}
async function saveLayout(layout) {
    try {
        await fetch(LAYOUT_PATH, {
            method: "PUT",
            headers: { "Content-Type": "application/json", [REQUEST_HEADER]: REQUEST_VALUE },
            body: JSON.stringify(layout),
        });
    }
    catch {
        // The engine has stopped; the widget stays where it was dropped until the page reloads.
    }
}
export function isEditingLayout() {
    return document.body.classList.contains(EDITING_CLASS);
}
function setEditing(isEditing) {
    document.body.classList.toggle(EDITING_CLASS, isEditing);
}
function resetLayout() {
    applyLayout({ offsets: {} });
    void saveLayout({ offsets: {} });
}
/** Let a widget be dragged while editing. */
function makeMovable(widget, element) {
    element.dataset["movable"] = WIDGET_TITLES[widget];
    element.addEventListener("pointerdown", (downEvent) => {
        if (!isEditingLayout() || downEvent.button !== 0) {
            return;
        }
        downEvent.preventDefault();
        element.setPointerCapture(downEvent.pointerId);
        const startOffset = currentOffsets[widget] ?? USUAL_PLACE;
        let movedOffset = startOffset;
        draggedWidget = widget;
        const move = (moveEvent) => {
            movedOffset = {
                x_share: shareOf(startOffset.x_share + (moveEvent.clientX - downEvent.clientX) / window.innerWidth),
                y_share: shareOf(startOffset.y_share + (moveEvent.clientY - downEvent.clientY) / window.innerHeight),
            };
            placeWidget(widget, movedOffset);
        };
        const drop = () => {
            element.removeEventListener("pointermove", move);
            element.removeEventListener("pointerup", drop);
            element.removeEventListener("pointercancel", drop);
            draggedWidget = null;
            currentOffsets = { ...currentOffsets, [widget]: movedOffset };
            void saveLayout({ offsets: currentOffsets });
        };
        element.addEventListener("pointermove", move);
        element.addEventListener("pointerup", drop);
        element.addEventListener("pointercancel", drop);
    });
}
/** Make the widgets movable, add edit mode's notice, and let the macOS app turn edit mode on. */
export function startLayoutEditing() {
    for (const widget of MOVABLE_WIDGETS) {
        const element = document.getElementById(WIDGET_ELEMENT_IDS[widget]);
        if (element !== null) {
            makeMovable(widget, element);
        }
    }
    const notice = document.createElement("div");
    notice.className = "layout-editor";
    const noticeText = document.createElement("span");
    noticeText.textContent = "Drag a widget to move it. Choose Edit layout in the menu again when done.";
    const resetButton = document.createElement("button");
    resetButton.type = "button";
    resetButton.textContent = "Reset layout";
    resetButton.addEventListener("click", resetLayout);
    notice.append(noticeText, resetButton);
    document.body.append(notice);
    window.leagueasymodeSetEditing = setEditing;
    window.leagueasymodeResetLayout = resetLayout;
}
