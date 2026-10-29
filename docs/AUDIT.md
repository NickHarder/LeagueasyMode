---
type: Audit
title: Audit
description: What LeagueasyMode builds on, audited in five areas (security, performance, architecture, data quality, compliance), the findings that matter most and what each one changes in the plan.
tags: [audit]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T07:03:29Z }
---

# Audit

## Summary

This audit ran late. The kit puts it before any product code; here it ran on 2026-10-29, three
weeks after the first product commit, with 167 product files in the repository (ARCH-01). So each
finding below is read as a backlog item against a working product, not as a constraint on a plan
not yet written. Each area's reproductions were run; any finding that would not reproduce was dropped.

The finding that matters most is not a defect in the code. It is that almost nothing the
estimators assume about a real game has been seen in one. The only real recording is a Practice
Tool game cancelled after a twentieth of a second: one answer, no players on the scoreboard, no
events (DQ-01, ARCH-05). The post-game ground truth every key metric is scored from (timeline,
game details, end-of-game stats, match history) has never been seen in a real recording (DQ-06),
and the test that holds estimators to their thresholds passes over zero recordings (ARCH-09). The
owner's ARAM and Swiftplay games of 2026-10-28 and 29 were left open on the Mac and never sent;
the fix (#89) ships with build 184. Until one full Summoner's Rift game arrives with its timeline,
every accuracy number in KEY_METRICS.md stays empty and every estimator stays a hand-set guess.

The one real recording did show two things the tests never do. The game's first answer comes from
the loading screen with an empty scoreboard, so the recorder never asks the client for champion
details (DQ-02); and the player on this machine is an error object there, which the engine reads
as a blank level-1 player (DQ-03, ARCH-06).

Security holds where it must: the local server binds to 127.0.0.1, checks the Host header against
DNS rebinding and the request header on every route that changes state; Riot's root certificate is
pinned; the GitHub token is never written or logged; the full history scans clean. The real
exposure is the update channel: the app installs any build whose zip matches a checksum published
beside it, from the same GitHub release, with an ad hoc signature and no Gatekeeper prompt
(SEC-01). Acceptable while the owner is the only user.

Privacy rests on the anonymizer, and it has a hole: keys it treats as game content (name,
displayName, description) are neither replaced nor searched, so a player name placed there would
pass (CMP-05). Problem reports scrub only this run's names, not PUUIDs or earlier runs' names
(SEC-02, CMP-07). Raw recordings with every player's Riot ID stay on the Mac indefinitely
(CMP-06).

Compliance carries the largest risk for a public app: enemy ultimate marks are the feature Riot's
2025 rule names (CMP-01), which the owner has decided to keep; the app is not registered with Riot
(CMP-03) and shows no Riot notice (CMP-04). Riot's primary pages could not be fetched from this
environment, so those findings rest on search results and say so.

Performance is not a concern in a game: one answer costs about 20 ms of a 500 ms poll, the page
uses under 4% of a core, memory stays under 2 MB (PERF-01, 05, 08). The cost is after the game:
scoring and anonymizing take about 52 s of CPU and slow the next game's engine meanwhile (PERF-06).

## How this changes the plan

| Finding | The decision it forces |
|---|---|
| DQ-01, ARCH-05, DQ-06, ARCH-09 | Before more estimator or scoring work: get one full Rift game with its timeline into the recordings repository, commit it as the replay fixture, and make the threshold test fail with no recording. The key metrics wait for it. |
| DQ-02, DQ-03, ARCH-06 | Next slice: ask for champion details once the scoreboard fills; read the loading-screen error as "no player yet"; tests from the real snapshot. |
| CMP-05, SEC-02, CMP-07 | Next slice that touches anonymizing or reports: search game-content keys for identities in client answers; scrub every known name and PUUID from reports, or leave out a log that still holds one. |
| SEC-01, SEC-03, CMP-03, CMP-04, CMP-09 | Gate the public download on these: a signed update channel (or owner-tagged releases only), hashed dependencies, Riot registration and notice, and a "What is kept and sent" section. Nothing changes while the owner is the only user. |
| CMP-01, CMP-02 | No change: the owner's settled decision (HANDOFF.md, "Settled") keeps the marks; the risk is recorded. |
| PERF-06 | Score and anonymize in a separate process, or after the client is idle; measure on the Mac first. |
| PERF-02, PERF-03, PERF-04, PERF-09 | No change now: under 5% of the budget. Revisit if a real game shows otherwise. |
| ARCH-02, ARCH-03, ARCH-04, ARCH-08 | Housekeeping, done when a slice touches the module: one atomic-write helper (ARCH-04) first, since it can lose a save. |
| CMP-06, DQ-07, DQ-08 | Deferred, with the reason in each area's file. |

## Security

Full findings: [audit/security.md](audit/security.md).

| Id | Severity | Finding | Response |
|---|---|---|---|
| SEC-01 | medium | Auto-update checks integrity, not authenticity, and installs without Gatekeeper | Signed checksums or Developer ID before a public download |
| SEC-02 | low | Problem-report logs are scrubbed with this run's names only, and fail open | Scrub every known name, or leave the log out |
| SEC-03 | low | The packaged engine's dependencies are pinned by version, not by hash | Hashes with `--require-hashes`, or bundled wheels |

## Performance

Full findings: [audit/performance.md](audit/performance.md). Measured in a Linux container on a
simulated 30-minute game; the Mac is not measured.

| Id | Severity | Finding | Response |
|---|---|---|---|
| PERF-01 | info | One answer costs about 20 ms late in a game, 4% of the poll | None |
| PERF-02 | low | The next-item guess scans the whole catalog per player per answer | Precompute per patch, when needed |
| PERF-03 | low | The event feed is rescanned from the start on every answer | Keep a cursor, when needed |
| PERF-04 | low | The engine computes on the event loop and then waits the whole poll | Wait the poll less the compute |
| PERF-05 | info | 24.7 kB pushed twice a second; the page's work is small | None |
| PERF-06 | medium | Scoring and anonymizing take about 52 s of CPU after each game and slow the engine | A separate process; measure on the Mac |
| PERF-07 | info | Recordings grow about 67 kB a minute plain, 24 times smaller in xz | None |
| PERF-08 | info | Memory stays under 2 MB over a game | None |
| PERF-09 | info | The engine and the recorder each ask the game for the same answer | Share one answer, when needed |

## Architecture

Full findings: [audit/architecture.md](audit/architecture.md).

| Id | Severity | Finding | Response |
|---|---|---|---|
| ARCH-01 | medium | The audit ran after the product | Findings are backlog items, each with a slice |
| ARCH-02 | low | The estimator layer imports the HTTP client and returns wire types | Move the records into a model module, deferred |
| ARCH-03 | low | A few large modules; the largest Swift file has no tests | Split when touched; move logic into OverlayCore |
| ARCH-04 | low | Concurrent saves of one file collide on the fixed `.partial` name | One atomic-write helper with `mkstemp` |
| ARCH-05 | high | The one real recording confirms only the pre-game resources | Record a full Rift game first (with DQ-01) |
| ARCH-06 | medium | The loading-screen `activePlayer` error becomes a blank player | Read it as "no player" (with DQ-03) |
| ARCH-07 | info | Enemy cooldowns are marked by the player, never read from the API | None |
| ARCH-08 | low | The TypeScript types mirror the schema by hand | Generate them, or test the mirror |
| ARCH-09 | low | The real-recording threshold test passes over zero recordings | Fail or skip with no recording |

## Data quality

Full findings: [audit/data-quality.md](audit/data-quality.md); the profile script,
[audit/data_profile.py](audit/data_profile.py), run on the real recording and on the one the tests
build: `uv run python docs/audit/data_profile.py <recordings directory>`.

| Id | Severity | Finding | Response |
|---|---|---|---|
| DQ-01 | critical | One real recording, cancelled at 0:00, confirms almost nothing | Record a full Rift game; it becomes the fixture |
| DQ-02 | high | The first answer is the loading screen, so champion details are never asked for | Ask once the scoreboard fills |
| DQ-03 | medium | The loading-screen `activePlayer` error validates as an empty player | Read it as "no player" |
| DQ-04 | medium | Missing fields become plausible values, hiding null rates | Keep "missing" distinct where it matters |
| DQ-05 | medium | The built test data disagrees with the real recording's shape | Replace the fixtures' shape with the real one |
| DQ-06 | high | The ground truth has never been seen in a real recording | The first full game confirms it |
| DQ-07 | low | The kill feed's name join is unconfirmed | The first full game confirms it |
| DQ-08 | info | The anonymized copy keeps the session's server address and spectator key | Drop them in the anonymizer |

## Compliance

Full findings: [audit/compliance.md](audit/compliance.md). Riot's own policy pages could not be
fetched here; the policy findings rest on search results.

| Id | Severity | Finding | Response |
|---|---|---|---|
| CMP-01 | high | Enemy ultimate marks are the feature Riot's 2025 rule names | Kept by the owner's decision; risk recorded |
| CMP-02 | medium | Hidden-information estimates sit in an unclear zone of that rule | Kept; read the primary page before a public download |
| CMP-03 | medium | The product is not registered with Riot | Owner's decision before a public download |
| CMP-04 | medium | No Riot notice in the app or its pages | Add before a public download |
| CMP-05 | medium | The anonymizer neither replaces nor searches game-content keys | Search them in client answers; test on a real recording |
| CMP-06 | low | Raw recordings with every player's Riot ID are kept forever | A retention setting, deferred |
| CMP-07 | low | The problem report's scrub misses PUUIDs and short names | Add the run's PUUIDs |
| CMP-08 | low | Claude's take keeps names out by its templates, not by a check | Refuse a line with a player name, deferred |
| CMP-09 | low | Automatic sending of games is not on the How to use page | Add "What is kept and sent" |

## Test-data defense

Every test uses built payloads (`tests/game_payloads.py`, `tests/recorded_games.py`) and hand-written
client fixtures (`tests/fixtures/`). They are safe: no real player is in them, and each is rebuilt
from code on every run, so they reproduce exactly. Their flaws become product failures where they
differ from a real game (DQ-05): one answer a minute, all keyframes, ten players from the first
answer and a full active player, so the loading screen (DQ-02, DQ-03), missing fields (DQ-04) and
the real shape of the ground truth (DQ-06) are never exercised. They cannot show whether any
estimator is accurate: that needs the owner's recorded games, scored against their timelines.
