---
type: Key Metrics
title: Key metrics
description: One north star, four drivers and two guardrails that prove LeagueasyMode's promise to the player, each scored from the owner's recorded games against League's post-game timeline or counted from what the app sends.
tags: [metrics]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T06:26:10Z }
---

# Key metrics

The promise ([USERS.md](USERS.md), P-01): the player makes a better call because the overlay told
them something true they could not see, and it never got in the way. Each metric below is scored
from the owner's recorded games against League's post-game timeline (the accuracy history,
`leagueasymode history`), or counted from what the app sends to the recordings repository. None
has a scored value yet: no game the owner played had been scored on 2026-10-29.

## 1. North star

- [NS-01: Games the overlay got right](metrics/NS-01.md)

## 2. Drivers

- [DR-01: Games scored](metrics/DR-01.md)
- [DR-02: The enemy jungler found](metrics/DR-02.md)
- [DR-03: Fight calls](metrics/DR-03.md)
- [DR-04: Contest calls](metrics/DR-04.md)

## 3. Guardrails

- [GR-01: Engine stops](metrics/GR-01.md)
- [GR-02: Problem reports](metrics/GR-02.md)

## 4. Considered and rejected

- **Time the overlay is on screen:** says nothing of whether what it showed was true or useful.
- **Callouts shown:** more is not better ("so much info a lot of it is uselss 90% of the time");
  a count of callouts at a glance may come back as a guardrail once a replay computes it.
- **Hidden gold and experience error:** scored in the history, but the player sees them only on
  Tab now; they feed NS-01 through their thresholds, not as drivers.
- **Downloads or users of the public app:** the app counts no one and sends nothing about
  anyone (P-02).
- **The player's win rate:** too many causes besides the overlay, and too few games to see it.

## 5. Dashboard and alert mapping

There is no dashboard. The drivers' values print with `leagueasymode history` on the Mac and in
the daily cloud session (13:52 UTC, P-03), which reads `games/`, `crash-reports/` and `reports/`
and opens a pull request for what they show: that run is the alert for GR-01 and GR-02. Once
`tests/accuracy_thresholds.json` holds thresholds (from 20 games), CI fails a push that drops an
estimator below its own: the alert for NS-01's accuracy part. The metrics' attested computations
(`docs/computations/`) are to write with the first scored games.
