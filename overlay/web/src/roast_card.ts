/**
 * The roast card: after a game, three lines for chat on the overlay, each about a different target,
 * at a spice level picked on the card (the owner, 2026-10-29: the post-game window's options were
 * "overwhelming", and "can it be done through the overlay"). A click copies a line, for the player
 * to paste; nothing is sent to chat.
 *
 * It shows only after the page saw a game end, and only a case kept after that, so an older game's
 * case never shows; it goes when the player closes it or the next game starts. The quick case's
 * lines are asked for again until the full case replaces them. Inside the macOS app the app copies
 * the line and says so in its toast (`PickedRoastLine`); in a browser the clipboard takes it.
 */

/** The class of an element the app takes clicks on, the overlay letting every other through. */
export const TAKES_CLICKS_CLASS = "takes-clicks";

const SUGGESTIONS_PATH = "/roast-suggestions";
// Asked for this often until the game's case is kept, for this long at most.
const WAITING_MILLISECONDS = 5000;
const LONGEST_WAIT_MILLISECONDS = 10 * 60 * 1000;
// A quick case's lines are asked for again this often, until the full case replaces them.
const QUICK_CASE_MILLISECONDS = 15000;
// A case kept this long before the page saw the game end is still this game's: the clocks agree to
// within it.
const KEPT_BEFORE_THE_END_SECONDS = 5;
const COPIED_MILLISECONDS = 2000;
const MILLISECONDS_PER_SECOND = 1000;
const SPICE_NAMES: readonly string[] = ["Honor-eligible", "Salty", "Tilted", "Chat-Restricted Speedrun"];
const DEFAULT_SPICE = 2;

interface RoastSuggestions {
  readonly kept_at_seconds: number;
  readonly spice: number;
  readonly is_quick: boolean;
  readonly lines: readonly string[];
}

function isRoastSuggestions(value: unknown): value is RoastSuggestions {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const record = value as Record<string, unknown>;
  const lines = record["lines"];
  return (
    typeof record["kept_at_seconds"] === "number" &&
    typeof record["spice"] === "number" &&
    typeof record["is_quick"] === "boolean" &&
    Array.isArray(lines) &&
    lines.every((line) => typeof line === "string")
  );
}

let wasGameRunning = false;
// When the page saw the last game end, in seconds since the epoch; null once the card is closed.
let gameEndedAtSeconds: number | null = null;
let gameEndedAtMilliseconds = 0;
let suggestions: RoastSuggestions | null = null;
let spice = DEFAULT_SPICE;
let copiedLine: string | null = null;
let askTimer: number | null = null;
let drawnText = "";

/** Follow the game: the card opens when it ends and closes when the next starts. */
export function updateRoastCard(isGameRunning: boolean): void {
  if (isGameRunning) {
    wasGameRunning = true;
    closeCard();
    return;
  }
  if (wasGameRunning) {
    wasGameRunning = false;
    gameEndedAtMilliseconds = Date.now();
    gameEndedAtSeconds = gameEndedAtMilliseconds / MILLISECONDS_PER_SECOND;
    suggestions = null;
    askSoon(0);
  }
}

function closeCard(): void {
  gameEndedAtSeconds = null;
  suggestions = null;
  if (askTimer !== null) {
    window.clearTimeout(askTimer);
    askTimer = null;
  }
  drawCard();
}

function askSoon(milliseconds: number): void {
  if (askTimer !== null) {
    window.clearTimeout(askTimer);
  }
  askTimer = window.setTimeout(() => {
    askTimer = null;
    void askForSuggestions();
  }, milliseconds);
}

async function askForSuggestions(): Promise<void> {
  const endedAt = gameEndedAtSeconds;
  if (endedAt === null) {
    return;
  }
  const askedSpice = spice;
  let answer: unknown = null;
  try {
    const response = await fetch(`${SUGGESTIONS_PATH}?spice=${String(askedSpice)}`);
    answer = response.ok ? ((await response.json()) as unknown) : null;
  } catch {
    // The engine is away for a moment; asked again below.
  }
  if (gameEndedAtSeconds !== endedAt || askedSpice !== spice) {
    return;
  }
  if (isRoastSuggestions(answer) && answer.kept_at_seconds >= endedAt - KEPT_BEFORE_THE_END_SECONDS) {
    suggestions = answer;
    drawCard();
    if (answer.is_quick) {
      askSoon(QUICK_CASE_MILLISECONDS);
    }
    return;
  }
  if (suggestions === null && Date.now() - gameEndedAtMilliseconds < LONGEST_WAIT_MILLISECONDS) {
    askSoon(WAITING_MILLISECONDS);
  }
}

/** Copy a line: the app copies it and shows its toast; a browser's clipboard takes it otherwise. */
function copyLine(line: string): void {
  const app = window.webkit?.messageHandlers?.leagueasymodeCopy;
  if (app !== undefined) {
    app.postMessage(line);
  } else {
    void navigator.clipboard.writeText(line).catch(() => undefined);
  }
  copiedLine = line;
  drawCard();
  window.setTimeout(() => {
    if (copiedLine === line) {
      copiedLine = null;
      drawCard();
    }
  }, COPIED_MILLISECONDS);
}

function button(className: string, text: string, onClick: () => void): HTMLButtonElement {
  const element = document.createElement("button");
  element.type = "button";
  element.className = `${className} ${TAKES_CLICKS_CLASS}`;
  element.textContent = text;
  element.addEventListener("click", onClick);
  return element;
}

function drawCard(): void {
  const card = document.getElementById("roast-card");
  if (card === null) {
    return;
  }
  if (gameEndedAtSeconds === null || suggestions === null) {
    card.hidden = true;
    card.replaceChildren();
    drawnText = "";
    return;
  }
  // Drawn again only when what it shows changes, so a click is never lost to a redraw.
  const shown = suggestions;
  const text = JSON.stringify([shown.lines, spice, copiedLine]);
  if (text === drawnText && !card.hidden) {
    return;
  }
  drawnText = text;
  const header = document.createElement("div");
  header.className = "roast-card-header";
  const title = document.createElement("span");
  title.className = "roast-card-title";
  title.textContent = "Roast this game";
  const close = button("roast-card-close", "✕", closeCard);
  close.setAttribute("aria-label", "Close");
  header.append(title, close);
  const spices = document.createElement("div");
  spices.className = "roast-card-spice";
  const spiceLabel = document.createElement("span");
  spiceLabel.textContent = "Spice";
  spices.append(
    spiceLabel,
    ...SPICE_NAMES.map((name, index) => {
      const level = index + 1;
      const choice = button("roast-card-level", String(level), () => {
        spice = level;
        drawCard();
        askSoon(0);
      });
      choice.title = name;
      choice.setAttribute("aria-label", `${String(level)} ${name}`);
      choice.setAttribute("aria-pressed", String(level === spice));
      return choice;
    }),
  );
  const lines = document.createElement("ul");
  lines.className = "roast-card-lines";
  lines.append(
    ...shown.lines.map((line) => {
      const item = document.createElement("li");
      const choice = button("roast-card-line", line, () => {
        copyLine(line);
      });
      if (line === copiedLine) {
        choice.dataset["copied"] = "true";
      }
      item.append(choice);
      return item;
    }),
  );
  const hint = document.createElement("p");
  hint.className = "roast-card-hint";
  hint.textContent = copiedLine === null ? "Click a line to copy · ⌘V in chat" : "Copied · ⌘V in chat";
  card.replaceChildren(header, spices, lines, hint);
  card.hidden = false;
}
