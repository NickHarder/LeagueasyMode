/**
 * Moving and sizing the widgets. In edit mode, which the macOS app turns on from its menu ("Edit
 * layout"), each movable widget is outlined and named, even an empty one, and can be dragged; its
 * bottom right corner is a handle that resizes it, as does the scroll wheel over it. Where it is
 * dropped and how big it is go to the engine, which keeps them and sends them back with every
 * state. Escape, the show/hide shortcut or two minutes end it. Out of edit mode the overlay lets
 * every click through to the game, and nothing moves.
 *
 * A widget's place is kept as shares of the overlay's width and height, so it stays put when the
 * overlay changes size, as when League's window does; its size as a share of its usual size.
 */

import {
  MAX_WIDGET_SCALE,
  MIN_WIDGET_SCALE,
  MOVABLE_WIDGETS,
  type MinimapFit,
  type MovableWidget,
  type OverlayLayout,
  type WidgetOffset,
} from "./state.js";

const LAYOUT_PATH = "/layout";
// The header the server asks of a move, which a page elsewhere cannot send.
const REQUEST_HEADER = "X-LeagueasyMode-Request";
const REQUEST_VALUE = "layout";
const EDITING_CLASS = "editing-layout";
// Shares are kept to four decimals: a tenth of a point on the widest screens.
const SHARE_PRECISION = 10_000;
// Sizes are kept to whole points.
const SCALE_PRECISION = 100;
const USUAL_SCALE = 1;
// The handle: this close to a widget's bottom right corner, a drag resizes instead of moving.
const HANDLE_PIXELS = 14;
// Dragging the handle 50 pixels out, right and down together, makes the widget a fifth bigger.
const SCALE_PER_PIXEL = 1 / 250;
// One step of the scroll wheel is 5 points of size.
const SCALE_PER_WHEEL_STEP = 0.05;
// A size set with the wheel is kept once the wheel rests this long.
const WHEEL_SAVE_DELAY_MILLISECONDS = 300;

export const WIDGET_ELEMENT_IDS: Readonly<Record<MovableWidget, string>> = {
  objective_strip: "objective-strip",
  callouts: "callouts",
  enemy_strip: "enemy-strip",
  you_panel: "you-panel",
};

export const WIDGET_TITLES: Readonly<Record<MovableWidget, string>> = {
  objective_strip: "Objectives",
  callouts: "Callouts",
  enemy_strip: "Enemy strip",
  you_panel: "You panel",
};

const USUAL_PLACE: WidgetOffset = { x_share: 0, y_share: 0 };
export const USUAL_MINIMAP_FIT: MinimapFit = { scale: 1, x_share: 0, y_share: 0 };

declare global {
  interface Window {
    /** Called by the macOS app when "Edit layout" is turned on or off. */
    leagueasymodeSetEditing?: (isEditing: boolean) => void;
    /** Called by the macOS app's "Reset layout": every widget back in its usual place. */
    leagueasymodeResetLayout?: () => void;
  }
}

let currentOffsets: Partial<Record<MovableWidget, WidgetOffset>> = {};
let currentScales: Partial<Record<MovableWidget, number>> = {};
let currentMinimapFit: MinimapFit = USUAL_MINIMAP_FIT;
let currentOpacity = 1;
let currentHidden: readonly MovableWidget[] = [];
let draggedWidget: MovableWidget | null = null;
let wheelSaveTimer: number | undefined;

function shareOf(value: number): number {
  return Math.round(Math.min(1, Math.max(-1, value)) * SHARE_PRECISION) / SHARE_PRECISION;
}

function scaleOf(value: number): number {
  return Math.round(Math.min(MAX_WIDGET_SCALE, Math.max(MIN_WIDGET_SCALE, value)) * SCALE_PRECISION) / SCALE_PRECISION;
}

function currentLayout(): OverlayLayout {
  return { offsets: currentOffsets, scales: currentScales, minimap_fit: currentMinimapFit, opacity: currentOpacity, hidden: currentHidden };
}

function placeWidget(widget: MovableWidget, offset: WidgetOffset): void {
  const element = document.getElementById(WIDGET_ELEMENT_IDS[widget]);
  if (element === null) {
    return;
  }
  const isUsualPlace = offset.x_share === 0 && offset.y_share === 0;
  element.style.translate = isUsualPlace
    ? ""
    : `${String(offset.x_share * 100)}vw ${String(offset.y_share * 100)}vh`;
}

/** Size a widget, and say its size in its name while editing: "You panel · 120%". */
function sizeWidget(widget: MovableWidget, scale: number): void {
  const element = document.getElementById(WIDGET_ELEMENT_IDS[widget]);
  if (element === null) {
    return;
  }
  const isUsualSize = scale === USUAL_SCALE;
  element.style.scale = isUsualSize ? "" : String(scale);
  element.dataset["movable"] = isUsualSize
    ? WIDGET_TITLES[widget]
    : `${WIDGET_TITLES[widget]} · ${String(Math.round(scale * 100))}%`;
}

/** Fit the minimap layer to League's minimap: its size beside League's, and a nudge. */
function fitMinimap(fit: MinimapFit): void {
  const minimap = document.getElementById("minimap");
  if (minimap === null) {
    return;
  }
  minimap.style.setProperty("--minimap-fit", String(fit.scale));
  const isUsualPlace = fit.x_share === 0 && fit.y_share === 0;
  minimap.style.translate = isUsualPlace ? "" : `${String(fit.x_share * 100)}vw ${String(fit.y_share * 100)}vh`;
}

/** Put each widget where the layout says, at the size it says, but the one being dragged. */
export function applyLayout(layout: OverlayLayout): void {
  currentOffsets = { ...layout.offsets };
  currentScales = { ...layout.scales };
  currentMinimapFit = layout.minimap_fit;
  currentOpacity = layout.opacity;
  currentHidden = layout.hidden;
  for (const widget of MOVABLE_WIDGETS) {
    showOrHide(widget, layout.hidden.includes(widget));
  }
  fitMinimap(layout.minimap_fit);
  // The widgets' backgrounds and borders fade; their text does not (overlay.css).
  document.documentElement.style.setProperty("--overlay-opacity", String(layout.opacity));
  for (const widget of MOVABLE_WIDGETS) {
    if (widget !== draggedWidget) {
      placeWidget(widget, layout.offsets[widget] ?? USUAL_PLACE);
      sizeWidget(widget, layout.scales[widget] ?? USUAL_SCALE);
    }
  }
}

async function saveLayout(layout: OverlayLayout): Promise<void> {
  try {
    await fetch(LAYOUT_PATH, {
      method: "PUT",
      headers: { "Content-Type": "application/json", [REQUEST_HEADER]: REQUEST_VALUE },
      body: JSON.stringify(layout),
    });
  } catch {
    // The engine has stopped; the widget stays where it was dropped until the page reloads.
  }
}

export function isEditingLayout(): boolean {
  return document.body.classList.contains(EDITING_CLASS);
}

function setEditing(isEditing: boolean): void {
  document.body.classList.toggle(EDITING_CLASS, isEditing);
}

/** Put every widget back; the minimap layer's fit and the opacity, which are no widget's place, stay. */
function resetLayout(): void {
  const usualLayout: OverlayLayout = {
    offsets: {},
    scales: {},
    minimap_fit: currentMinimapFit,
    opacity: currentOpacity,
    hidden: currentHidden,
  };
  applyLayout(usualLayout);
  void saveLayout(usualLayout);
}

/**
 * Turn a widget off or on (layout slice L.5): off, it never shows over the game; in edit mode it
 * stays in sight, faded, and the notice's button for it says "Show" instead of "Hide".
 */
function showOrHide(widget: MovableWidget, isHidden: boolean): void {
  const element = document.getElementById(WIDGET_ELEMENT_IDS[widget]);
  if (element !== null) {
    if (isHidden) {
      element.dataset["layoutHidden"] = "true";
    } else {
      delete element.dataset["layoutHidden"];
    }
  }
  const toggle = document.querySelector<HTMLButtonElement>(`.layout-editor [data-widget="${widget}"]`);
  if (toggle !== null) {
    toggle.textContent = `${isHidden ? "Show" : "Hide"} ${WIDGET_TITLES[widget]}`;
  }
}

/** Turn a widget off, or on again, and keep that. */
function toggleHidden(widget: MovableWidget): void {
  const isHidden = !currentHidden.includes(widget);
  currentHidden = isHidden
    ? [...currentHidden, widget]
    : currentHidden.filter((hiddenWidget) => hiddenWidget !== widget);
  showOrHide(widget, isHidden);
  void saveLayout(currentLayout());
}

/** Return whether a point is on a widget's handle, its bottom right corner. */
function isOnHandle(element: HTMLElement, clientX: number, clientY: number): boolean {
  const bounds = element.getBoundingClientRect();
  return clientX >= bounds.right - HANDLE_PIXELS && clientY >= bounds.bottom - HANDLE_PIXELS;
}

/** Keep a widget's new size, without the one it had at its usual size. */
function withScale(widget: MovableWidget, scale: number): Partial<Record<MovableWidget, number>> {
  const { [widget]: _previous, ...otherScales } = currentScales;
  return scale === USUAL_SCALE ? otherScales : { ...otherScales, [widget]: scale };
}

/** Let a widget be dragged, and resized by its handle or the wheel, while editing. */
function makeMovable(widget: MovableWidget, element: HTMLElement): void {
  sizeWidget(widget, currentScales[widget] ?? USUAL_SCALE);
  element.addEventListener("pointerdown", (downEvent: PointerEvent) => {
    if (!isEditingLayout() || downEvent.button !== 0) {
      return;
    }
    downEvent.preventDefault();
    element.setPointerCapture(downEvent.pointerId);
    const isResizing = isOnHandle(element, downEvent.clientX, downEvent.clientY);
    const startOffset = currentOffsets[widget] ?? USUAL_PLACE;
    const startScale = currentScales[widget] ?? USUAL_SCALE;
    let movedOffset = startOffset;
    let resizedScale = startScale;
    draggedWidget = widget;
    const move = (moveEvent: PointerEvent): void => {
      const right = moveEvent.clientX - downEvent.clientX;
      const down = moveEvent.clientY - downEvent.clientY;
      if (isResizing) {
        resizedScale = scaleOf(startScale + (right + down) * SCALE_PER_PIXEL);
        sizeWidget(widget, resizedScale);
        return;
      }
      movedOffset = {
        x_share: shareOf(startOffset.x_share + right / window.innerWidth),
        y_share: shareOf(startOffset.y_share + down / window.innerHeight),
      };
      placeWidget(widget, movedOffset);
    };
    const drop = (): void => {
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", drop);
      element.removeEventListener("pointercancel", drop);
      draggedWidget = null;
      if (isResizing) {
        currentScales = withScale(widget, resizedScale);
      } else {
        currentOffsets = { ...currentOffsets, [widget]: movedOffset };
      }
      void saveLayout(currentLayout());
    };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", drop);
    element.addEventListener("pointercancel", drop);
  });
  element.addEventListener("wheel", (wheelEvent: WheelEvent) => {
    if (!isEditingLayout() || wheelEvent.deltaY === 0) {
      return;
    }
    wheelEvent.preventDefault();
    const step = wheelEvent.deltaY < 0 ? SCALE_PER_WHEEL_STEP : -SCALE_PER_WHEEL_STEP;
    const scale = scaleOf((currentScales[widget] ?? USUAL_SCALE) + step);
    currentScales = withScale(widget, scale);
    sizeWidget(widget, scale);
    window.clearTimeout(wheelSaveTimer);
    wheelSaveTimer = window.setTimeout(() => void saveLayout(currentLayout()), WHEEL_SAVE_DELAY_MILLISECONDS);
  });
}

/** Make the widgets movable, add edit mode's notice, and let the macOS app turn edit mode on. */
export function startLayoutEditing(): void {
  for (const widget of MOVABLE_WIDGETS) {
    const element = document.getElementById(WIDGET_ELEMENT_IDS[widget]);
    if (element !== null) {
      makeMovable(widget, element);
    }
  }
  const notice = document.createElement("div");
  notice.className = "layout-editor";
  const noticeText = document.createElement("span");
  noticeText.textContent =
    "Drag a widget to move it; drag its corner or scroll over it to resize it. Press Esc when done; editing ends by itself after 2 minutes.";
  const resetButton = document.createElement("button");
  resetButton.type = "button";
  resetButton.textContent = "Reset layout";
  resetButton.addEventListener("click", resetLayout);
  const toggles = MOVABLE_WIDGETS.map((widget) => {
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.dataset["widget"] = widget;
    toggle.textContent = `Hide ${WIDGET_TITLES[widget]}`;
    toggle.addEventListener("click", () => {
      toggleHidden(widget);
    });
    return toggle;
  });
  notice.append(noticeText, resetButton, ...toggles);
  document.body.append(notice);
  window.leagueasymodeSetEditing = setEditing;
  window.leagueasymodeResetLayout = resetLayout;
}
