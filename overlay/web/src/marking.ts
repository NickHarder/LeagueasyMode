/**
 * Marking a spell with a click, the "Click to mark spells" setting. Each enemy's row gets a button
 * for their Flash, their other summoner spell and their ultimate; a press posts the mark to the
 * engine as the app's ⌃⌥ shortcuts do, naming the enemy by the same place in role order.
 *
 * The overlay lets every click through to the game. Inside the macOS app the page tells the app
 * where the buttons are (`ClickRegions` in the app), and the app takes the clicks on them only,
 * never the keyboard.
 */
import type { PlayerCard } from "./state.js";

export type MarkedSpell = "flash" | "summoner" | "ultimate";

const MARKS_PATH = "/marks";
const REQUEST_HEADER = "X-LeagueasyMode-Request";
const MARK_REQUEST_VALUE = "mark";
const BUTTON_CLASS = "mark-button";
const ULTIMATE_LABEL = "R";
// How long a pressed button shows it was taken, before the engine's timer replaces it.
const PRESSED_MILLISECONDS = 600;

/** Return the buttons that mark one enemy's spells, or null when the enemy has no place to mark. */
export function markButtonsElement(card: PlayerCard): HTMLElement | null {
  const enemySlot = card.enemy_slot;
  const [flashName, summonerName] = card.marked_spell_names;
  if (enemySlot === null || flashName === undefined || summonerName === undefined) {
    return null;
  }
  const buttons: [MarkedSpell, string, string][] = [
    ["flash", flashName, flashName],
    ["summoner", summonerName, summonerName],
    ["ultimate", ULTIMATE_LABEL, "Ultimate"],
  ];
  const element = document.createElement("span");
  element.className = "mark-buttons";
  element.replaceChildren(
    ...buttons.map(([spell, label, spellName]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = BUTTON_CLASS;
      button.dataset["enemySlot"] = String(enemySlot);
      button.dataset["spell"] = spell;
      button.textContent = label;
      button.title = `${card.champion_name} used ${spellName}`;
      return button;
    }),
  );
  return element;
}

/** Post a mark to the engine, as the app's shortcuts do. */
async function postMark(enemySlot: number, spell: MarkedSpell): Promise<void> {
  try {
    await fetch(MARKS_PATH, {
      method: "POST",
      headers: { "Content-Type": "application/json", [REQUEST_HEADER]: MARK_REQUEST_VALUE },
      body: JSON.stringify({ enemy_slot: enemySlot, spell }),
    });
  } catch {
    // The engine is away; the next state says nothing was marked.
  }
}

function isMarkedSpell(value: string | undefined): value is MarkedSpell {
  return value === "flash" || value === "summoner" || value === "ultimate";
}

/**
 * Mark on a press of any button in a container, which stays while its rows are drawn again: a
 * press counts as it happens, so a row drawn again before the button is let go loses nothing.
 */
export function listenForMarks(container: HTMLElement): void {
  container.addEventListener("pointerdown", (event) => {
    const target = event.target;
    const button = target instanceof Element ? target.closest<HTMLElement>(`.${BUTTON_CLASS}`) : null;
    if (button === null) {
      return;
    }
    event.preventDefault();
    const enemySlot = Number(button.dataset["enemySlot"]);
    const spell = button.dataset["spell"];
    if (!Number.isInteger(enemySlot) || !isMarkedSpell(spell)) {
      return;
    }
    button.dataset["pressed"] = "true";
    window.setTimeout(() => {
      delete button.dataset["pressed"];
    }, PRESSED_MILLISECONDS);
    void postMark(enemySlot, spell);
  });
}

let lastReportedRegions = "";

/**
 * Tell the app where the buttons are, in the page's points from its top left, when that changed;
 * an empty list when there are none, so that the app takes no click at all.
 */
export function reportClickRegions(): void {
  const appHandler = window.webkit?.messageHandlers?.leagueasymodeClickRegions;
  if (appHandler === undefined) {
    return;
  }
  const regions = [...document.querySelectorAll<HTMLElement>(`.${BUTTON_CLASS}`)]
    .map((button) => button.getBoundingClientRect())
    .filter((rectangle) => rectangle.width > 0 && rectangle.height > 0)
    .map((rectangle) => [
      Math.round(rectangle.left),
      Math.round(rectangle.top),
      Math.round(rectangle.width),
      Math.round(rectangle.height),
    ]);
  const regionsText = JSON.stringify(regions);
  if (regionsText === lastReportedRegions) {
    return;
  }
  lastReportedRegions = regionsText;
  appHandler.postMessage(regionsText);
}
