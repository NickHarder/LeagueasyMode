/**
 * What the engine tells the post-game window: the last game reconstructed, and the accuracy
 * history. Mirrors `leagueasymode.game_summary` (`overlay/web/game_summary.schema.json`) and the
 * accuracy history's lines (`leagueasymode.accuracy_history`).
 */

export type Side = "ally" | "enemy";

/** One minute's value of a series. */
export interface SummaryPoint {
  readonly minute: number;
  readonly value: number;
}

/** One moment of the feed, from the player's side. */
export interface SummaryMoment {
  readonly game_time_seconds: number;
  readonly kind: string;
  readonly side: Side;
  readonly text: string;
}

/** A minute that moved the win chance, and what happened in it. */
export interface WinSwing {
  readonly minute: number;
  readonly change: number;
  readonly moments: readonly string[];
}

/** One estimator's score on the game. */
export interface SummaryScore {
  readonly estimator: string;
  readonly measure: string;
  readonly sample_count: number;
  readonly value: number;
  readonly text: string;
}

/** The game reconstructed. */
export interface GameSummary {
  readonly recording_name: string;
  readonly result: "win" | "loss" | null;
  readonly champion_name: string | null;
  readonly duration_seconds: number;
  readonly win_chance: readonly SummaryPoint[];
  readonly gold_lead_estimated: readonly SummaryPoint[];
  readonly gold_lead_true: readonly SummaryPoint[];
  readonly moments: readonly SummaryMoment[];
  readonly swings: readonly WinSwing[];
  readonly scores: readonly SummaryScore[];
}

/** One game of the accuracy history. */
export interface GameAccuracy {
  readonly recording_name: string;
  readonly scores: readonly SummaryScoreLine[];
}

/** One estimator's score in the accuracy history. */
export interface SummaryScoreLine {
  readonly estimator: string;
  readonly measure: string;
  readonly sample_count: number;
  readonly value: number;
}

const SIDES: ReadonlySet<string> = new Set(["ally", "enemy"]);
const RESULTS: ReadonlySet<string> = new Set(["win", "loss"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isArrayOf<Item>(value: unknown, isItem: (item: unknown) => item is Item): value is readonly Item[] {
  return Array.isArray(value) && value.every(isItem);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isSummaryPoint(value: unknown): value is SummaryPoint {
  return isRecord(value) && typeof value["minute"] === "number" && typeof value["value"] === "number";
}

function isSummaryMoment(value: unknown): value is SummaryMoment {
  return (
    isRecord(value) &&
    typeof value["game_time_seconds"] === "number" &&
    typeof value["kind"] === "string" &&
    typeof value["side"] === "string" &&
    SIDES.has(value["side"]) &&
    typeof value["text"] === "string"
  );
}

function isWinSwing(value: unknown): value is WinSwing {
  return (
    isRecord(value) &&
    typeof value["minute"] === "number" &&
    typeof value["change"] === "number" &&
    isArrayOf(value["moments"], isString)
  );
}

function isScoreLine(value: unknown): value is SummaryScoreLine {
  return (
    isRecord(value) &&
    typeof value["estimator"] === "string" &&
    typeof value["measure"] === "string" &&
    typeof value["sample_count"] === "number" &&
    typeof value["value"] === "number"
  );
}

function isSummaryScore(value: unknown): value is SummaryScore {
  return isScoreLine(value) && isRecord(value) && typeof value["text"] === "string";
}

/** Return whether a value is the last game's summary as the engine sends it. */
export function isGameSummary(value: unknown): value is GameSummary {
  if (!isRecord(value)) {
    return false;
  }
  const result = value["result"];
  const championName = value["champion_name"];
  return (
    typeof value["recording_name"] === "string" &&
    (result === null || (typeof result === "string" && RESULTS.has(result))) &&
    (championName === null || typeof championName === "string") &&
    typeof value["duration_seconds"] === "number" &&
    isArrayOf(value["win_chance"], isSummaryPoint) &&
    isArrayOf(value["gold_lead_estimated"], isSummaryPoint) &&
    isArrayOf(value["gold_lead_true"], isSummaryPoint) &&
    isArrayOf(value["moments"], isSummaryMoment) &&
    isArrayOf(value["swings"], isWinSwing) &&
    isArrayOf(value["scores"], isSummaryScore)
  );
}

function isGameAccuracy(value: unknown): value is GameAccuracy {
  return isRecord(value) && typeof value["recording_name"] === "string" && isArrayOf(value["scores"], isScoreLine);
}

/** Return the games of the accuracy history as the engine sends them; none when unreadable. */
export function accuracyGamesOf(value: unknown): readonly GameAccuracy[] {
  return isRecord(value) && isArrayOf(value["games"], isGameAccuracy) ? value["games"] : [];
}
