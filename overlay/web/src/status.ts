/**
 * The status page: what the engine sees, part by part, kept current while it is open, and the
 * report to copy into a message after a test. Nothing on it names a player.
 */

import { type EngineStatus, STATE_NAMES, eventText, isEngineStatus, statusReport, utcTimeText } from "./status_state.js";

const REFRESH_MILLISECONDS = 2000;

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

/** The parts of the page that change with each report. */
interface StatusView {
  readonly detail: HTMLElement;
  readonly parts: HTMLElement;
  readonly events: HTMLElement;
  readonly fieldsSection: HTMLElement;
  readonly fields: HTMLElement;
  readonly report: HTMLTextAreaElement;
}

function updateView(view: StatusView, status: EngineStatus): void {
  view.detail.textContent = `LeagueasyMode ${status.version} · updated ${utcTimeText(status.reported_at)}`;
  view.parts.replaceChildren(
    ...status.parts.map((part) => {
      const row = htmlElement("li", "status-part");
      row.dataset["state"] = part.state;
      row.dataset["key"] = part.key;
      // The state is written out, not only colored.
      row.append(
        htmlElement("span", "status-badge", STATE_NAMES[part.state]),
        htmlElement("strong", "status-title", part.title),
        htmlElement("span", "status-detail", part.detail),
      );
      return row;
    }),
  );
  view.events.replaceChildren(
    ...(status.events.length > 0
      ? status.events.map((event) => {
          const item = htmlElement("li", event.is_read ? "" : "status-unread", eventText(event));
          return item;
        })
      : [htmlElement("li", "status-none", "None yet: the feed fills once a game is running.")]),
  );
  view.fieldsSection.hidden = status.unreadable_fields.length === 0;
  view.fields.replaceChildren(...status.unreadable_fields.map((field) => htmlElement("li", "", field)));
  view.report.value = statusReport(status);
}

async function copyReport(report: HTMLTextAreaElement, copyStatus: HTMLElement): Promise<void> {
  try {
    await navigator.clipboard.writeText(report.value);
    copyStatus.textContent = "Copied: paste it into a message.";
  } catch {
    report.focus();
    report.select();
    copyStatus.textContent = "Selected: press ⌘C to copy it.";
  }
}

/** Draw the page's frame, and return the parts that each report fills. */
export function renderStatusFrame(root: HTMLElement): StatusView {
  const detail = htmlElement("p", "summary-detail");
  const parts = htmlElement("ul", "status-parts");
  const events = htmlElement("ul", "status-events");
  const fields = htmlElement("ul", "status-fields");
  const fieldsSection = htmlElement("section", "status-section");
  fieldsSection.append(
    htmlElement("h2", "", "Fields the engine could not read"),
    htmlElement(
      "p",
      "summary-detail",
      "Places in the game's answer whose value is missing or of another kind than expected: they need a change to the engine.",
    ),
    fields,
  );
  const report = htmlElement("textarea", "status-report");
  report.readOnly = true;
  report.rows = 16;
  report.setAttribute("aria-label", "Report");
  const copyButton = htmlElement("button", "status-copy", "Copy report");
  copyButton.type = "button";
  const copyStatus = htmlElement("span", "status-copied");
  copyStatus.setAttribute("role", "status");
  copyButton.addEventListener("click", () => {
    void copyReport(report, copyStatus);
  });
  const eventsSection = htmlElement("section", "status-section");
  eventsSection.append(
    htmlElement("h2", "", "Feed events"),
    htmlElement("p", "summary-detail", "Each kind of event in this game's feed; one no estimator reads may be new."),
    events,
  );
  const reportSection = htmlElement("section", "status-section");
  const actions = htmlElement("div", "status-actions");
  actions.append(copyButton, copyStatus);
  reportSection.append(
    htmlElement("h2", "", "Report"),
    htmlElement("p", "summary-detail", "To send after a test. It names no player and no folder of yours."),
    actions,
    report,
  );
  root.replaceChildren(
    htmlElement("h1", "summary-result", "What the engine sees"),
    detail,
    parts,
    eventsSection,
    fieldsSection,
    reportSection,
  );
  return { detail, parts, events, fieldsSection, fields, report };
}

async function fetchStatus(): Promise<EngineStatus | null> {
  try {
    const response = await fetch("/status");
    const status: unknown = response.ok ? await response.json() : null;
    return isEngineStatus(status) ? status : null;
  } catch {
    return null;
  }
}

async function start(): Promise<void> {
  const root = document.getElementById("status");
  if (root === null) {
    return;
  }
  const firstStatus = await fetchStatus();
  if (firstStatus === null) {
    root.replaceChildren(
      htmlElement("h1", "summary-result", "Status"),
      htmlElement("p", "summary-detail", "The engine is not running; start LeagueasyMode and open this page again."),
    );
    return;
  }
  const view = renderStatusFrame(root);
  updateView(view, firstStatus);
  window.setInterval(() => {
    void fetchStatus().then((status) => {
      if (status !== null) {
        updateView(view, status);
      }
    });
  }, REFRESH_MILLISECONDS);
}

void start();
