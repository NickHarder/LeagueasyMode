---
type: Plan
title: "Overlay layout: move, resize and see through"
description: A plan, for the owner's approval, to let the player place each widget exactly, resize it and see the game through it, tied to the use cases in USERS.md, with the build order and what was considered and cut.
tags: [plan, layout, overlay]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T03:20:00Z }
---

# Overlay layout: move, resize and see through

The owner, 2026-10-29, after the first screenshot of a game: "it covers some stuff", then "can i
move the overlay somehow? drag it to move it or use sliders for x and y postion or resize it?
think of functionality."

It serves [UC-06](../USERS.md) above all: the overlay where the player wants it, at a size they
can read. Because a widget that covers League's HUD, or is too small to read in the second a
glance takes, fails every other use case on screen, it serves UC-02 to UC-05 too.

## What exists

- **Edit layout** (menu, or the shortcut while it is on): the overlay tints and takes the mouse;
  each of the four widgets (objective strip, callouts, enemy strip, You panel) is dragged to a new
  place, kept in `layout.json` as a share of League's window, so it holds when the window
  changes size. Esc, the shortcut or two minutes end it; Reset layout puts all back.
- **Settings:** a switch per widget, on or off.
- **Not there:** a size for a widget, a place set to the pixel, a way to see the game through a
  widget, anything that keeps a widget off League's own HUD.

## Slices, proposed build order

| # | Slice | What changes for the player | Use cases |
|---|---|---|---|
| L.1 | **Resize** | In edit mode each widget has a handle at its corner: drag it to make the widget bigger or smaller (60% to 160%), or scroll over it. The size is kept per widget in `layout.json`, beside the place | UC-06, UC-02 to UC-05 |
| L.2 | **Sliders** | A Layout section on the Settings page: for each widget, X and Y sliders (a share of League's window) and a size slider, moving the overlay live as they move; a Reset per widget. The same section fits the minimap layer to League's minimap: a size and a small nudge, for when League's settings file and its minimap do not line up | UC-06, UC-02 |
| L.3 | **Keep off League's HUD** | The usual places stay clear of League's HUD (kill feed and stats top right, minimap bottom right, champion bar bottom centre, ally portraits left). In edit mode those regions are shaded and named, so the player sees what a widget would cover, and a widget dropped on one is moved just off it. A widget is never placed outside League's window | UC-06 |
| L.4 | **See-through** | One "Overlay opacity" slider in Settings (40% to 100%): the widgets' backgrounds fade, the text stays readable | UC-06 |
| L.5 | **Hide from edit mode** | In edit mode, an × on each widget's label turns it off, as its switch in Settings does; the switch turns it back on | UC-06 |

Drag stays the quick way; the sliders are the exact way, and they work outside edit mode, so a
place can be set without the overlay ever taking the mouse in a game.

## How each is verified

- L.1, L.2, L.4, L.5: the layout's model and its file in the engine's tests; the drag, the handle,
  the sliders and the opacity in Chromium, as `tests/test_layout_page.py` tests moving today.
- L.3: the regions as shares of the window, tested against the window sizes seen (1920 × 925
  windowed); whether they match League's HUD is seen only on the Mac, so the first game after
  says.
- Every slice: the How to use page and `docs/references/macos-app.md` say how.

## Decision: drag, a handle and sliders, all three

- **Claim:** the player places and sizes widgets by dragging in edit mode, and sets them exactly
  with sliders on the Settings page.
- **Evidence:** the owner asked for both ("drag it to move it or use sliders"); dragging already
  works and is fast; a slider gives the exact place and size, and needs no edit mode, so the
  overlay never has to take the mouse.
- **Alternative considered:** sliders only, dropping edit mode.
- **Why rejected:** edit mode is the only way to see the widget move over the game itself while
  placing it; it is already built and tested.
- **How to reverse:** both write the same `layout.json`; either can be removed alone.

## Considered and cut

- **A text size per line:** too fine to set, and the widget's size scales its text.
- **A layout per game mode (the Rift, ARAM):** League's HUD is in the same places on both; one
  layout serves. Revisit if the player asks.
- **Moving the minimap layer freely:** it must sit on League's minimap; L.2's size and nudge fit
  it there instead.

## Where the owner decides

1. **Approve the plan,** or change the order.
2. **L.3's regions:** shade League's HUD in edit mode and move widgets off it (proposed), or only
   shade it and let the player choose.
