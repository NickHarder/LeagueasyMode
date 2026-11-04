/**
 * The post-game window: the roast, and the last game as League's end screen does not show it.
 *
 * A page of its own (`/summary.html`), opened from the macOS app's menu in a normal window, not
 * the click-through overlay. It reads the last game from `/summary`, once; the roast under the
 * result asks `/case` for each target the player picks. Only what League's own end screen does
 * not show, and nothing about how the overlay's estimates scored (the owner, 2026-11-03: "just fun
 * stuff i can analyze the end game screen doesnt already give ... no nerd stuff").
 */

import { caseSectionElement } from "./case_file.js";
import {
  type GameSummary,
  type SummaryMoment,
  type SummaryPoint,
  isGameSummary,
} from "./summary_state.js";

const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
const SECONDS_PER_MINUTE = 60;
const PERCENT = 100;
const ONE_THOUSAND = 1000;
const MINUS_SIGN = "−";
const CHART_WIDTH = 640;
const CHART_HEIGHT = 200;
const MARGIN_LEFT = 44;
const MARGIN_RIGHT = 72;
const MARGIN_TOP = 12;
const MARGIN_BOTTOM = 24;
const MINUTE_TICK_STEP = 5;
const END_DOT_RADIUS = 4;
const SWING_DOT_RADIUS = 5;
// Gold axis steps to choose among, so that the axis has a few round ticks.
const GOLD_TICK_STEPS = [500, 1000, 2000, 5000, 10000, 20000];
const MOST_GOLD_TICKS = 5;

/** One line of a chart: its name, its points, and the CSS variable of its color. */
interface ChartSeries {
  readonly name: string;
  readonly points: readonly SummaryPoint[];
  readonly colorVariable: string;
}

/** A line chart's description. */
interface LineChart {
  readonly label: string;
  readonly series: readonly ChartSeries[];
  readonly lowest: number;
  readonly highest: number;
  readonly ticks: readonly number[];
  readonly formatValue: (value: number) => string;
  // A hairline drawn across at this value, such as 50% or no lead.
  readonly reference: number;
  // Minutes marked on the first series, such as the biggest swings.
  readonly markedMinutes: readonly number[];
}

/** Return a game time as minutes and seconds: "31:24". */
export function formatClock(seconds: number): string {
  const wholeSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(wholeSeconds / SECONDS_PER_MINUTE);
  const remainder = wholeSeconds % SECONDS_PER_MINUTE;
  return `${String(minutes)}:${String(remainder).padStart(2, "0")}`;
}

/** Return a chance as a whole percentage: "64%". */
export function formatPercent(chance: number): string {
  return `${(chance * PERCENT).toFixed(0)}%`;
}

/** Return a change of chance with its sign: "+18%", "−12%". */
export function formatChange(change: number): string {
  const points = Math.round(change * PERCENT);
  return points >= 0 ? `+${String(points)}%` : `${MINUS_SIGN}${String(-points)}%`;
}

/** Return a gold lead in thousands with its sign: "+2.1k", "−0.8k", "0". */
export function formatGoldLead(gold: number): string {
  const thousands = Math.round(gold / 100) / (ONE_THOUSAND / 100);
  if (thousands === 0) {
    return "0";
  }
  return thousands > 0 ? `+${thousands.toFixed(1)}k` : `${MINUS_SIGN}${(-thousands).toFixed(1)}k`;
}

/** Return round ticks for a gold axis that holds every value, with 0 among them. */
export function goldTicks(values: readonly number[]): number[] {
  const largest = Math.max(1, ...values.map((value) => Math.abs(value)));
  const step = GOLD_TICK_STEPS.find((candidate) => (2 * Math.ceil(largest / candidate)) + 1 <= MOST_GOLD_TICKS) ?? 50000;
  const reach = Math.ceil(largest / step) * step;
  const ticks: number[] = [];
  for (let tick = -reach; tick <= reach; tick += step) {
    ticks.push(tick);
  }
  return ticks;
}

function svgElement<Name extends keyof SVGElementTagNameMap>(
  name: Name,
  attributes: Readonly<Record<string, string | number>>,
): SVGElementTagNameMap[Name] {
  const element = document.createElementNS(SVG_NAMESPACE, name);
  for (const [attribute, value] of Object.entries(attributes)) {
    element.setAttribute(attribute, String(value));
  }
  return element;
}

function htmlElement<Name extends keyof HTMLElementTagNameMap>(
  name: Name,
  className: string,
  text?: string,
): HTMLElementTagNameMap[Name] {
  const element = document.createElement(name);
  if (className !== "") {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}

/** Draw a line chart, with its crosshair and tooltip, and a table of its values beneath. */
function lineChartElement(chart: LineChart): HTMLElement {
  const figure = htmlElement("figure", "chart");
  const allMinutes = chart.series.flatMap((series) => series.points.map((point) => point.minute));
  const lastMinute = Math.max(1, ...allMinutes);
  const plotWidth = CHART_WIDTH - MARGIN_LEFT - MARGIN_RIGHT;
  const plotHeight = CHART_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM;
  const xOf = (minute: number): number => MARGIN_LEFT + (minute / lastMinute) * plotWidth;
  const yOf = (value: number): number =>
    MARGIN_TOP + plotHeight - ((value - chart.lowest) / (chart.highest - chart.lowest)) * plotHeight;
  const svg = svgElement("svg", {
    viewBox: `0 0 ${String(CHART_WIDTH)} ${String(CHART_HEIGHT)}`,
    role: "img",
    "aria-label": chart.label,
    tabindex: 0,
    class: "chart-plot",
  });
  for (const tick of chart.ticks) {
    svg.append(
      svgElement("line", {
        x1: MARGIN_LEFT,
        x2: MARGIN_LEFT + plotWidth,
        y1: yOf(tick),
        y2: yOf(tick),
        class: tick === chart.reference ? "chart-baseline" : "chart-grid",
      }),
    );
    const tickLabel = svgElement("text", { x: MARGIN_LEFT - 6, y: yOf(tick) + 4, class: "chart-tick chart-tick-y" });
    tickLabel.textContent = chart.formatValue(tick);
    svg.append(tickLabel);
  }
  for (let minute = 0; minute <= lastMinute; minute += MINUTE_TICK_STEP) {
    const tickLabel = svgElement("text", { x: xOf(minute), y: CHART_HEIGHT - 6, class: "chart-tick chart-tick-x" });
    tickLabel.textContent = `${String(minute)}:00`;
    svg.append(tickLabel);
  }
  for (const series of chart.series) {
    if (series.points.length === 0) {
      continue;
    }
    const path = series.points
      .map((point, index) => `${index === 0 ? "M" : "L"}${xOf(point.minute).toFixed(1)},${yOf(point.value).toFixed(1)}`)
      .join(" ");
    svg.append(svgElement("path", { d: path, class: "chart-line", stroke: `var(${series.colorVariable})` }));
    const last = series.points[series.points.length - 1];
    if (last !== undefined) {
      svg.append(
        svgElement("circle", {
          cx: xOf(last.minute),
          cy: yOf(last.value),
          r: END_DOT_RADIUS,
          class: "chart-dot",
          fill: `var(${series.colorVariable})`,
        }),
      );
      // Direct labels supplement the legend, at the end of each line.
      const endLabel = svgElement("text", { x: xOf(last.minute) + 8, y: yOf(last.value) + 4, class: "chart-end-label" });
      endLabel.textContent = chart.series.length > 1 ? `${series.name} ${chart.formatValue(last.value)}` : chart.formatValue(last.value);
      svg.append(endLabel);
    }
  }
  const firstSeries = chart.series[0];
  for (const minute of chart.markedMinutes) {
    const point = firstSeries?.points.find((candidate) => candidate.minute === minute);
    if (point !== undefined && firstSeries !== undefined) {
      svg.append(
        svgElement("circle", {
          cx: xOf(point.minute),
          cy: yOf(point.value),
          r: SWING_DOT_RADIUS,
          class: "chart-dot chart-swing",
          fill: `var(${firstSeries.colorVariable})`,
        }),
      );
    }
  }
  const crosshair = svgElement("line", { y1: MARGIN_TOP, y2: MARGIN_TOP + plotHeight, class: "chart-crosshair", visibility: "hidden" });
  svg.append(crosshair);
  const tooltip = htmlElement("div", "chart-tooltip");
  tooltip.hidden = true;
  const showMinute = (minute: number): void => {
    const x = xOf(minute);
    crosshair.setAttribute("x1", String(x));
    crosshair.setAttribute("x2", String(x));
    crosshair.setAttribute("visibility", "visible");
    const rows = chart.series.flatMap((series) => {
      const point = series.points.find((candidate) => candidate.minute === minute);
      if (point === undefined) {
        return [];
      }
      const row = htmlElement("div", "chart-tooltip-row");
      const key = htmlElement("span", "chart-tooltip-key");
      key.style.backgroundColor = `var(${series.colorVariable})`;
      row.append(key, htmlElement("strong", "", chart.formatValue(point.value)), htmlElement("span", "chart-tooltip-name", series.name));
      return [row];
    });
    tooltip.replaceChildren(htmlElement("div", "chart-tooltip-time", `${String(minute)}:00`), ...rows);
    tooltip.hidden = false;
    tooltip.style.left = `${String((x / CHART_WIDTH) * PERCENT)}%`;
  };
  const hide = (): void => {
    crosshair.setAttribute("visibility", "hidden");
    tooltip.hidden = true;
  };
  let focusedMinute = lastMinute;
  svg.addEventListener("pointermove", (event) => {
    const bounds = svg.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * CHART_WIDTH;
    focusedMinute = Math.min(lastMinute, Math.max(0, Math.round(((x - MARGIN_LEFT) / plotWidth) * lastMinute)));
    showMinute(focusedMinute);
  });
  svg.addEventListener("pointerleave", hide);
  // The same readout on keyboard focus: the arrows move it a minute at a time.
  svg.addEventListener("focus", () => {
    showMinute(focusedMinute);
  });
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      focusedMinute = Math.min(lastMinute, Math.max(0, focusedMinute + (event.key === "ArrowLeft" ? -1 : 1)));
      showMinute(focusedMinute);
      event.preventDefault();
    }
  });
  figure.append(svg, tooltip, tableViewElement(chart));
  return figure;
}

/** Return a chart's values as a table, folded away, so that no value needs the pointer. */
function tableViewElement(chart: LineChart): HTMLElement {
  const details = htmlElement("details", "chart-table");
  details.append(htmlElement("summary", "", "Table"));
  const table = htmlElement("table", "");
  const header = htmlElement("tr", "");
  header.append(htmlElement("th", "", "Minute"), ...chart.series.map((series) => htmlElement("th", "", series.name)));
  const minutes = [...new Set(chart.series.flatMap((series) => series.points.map((point) => point.minute)))].sort(
    (first, second) => first - second,
  );
  const rows = minutes.map((minute) => {
    const row = htmlElement("tr", "");
    row.append(
      htmlElement("td", "", `${String(minute)}:00`),
      ...chart.series.map((series) => {
        const point = series.points.find((candidate) => candidate.minute === minute);
        return htmlElement("td", "", point === undefined ? "" : chart.formatValue(point.value));
      }),
    );
    return row;
  });
  table.append(header, ...rows);
  details.append(table);
  return details;
}

function sectionElement(title: string, ...children: HTMLElement[]): HTMLElement {
  const section = htmlElement("section", "summary-section");
  section.append(htmlElement("h2", "", title), ...children);
  return section;
}

function headerElement(summary: GameSummary): HTMLElement {
  const header = htmlElement("header", "summary-header");
  const resultText = summary.result === "win" ? "Victory" : summary.result === "loss" ? "Defeat" : "Game over";
  const hero = htmlElement("h1", "summary-result", resultText);
  hero.dataset["result"] = summary.result ?? "unknown";
  const detail = [summary.champion_name, formatClock(summary.duration_seconds)].filter((part): part is string => part !== null);
  header.append(hero, htmlElement("p", "summary-detail", detail.join(" · ")));
  return header;
}

function swingsElement(summary: GameSummary): HTMLElement {
  const list = htmlElement("ol", "summary-swings");
  for (const swing of summary.swings) {
    const item = htmlElement("li", "");
    item.dataset["direction"] = swing.change >= 0 ? "ally" : "enemy";
    const happened = swing.moments.length > 0 ? swing.moments.join("; ") : "no kill or objective: gold and levels";
    item.append(
      htmlElement("span", "summary-swing-time", `${String(swing.minute - 1)}:00–${String(swing.minute)}:00`),
      htmlElement("strong", "summary-swing-change", formatChange(swing.change)),
      htmlElement("span", "summary-swing-moments", happened),
    );
    list.append(item);
  }
  return list;
}

function momentsElement(moments: readonly SummaryMoment[]): HTMLElement {
  const list = htmlElement("ol", "summary-moments");
  for (const moment of moments) {
    const item = htmlElement("li", "");
    item.dataset["side"] = moment.side;
    const key = htmlElement("span", "summary-moment-key");
    key.title = moment.side === "ally" ? "your team" : "their team";
    item.append(htmlElement("span", "summary-moment-time", formatClock(moment.game_time_seconds)), key, htmlElement("span", "", moment.text));
    list.append(item);
  }
  return list;
}

/** Return the moments' legend: whose good each dot marks, so that color is never alone. */
function momentsLegendElement(): HTMLElement {
  const legend = htmlElement("div", "chart-legend");
  for (const [side, name] of [
    ["ally", "your team's"],
    ["enemy", "their team's"],
  ] as const) {
    const item = htmlElement("span", "chart-legend-item");
    item.dataset["side"] = side;
    item.append(htmlElement("span", "summary-moment-key"), document.createTextNode(name));
    legend.append(item);
  }
  return legend;
}

/** Draw the whole window from the last game. */
export function renderSummary(root: HTMLElement, summary: GameSummary): void {
  const winSeries: ChartSeries = { name: "Win chance", points: summary.win_chance, colorVariable: "--series-1" };
  // The gold lead as it was: the timeline's when Riot sent it, else the overlay's read of it. No
  // estimate against truth here (the owner, 2026-11-03: "no nerd stuff").
  const goldSeries: ChartSeries[] = [
    {
      name: "Gold lead",
      points: summary.gold_lead_true.length > 0 ? summary.gold_lead_true : summary.gold_lead_estimated,
      colorVariable: "--series-1",
    },
  ];
  const ticks = goldTicks(goldSeries.flatMap((series) => series.points.map((point) => point.value)));
  // The server leaves the win chance out unless "Show experimental estimates" is on: it has not
  // beaten a coin flip on real games yet. Without it, neither its chart nor what swung it shows.
  const hasWinChance = summary.win_chance.length > 0;
  const winChanceSections = hasWinChance
    ? [
        sectionElement(
          "Your win chance",
          lineChartElement({
            label: "Your team's win chance at the start of each minute",
            series: [winSeries],
            lowest: 0,
            highest: 1,
            ticks: [0, 0.25, 0.5, 0.75, 1],
            formatValue: formatPercent,
            reference: 0.5,
            markedMinutes: summary.swings.map((swing) => swing.minute),
          }),
        ),
      ]
    : [];
  const swingSections = hasWinChance ? [sectionElement("What swung it", swingsElement(summary))] : [];
  root.replaceChildren(
    headerElement(summary),
    caseSectionElement(fetchJson),
    ...winChanceSections,
    sectionElement(
      "Gold lead",
      lineChartElement({
        label: "Your team's gold lead each minute",
        series: goldSeries,
        lowest: ticks[0] ?? -1,
        highest: ticks[ticks.length - 1] ?? 1,
        ticks,
        formatValue: formatGoldLead,
        reference: 0,
        markedMinutes: [],
      }),
    ),
    ...swingSections,
    sectionElement("Key moments", momentsLegendElement(), momentsElement(summary.moments)),
  );
}

/** Show that no game has been recorded yet. */
function renderNoGame(root: HTMLElement): void {
  root.replaceChildren(
    htmlElement("h1", "summary-result", "No game yet"),
    htmlElement(
      "p",
      "summary-detail",
      "Play a game with LeagueasyMode running; this window fills in once the match timeline arrives, a minute or two after the game.",
    ),
  );
}

async function fetchJson(path: string): Promise<unknown> {
  const response = await fetch(path);
  return response.ok ? ((await response.json()) as unknown) : null;
}

async function start(): Promise<void> {
  const root = document.getElementById("summary");
  if (root === null) {
    return;
  }
  const summary = await fetchJson("/summary");
  if (!isGameSummary(summary)) {
    renderNoGame(root);
    return;
  }
  renderSummary(root, summary);
}

void start();
