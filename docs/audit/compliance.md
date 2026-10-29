---
type: Audit Area
title: "Compliance"
description: Where LeagueasyMode stands against Riot's third-party policies, what personal data of other players it keeps and sends, what reaches a model provider, and what a user can see of it.
tags: [audit, compliance]
status: draft
generated: { by: claude-code/claude-opus-5-5, at: 2026-10-29T06:42:58Z }
sources:
  - id: riot-general-policies
    resource: https://developer.riotgames.com/policies/general
    title: Riot Developer Portal, General Policies (last updated March 11, 2025, per search result; the page could not be fetched from this session)
  - id: riot-lol-policy
    resource: https://support-developer.riotgames.com/hc/en-us/articles/22698698001939-League-of-Legends
    title: Riot Developer Relations, League of Legends policy (game integrity section, as quoted by search)
  - id: bo3-ult-ban
    resource: https://bo3.gg/lol/news/riot-games-has-banned-companion-apps-from-tracking-enemy-ultimates-timers
    title: bo3.gg, Riot bans companion apps from tracking enemy ultimate timers (secondary)
  - id: lolnow-overlays
    resource: https://lolnow.gg/riot-cracks-down-on-overlays-in-league-of-legends-a-long-overdue-clean-up/
    title: lolnow.gg, Riot cracks down on overlays (secondary, on the May 29, 2025 update)
  - id: riot-ljj
    resource: https://riotgames.com/legal-jibber-jabber
    title: Riot Games, Legal Jibber Jabber
  - id: anonymize
    resource: ../../src/leagueasymode/recording/anonymize.py
  - id: sender
    resource: ../../src/leagueasymode/recording/sender.py
  - id: problem-report
    resource: ../../src/leagueasymode/problem_report.py
  - id: crash-reports
    resource: ../../src/leagueasymode/crash_reports.py
  - id: claude-take
    resource: ../../src/leagueasymode/roast/claude_take.py
  - id: player-intel
    resource: ../../src/leagueasymode/player_intel.py
  - id: config
    resource: ../../src/leagueasymode/config.py
  - id: how-to-use
    resource: ../../src/leagueasymode/overlay_web/how-to-use.html
---

# Compliance audit

**This audit is late.** The skill expects it before any product code exists; here the engine, the
macOS app, recording, sending and Claude's take are already built. Each finding below describes
the code as it stands and was checked against it. The owner's settled decisions (`HANDOFF.md`,
"Settled") are recorded as facts with their risk, not reopened.

**Limits of the evidence.** Riot's own policy pages (`developer.riotgames.com`,
`support-developer.riotgames.com`) and the secondary articles did not resolve from this cloud
session (DNS blocked); their content below comes from web-search result text, and the hosts must be
allowed in the session's network settings to quote them first-hand. Nothing in the app has met a
real game yet (`HANDOFF.md`, "Known limitations"), so the payload shapes are the test fixtures'.

Evidence run: `uv run pytest -q tests/test_anonymize.py tests/test_problem_report.py
tests/test_claude_take.py tests/test_sender.py` → `44 passed in 2.50s`.

## What the app shows, against Riot's rules

### [CMP-01] Enemy ultimate marks are the feature Riot's 2025 rule names
- **Severity:** high
- **Location:** `src/leagueasymode/inference/cooldowns.py:1-23`; `src/leagueasymode/overlay_web/how-to-use.html:100` ("that enemy used their ultimate") and `:154` (enemy strip shows each enemy's R rank and the marked cooldowns)
- **Reproduction:** web search "Riot Games League of Legends third party app policy 2025 ultimate timers Overwolf removed"; `grep -n "ultimate" src/leagueasymode/inference/cooldowns.py`
- **Impact on the project:** Secondary reports say Riot banned third-party tracking of enemy ultimate timers from March 13, 2025, covering **manual as well as automatic** tracking, and deactivated the API keys of apps that did not comply.[^bo3-ult-ban] A report on the May 29, 2025 overlay update lists "ultimate trackers with real-time cooldowns" as no longer allowed, while summoner spell and jungle camp timers stay allowed because they have set cooldowns.[^lolnow-overlays] Riot's game-integrity text, as quoted in search, says products must not use information not present in the game client that gives a competitive edge, with enemy ultimate cooldowns as its example.[^riot-lol-policy] The app's manual ⌃⌥…R marks count down an enemy ultimate's cooldown, so they fall inside that wording. The manual Flash and summoner marks fall on the allowed side by the same reports. The search found nothing on what Overwolf itself removed. LeagueasyMode holds no Riot API key, so key deactivation is not the lever; the exposure is to the account of whoever runs it (Vanguard/ToS enforcement is not documented for overlays, and was not verified) and to a public download being named against policy.
- **Mitigation:** Deferred by the owner's settled decision (2026-10-28: the marks stay). Recorded risk: **high** for a public download, lower for personal use. Revisit only if the owner reopens it.

### [CMP-02] Hidden-information estimates sit in an unclear zone of the same rule
- **Severity:** medium
- **Location:** `src/leagueasymode/inference/gold.py`, `src/leagueasymode/inference/jungle_path.py`; `how-to-use.html:152-158` (items' gold, where the jungler likely is)
- **Reproduction:** web search "developer.riotgames.com policies league of legends game integrity overlay enemy cooldown ultimate information not available to player"
- **Impact on the project:** The quoted rule forbids "information not present in the game client".[^riot-lol-policy] Enemy gold and the jungler's likely position are inferred from what the local game API exposes, which is a different case from reading memory, but the rule's wording is about advantage, not source. No search result rules on estimates either way. Jungle camp timers are reported as allowed.[^lolnow-overlays]
- **Mitigation:** Deferred under the settled "everything is allowed" decision. Before the public download, read the primary page first-hand (host to allow: `developer.riotgames.com`) and record the exact wording here.

### [CMP-03] The product is not registered with Riot
- **Severity:** medium
- **Location:** repository-wide; `README.md:6-7` (only Data Dragon is named as Riot's)
- **Reproduction:** `grep -rniI "developer portal\|register" docs HANDOFF.md README.md` → no registration; web search "Riot developer policies League Client API LCU live client data API products must be registered approval"
- **Impact on the project:** The General Policies, as quoted, say a product that serves players must be registered "regardless of whether or not your product uses official documented APIs", and that a product using the League Client API registers through the Developer Portal; new features are audited on the product's page.[^riot-general-policies] A public download that reads the client's API (`player_intel.py:34-46`: ranked stats, match history and timelines of every player in the game) is such a product. Registration would also put CMP-01 in front of Riot's review.
- **Mitigation:** An owner decision before the public download: register (and accept that review), or keep the app personal. Not settled in `HANDOFF.md`.

### [CMP-04] No Riot notice anywhere in the app or its pages
- **Severity:** medium
- **Location:** `src/leagueasymode/overlay_web/how-to-use.html`, `README.md`, `overlay/macos/Sources`
- **Reproduction:** `grep -rniI "endorse\|jibber\|riot games" src overlay/macos overlay/web/src README.md` → one hit, a lockfile path (`league_client.py:26`); no notice
- **Impact on the project:** The app shows Riot IP (champion and item names and stats from Data Dragon, `data_dragon.py:26`). The Developer Portal policies require boilerplate saying the product is not endorsed by Riot and does not reflect Riot's views, where players can readily see it.[^riot-general-policies] The Legal Jibber Jabber policy asks fan projects for a notice that the project was made under it and that Riot does not endorse or sponsor it.[^riot-ljj]
- **Mitigation:** Add the notice to the How to use page and the app's About before the public download. A text change; no owner decision it contradicts.

## Other players' personal data

### [CMP-05] The anonymizer neither replaces nor searches game-content keys, so a name there passes
- **Severity:** medium
- **Location:** `src/leagueasymode/recording/anonymize.py:46-60` (`GAME_CONTENT_FIELDS` includes `name`, `displayName`, `description`), `:248` and `:270-277`
- **Reproduction:** a probe run with `uv run python` from the repository root, with `tests/` on `sys.path`: `src = write_source_recording(d, extra_payload={"displayName": name, "name": name})` (from `tests/test_anonymize.py`, `name = DEFAULT_PLAYERS[1].riot_id_game_name`), then `anonymize_recording(src, d / "a.jsonl")` and search the decompressed copy for `name` → `player name: 'Jungle Diff' | still in anonymized copy: True`
- **Impact on the project:** The module promises to fail closed: any identity left anywhere stops the copy.[^anonymize] The exemption for game content is deliberate (a player named like a champion), but it also exempts these keys from the leak search, so the promise does not hold for them. The League client uses `displayName` for players in some of its answers; whether the recorded paths (gameflow session, ranked stats, match history, timelines) do was not verifiable without a real game. If one does, that player's name goes to the games' repository.
- **Mitigation:** A later slice: search exempt keys for leaks in client resources (where champion text is rare), or exempt them only in the game API's payloads; a test with a real recording's client answers.

### [CMP-06] Raw recordings, with every player's Riot ID, PUUID and match history, are kept forever
- **Severity:** low
- **Location:** `src/leagueasymode/config.py:36-42` (`~/Library/Application Support/LeagueasyMode/recordings`); `player_intel.py:35-46` (ranked stats, the last 20 games and timelines of each player, recorded by `cli.py:180`); `sender.py:13-15`
- **Reproduction:** `grep -rn "unlink\|rmtree\|retention\|delete" src/leagueasymode --include=*.py` → only temporary and partial files are removed (`writer.py:188`, `sender.py:148`, `anonymize.py:199`, `data_dragon.py:834`, `cli.py:756`); nothing deletes a raw recording, sent or not
- **Impact on the project:** Each game leaves on the Mac the Riot IDs and PUUIDs of nine other people and their recent match histories, with no end date. Only the anonymized copy leaves (`sender.py:355-383`), and only with a GitHub token (`sender.py:281-287`: "games stay on this Mac"). `sent-games.json` holds recording names (times), not players. For a public download, every user keeps the same on their Mac without being told (CMP-08).
- **Mitigation:** Explicit deferral: the owner needs raw games for scoring. A later slice can add a retention setting (for example, delete raw recordings once sent and scored).

### [CMP-07] The problem report's scrub covers names from the game's scoreboard only
- **Severity:** low
- **Location:** `src/leagueasymode/problem_report.py:37-41`, `:71-107`
- **Reproduction:** `uv run python -c "...scrub('GET /lol-ranked/v1/ranked-stats/puuid-gank-0000 for Gank Plz and Jo', player_identities({...}), Path('/Users/x'))"` → `GET /lol-ranked/v1/ranked-stats/puuid-gank-0000 for [player] and Jo`
- **Impact on the project:** The note and the log tails are scrubbed of summoner names and Riot IDs from `allPlayers` and of the home folder.[^problem-report] PUUIDs, names under 3 characters, friends' Riot IDs and names seen only in client answers stay. At the default `INFO` level the engine logs no client path (`league_client.py:273` logs at `debug`, error type only), so a PUUID reaches the log only through an exception message (`crash_reports.py:143` logs `exc_info`) or a note the player types. Crash reports themselves carry no message (`crash_reports.py:84-101`). The game in the report goes through the anonymizer, so CMP-05 applies to it too.
- **Mitigation:** Low cost: add the PUUIDs of the run to the scrubbed identities. Deferred to the next slice touching reports.

## What goes to a model provider

### [CMP-08] Claude's take sends wording and style only, off by default; names are kept out by the templates, not by a check
- **Severity:** low
- **Location:** `src/leagueasymode/roast/claude_take.py:52-77` (prompt; `enabled: bool = False`), `:88-116` (`slot_out`), `:216-224` (`claude -p`, prompt on stdin); `tests/test_claude_take.py:133-147`
- **Reproduction:** `uv run pytest -q tests/test_claude_take.py` (in the 44 passed); `grep -rn '{name}\|{opponent\.name}' src/leagueasymode/roast/*.toml` → no template uses a player-name slot
- **Impact on the project:** With the setting on, the owner's `claude` command (their own login, so Anthropic under the owner's account terms) receives: the fixed rules text, the owner's style (at most 200 characters), and the approved chat line with every champion name and number replaced by `{c1}`/`{n1}`.[^claude-take] The test asserts no champion name or number follows `Line:`. Player names are absent because the line templates (`moments.toml`, `team_calls.toml`, `templates.toml`) carry champions, not players; `slot_out` does not look for player names, so a future template with `{name}` would send one. Answers that add a capitalised name are refused (`:146-148`). Nothing about Claude's take leaves the Mac when it is off or the command is missing (`:281-282`).
- **Mitigation:** Optional hardening: pass the game's player names to `slot_out` and refuse to send a line holding one. Deferred; the current templates make it a latent risk only.

## Audit logging and what the user can see

### [CMP-09] Sends are logged and visible; the automatic sending of games is not on the How to use page
- **Severity:** low
- **Location:** `sender.py:52`, `:431-458` (status lines); `overlay_web/status.js:58`; `overlay/macos/Sources/LeagueasyOverlay/AppDelegate.swift:747` ("Open engine log"); `how-to-use.html:224-227`; `config.py:210` (`send_games_to` defaults to the owner's repository)
- **Reproduction:** `grep -niI "send\|github\|anonym\|record" src/leagueasymode/overlay_web/how-to-use.html` → only the problem report is described as sent (`:224-227`)
- **Impact on the project:** A user can see what left: `sent-games.json` lists each game sent or withheld and each crash and report file sent;[^sender] the status page says how many were sent and to which repository, or that games stay on the Mac without a token; the engine log keeps three files (`engine.log`, `.1`, `.2`; `OverlayCoreTests.swift:825`) and opens from the menu. Missing: the How to use page says nothing about recording every game, keeping it, or sending games and crash reports automatically. For the owner this is known; for a public user nothing is sent without a token, but the default target is the owner's repository, so a user given a token would send there.
- **Mitigation:** Add a "What is kept and sent" section to the How to use page alongside the notice of CMP-04. No owner decision blocks it.

## Footnotes

[^riot-general-policies]: Riot Developer Portal, General Policies
[^riot-lol-policy]: Riot Developer Relations, League of Legends policy
[^bo3-ult-ban]: bo3.gg on the March 2025 ultimate-timer ban
[^lolnow-overlays]: lolnow.gg on the May 29, 2025 overlay update
[^riot-ljj]: Riot Games, Legal Jibber Jabber
[^anonymize]: `src/leagueasymode/recording/anonymize.py`, module docstring
[^problem-report]: `src/leagueasymode/problem_report.py`, module docstring and `scrub`
[^claude-take]: `src/leagueasymode/roast/claude_take.py`
[^sender]: `src/leagueasymode/recording/sender.py`, `SentLog`
