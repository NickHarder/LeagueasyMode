---
type: Plan
title: "Phase 7: packaging, without signing for now"
description: The slices of phase 7 of the approved plan, settings, an app bundle that needs no clone, and releases with an update check, built without Apple's signing as the owner chose, in a proposed build order with what each needs and where the owner decides.
tags: [plan, phase-7, packaging]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-09T01:37:17Z }
---

# Phase 7: packaging, without signing for now

Phase 7 of [the approved plan](overlay-and-inference.md) is "a signed app, auto-update,
settings". The owner, 2026-10-09: "keep building phase 7, skip signing for now". So everything is
built to work unsigned, and signing is a step added later without changing the rest: an unsigned
app opens after the player allows it once (right-click, Open; or System Settings, Privacy &
Security, Open Anyway).

## Slices, proposed build order

| # | Slice | Shows | Needs |
|---|---|---|---|
| 7.1 | Settings | A settings page (menu, "Settings…"): a switch for each part of the overlay (win chance, fight chance, contests, the You panel, the minimap layer, the enemy estimates, callouts, suggestions), each change showing at once | The player's choices in `preferences.json` in the application's directory, sent to the overlay with its state; the engine's own settings, for an installed app with no clone, in `settings.env` beside it |
| 7.2 | The app bundle | `LeagueasyMode.app`, built by CI and kept as an artifact of each run, that needs no clone of the repository | The Swift app, the engine as a wheel with the versions `uv.lock` pins, and `uv` (one binary, Apache or MIT licensed), all inside the bundle; the app runs the engine with the bundled `uv`, which fetches Python and the engine's dependencies once, on the first start |
| 7.3 | Releases and updates | A release on GitHub for each version tag, with the zipped app; the menu says when a newer release is out, and opens its page | A workflow on tags `v*`; the app asks GitHub's API for the latest release at most once a day, a switch in the menu turns that off; "Open at login" in the menu |

## How each is verified

- **7.1** by the server's tests (a change without the app's header is refused, an unknown
  preference is refused, a change is kept and sent with the state) and in Chromium (the switches,
  and the overlay without what was turned off).
- **7.2** by CI on macOS: the bundle is built and signed ad hoc, and its engine, started with the
  bundled `uv` from an empty home folder as the app starts it, serves every page; the Swift that
  finds the bundled engine and picks it over a clone has unit tests.
- **7.3** by unit tests of the version comparison, of reading GitHub's answer (a draft, a
  prerelease, an older version and an address off this repository all ignored), of the
  once-a-day rule and of open at login's menu item; the release workflow, which builds and checks
  the app as CI does, by its first tag.

## Where the owner decides

1. **Signing (all of 7).** Left out, as the owner chose; the $99 a year of the Apple Developer
   Program adds it, and with it updates that install themselves.
2. **The update check (7.3).** Proposed: on, at most once a day, turned off from the menu. It is
   the app's only request beyond this machine, League's own servers and Data Dragon.
3. **What the settings offer (7.1).** Proposed: the eight switches above; the strip's exact facts
   (levels, death timers, items) always show.
