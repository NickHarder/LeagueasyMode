/**
 * What the engine tells the post-game window about the last game's case: mirrors
 * `leagueasymode.roast.case_view` (`overlay/web/roast_case.schema.json`), and the query `/case`
 * takes.
 */

export type CaseSide = "ally" | "enemy";
export type SourceKind = "game" | "timeline" | "live" | "computation";

/** One of the ten players, for the target chips. */
export interface CasePlayer {
  readonly participant_id: number;
  readonly champion: string;
  readonly position: string;
  readonly side: CaseSide;
  readonly is_defendant: boolean;
  readonly is_friend: boolean;
}

/** A piece of a line; one that states an exhibit's value carries its letter. */
export interface ViewPart {
  readonly text: string;
  readonly letter: string | null;
}

/** One line of the case. */
export interface ViewLine {
  readonly parts: readonly ViewPart[];
}

/** One lane of the position diff board, at minute 14. */
export interface ViewLane {
  readonly position: string;
  readonly ally_champion: string;
  readonly enemy_champion: string;
  readonly outcome: string;
  readonly gold_difference: string | null;
  readonly cs_difference: string | null;
  readonly letter: string | null;
}

/** One exhibit, and where its value came from. */
export interface ViewExhibit {
  readonly letter: string;
  readonly label: string;
  readonly display: string;
  readonly unit: string;
  readonly source: string;
  readonly source_kind: SourceKind;
  readonly supporting: boolean;
}

/** The case, for the window. */
export interface CaseView {
  readonly game_id: number;
  readonly players: readonly CasePlayer[];
  readonly target: string;
  readonly spice: number;
  readonly spice_name: string;
  readonly prove: boolean;
  readonly take: number;
  readonly verdict_title: string;
  readonly verdict_summary: string;
  readonly acquitted: boolean | null;
  readonly board: readonly ViewLane[];
  readonly lines: readonly ViewLine[];
  readonly closing_line: string;
  /** Lines to pick from for chat, the closing line first; the window copies the one clicked. */
  readonly closing_options: readonly string[];
  readonly closing_line_limit: number;
  readonly risk_warning: string | null;
  readonly exhibits: readonly ViewExhibit[];
  // Claude's take of the closing line (phase 11.8), and whether one is still being written.
  readonly claude_take: string | null;
  readonly claude_take_pending: boolean;
  // A quick case from the end-of-game stats (phase 11.7), until the full one comes.
  readonly is_quick: boolean;
}

/** What the window asks `/case` for. */
export interface CaseChoice {
  // "team", "enemy", "lane:<POSITION>" or "player:<participant id>".
  readonly target: string;
  readonly spice: number;
  readonly prove: boolean;
  readonly take: number;
}

export const DEFAULT_CHOICE: CaseChoice = { target: "team", spice: 2, prove: false, take: 0 };

const SIDES: ReadonlySet<string> = new Set(["ally", "enemy"]);
const SOURCE_KINDS: ReadonlySet<string> = new Set(["game", "timeline", "live", "computation"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isArrayOf<Item>(value: unknown, isItem: (item: unknown) => item is Item): value is readonly Item[] {
  return Array.isArray(value) && value.every(isItem);
}

function isTextOrNull(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isCasePlayer(value: unknown): value is CasePlayer {
  return (
    isRecord(value) &&
    typeof value["participant_id"] === "number" &&
    typeof value["champion"] === "string" &&
    typeof value["position"] === "string" &&
    typeof value["side"] === "string" &&
    SIDES.has(value["side"]) &&
    typeof value["is_defendant"] === "boolean" &&
    typeof value["is_friend"] === "boolean"
  );
}

function isViewPart(value: unknown): value is ViewPart {
  return isRecord(value) && typeof value["text"] === "string" && isTextOrNull(value["letter"]);
}

function isViewLine(value: unknown): value is ViewLine {
  return isRecord(value) && isArrayOf(value["parts"], isViewPart);
}

function isViewLane(value: unknown): value is ViewLane {
  return (
    isRecord(value) &&
    typeof value["position"] === "string" &&
    typeof value["ally_champion"] === "string" &&
    typeof value["enemy_champion"] === "string" &&
    typeof value["outcome"] === "string" &&
    isTextOrNull(value["gold_difference"]) &&
    isTextOrNull(value["cs_difference"]) &&
    isTextOrNull(value["letter"])
  );
}

function isViewExhibit(value: unknown): value is ViewExhibit {
  return (
    isRecord(value) &&
    typeof value["letter"] === "string" &&
    typeof value["label"] === "string" &&
    typeof value["display"] === "string" &&
    typeof value["unit"] === "string" &&
    typeof value["source"] === "string" &&
    typeof value["source_kind"] === "string" &&
    SOURCE_KINDS.has(value["source_kind"]) &&
    typeof value["supporting"] === "boolean"
  );
}

/** Return whether a value is a case as `/case` sends it. */
export function isCaseView(value: unknown): value is CaseView {
  if (!isRecord(value)) {
    return false;
  }
  const acquitted = value["acquitted"];
  return (
    typeof value["game_id"] === "number" &&
    isArrayOf(value["players"], isCasePlayer) &&
    typeof value["target"] === "string" &&
    typeof value["spice"] === "number" &&
    typeof value["spice_name"] === "string" &&
    typeof value["prove"] === "boolean" &&
    typeof value["take"] === "number" &&
    typeof value["verdict_title"] === "string" &&
    typeof value["verdict_summary"] === "string" &&
    (acquitted === null || typeof acquitted === "boolean") &&
    isArrayOf(value["board"], isViewLane) &&
    isArrayOf(value["lines"], isViewLine) &&
    typeof value["closing_line"] === "string" &&
    isArrayOf(value["closing_options"], (option): option is string => typeof option === "string") &&
    typeof value["closing_line_limit"] === "number" &&
    isTextOrNull(value["risk_warning"]) &&
    isArrayOf(value["exhibits"], isViewExhibit) &&
    isTextOrNull(value["claude_take"]) &&
    typeof value["claude_take_pending"] === "boolean" &&
    typeof value["is_quick"] === "boolean"
  );
}

/** Return the path that asks `/case` for a choice. */
export function casePath(choice: CaseChoice): string {
  const query = new URLSearchParams({
    target: choice.target,
    spice: String(choice.spice),
    prove: choice.prove ? "1" : "0",
    take: String(choice.take),
  });
  return `/case?${query.toString()}`;
}
