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
  if (isEditing) {
    drawHudRegions();
  }
}

/** A part of League's own HUD, as shares of its window: left, top, right and bottom edges. */
interface HudRegion {
  readonly name: string;
  readonly left: number;
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
}

// League's HUD at its default size, as shares of the window (layout slice L.3): a first guess,
// seen against a 1920 × 925 window, to be checked on the Mac. The minimap is worked out from the
// minimap layer, which sits on it.
const FIXED_HUD_REGIONS: readonly HudRegion[] = [
  { name: "Score", left: 0.8, top: 0, right: 1, bottom: 0.045 },
  { name: "Kill feed", left: 0.84, top: 0.05, right: 1, bottom: 0.3 },
  { name: "Champion bar", left: 0.3, top: 0.83, right: 0.7, bottom: 1 },
  { name: "Chat", left: 0, top: 0.64, right: 0.25, bottom: 0.83 },
  { name: "Ally portraits", left: 0, top: 0.2, right: 0.045, bottom: 0.55 },
];
// The minimap layer's side at League's scale 1, a share of the window's height (overlay.css).
const MINIMAP_HEIGHT_SHARE = 0.22;
// How many times a dropped widget is moved off a region; a move can land it on another.
const MOST_HUD_MOVES = 4;
// The gap left between a moved widget and the region it was moved off, in pixels.
const HUD_GAP_PIXELS = 4;

/** Return League's HUD regions in this window: the fixed ones and the minimap. */
function hudRegions(): HudRegion[] {
  const minimap = document.getElementById("minimap");
  const style = minimap === null ? null : getComputedStyle(minimap);
  const leagueScale = Number(style?.getPropertyValue("--minimap-scale") ?? "") || 1;
  const fitScale = Number(style?.getPropertyValue("--minimap-fit") ?? "") || 1;
  const heightShare = MINIMAP_HEIGHT_SHARE * leagueScale * fitScale;
  const widthShare = (heightShare * window.innerHeight) / window.innerWidth;
  const isLeft = minimap?.dataset["side"] === "left";
  return [
    ...FIXED_HUD_REGIONS,
    {
      name: "Minimap",
      left: isLeft ? 0 : 1 - widthShare,
      top: 1 - heightShare,
      right: isLeft ? widthShare : 1,
      bottom: 1,
    },
  ];
}

/** Shade and name League's HUD regions, for edit mode: what a widget dropped there would cover. */
function drawHudRegions(): void {
  let layer = document.getElementById("hud-regions");
  if (layer === null) {
    layer = document.createElement("div");
    layer.id = "hud-regions";
    layer.setAttribute("aria-hidden", "true");
    document.body.prepend(layer);
  }
  layer.replaceChildren(
    ...hudRegions().map((region) => {
      const shade = document.createElement("div");
      shade.className = "hud-region";
      shade.textContent = region.name;
      shade.style.left = `${String(region.left * 100)}vw`;
      shade.style.top = `${String(region.top * 100)}vh`;
      shade.style.width = `${String((region.right - region.left) * 100)}vw`;
      shade.style.height = `${String((region.bottom - region.top) * 100)}vh`;
      return shade;
    }),
  );
}

/**
 * Return what a widget covers: its own box, or for the strips that span the window's width, the
 * box of what they hold, which is all that shows; null when nothing shows.
 */
function coveredBox(element: HTMLElement): DOMRect | null {
  if (element.id !== WIDGET_ELEMENT_IDS.objective_strip && element.id !== WIDGET_ELEMENT_IDS.callouts) {
    return element.getBoundingClientRect();
  }
  const boxes = [...element.children]
    .map((child) => child.getBoundingClientRect())
    .filter((box) => box.width > 0 && box.height > 0);
  if (boxes.length === 0) {
    return null;
  }
  const left = Math.min(...boxes.map((box) => box.left));
  const top = Math.min(...boxes.map((box) => box.top));
  const right = Math.max(...boxes.map((box) => box.right));
  const bottom = Math.max(...boxes.map((box) => box.bottom));
  return new DOMRect(left, top, right - left, bottom - top);
}

/**
 * Return how far, in pixels, to move a box so that it covers no HUD region and stays in the
 * window: the shortest way off each region it lands on, then back inside the window's edges.
 */
export function moveOffHud(box: DOMRect, regions: readonly HudRegion[], width: number, height: number): [number, number] {
  let right = 0;
  let down = 0;
  for (let move = 0; move < MOST_HUD_MOVES; move += 1) {
    const left = box.left + right;
    const top = box.top + down;
    const covered = regions.find(
      (region) =>
        left < region.right * width &&
        left + box.width > region.left * width &&
        top < region.bottom * height &&
        top + box.height > region.top * height,
    );
    if (covered === undefined) {
      break;
    }
    const ways: [number, number][] = [
      [covered.left * width - (left + box.width) - HUD_GAP_PIXELS, 0],
      [covered.right * width - left + HUD_GAP_PIXELS, 0],
      [0, covered.top * height - (top + box.height) - HUD_GAP_PIXELS],
      [0, covered.bottom * height - top + HUD_GAP_PIXELS],
    ];
    const inside = ways.filter(
      ([wayRight, wayDown]) =>
        left + wayRight >= 0 &&
        left + wayRight + box.width <= width &&
        top + wayDown >= 0 &&
        top + wayDown + box.height <= height,
    );
    const shortest = (inside.length > 0 ? inside : ways).reduce((best, way) =>
      Math.abs(way[0]) + Math.abs(way[1]) < Math.abs(best[0]) + Math.abs(best[1]) ? way : best,
    );
    right += shortest[0];
    down += shortest[1];
  }
  // Never outside the window, whatever the regions.
  const left = box.left + right;
  const top = box.top + down;
  right += Math.max(0, -left) - Math.max(0, left + box.width - width);
  down += Math.max(0, -top) - Math.max(0, top + box.height - height);
  return [right, down];
}

/** Move a dropped widget off League's HUD and into the window, and return its new place. */
function settleOffHud(widget: MovableWidget, element: HTMLElement, offset: WidgetOffset): WidgetOffset {
  const box = coveredBox(element);
  if (box === null) {
    return offset;
  }
  const [right, down] = moveOffHud(box, hudRegions(), window.innerWidth, window.innerHeight);
  if (right === 0 && down === 0) {
    return offset;
  }
  const settled = {
    x_share: shareOf(offset.x_share + right / window.innerWidth),
    y_share: shareOf(offset.y_share + down / window.innerHeight),
  };
  placeWidget(widget, settled);
  return settled;
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
      }
      // Dropped on League's HUD, or grown over it, the widget moves just off it (the owner:
      // "move them off automatically").
      const settledOffset = settleOffHud(widget, element, isResizing ? startOffset : movedOffset);
      const { [widget]: _previousOffset, ...otherOffsets } = currentOffsets;
      const isUsualPlace = settledOffset.x_share === 0 && settledOffset.y_share === 0;
      // A resize that leaves the widget in its usual place keeps no offset for it, as before.
      currentOffsets =
        isResizing && isUsualPlace ? otherOffsets : { ...otherOffsets, [widget]: settledOffset };
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
