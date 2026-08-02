# LeagueasyMode: Post-Mortem & Technical Retrospective

*Note: This repository is archived and no longer under active development. This document serves as the project's technical retrospective, design log, and architectural post-mortem.*

---

## Executive Summary

LeagueasyMode began as an experimental weekend project: a real-time, audio-first tactical telemetry engine for League of Legends Junglers. The goal was to offload macro calculations—such as recall deadlines, cannon wave crash timings, objective vision prep, and opponent power spikes—to a secondary "decoupled" HUD running on an external device (a mobile phone or Raspberry Pi kiosk).

The core technical experiment was two-fold:

1. Could I build a full-stack, low-latency telemetry application using AI pair programming ("vibe coding") without ever reading the official Riot API documentation?
2. Could I engineer an external, low-overhead secondary screen that bypassed the performance hits and screen clutter of traditional commercial desktop overlays?

Ultimately, the project reached a hard technical ceiling imposed by Riot's local API security boundaries. Combined with an upcoming personal PC hardware upgrade, the project achieved its educational goals and was gracefully archived.

---

## The Hardware Constraint: My 2020 Intel Mac

The catalyst for LeagueasyMode was a severe hardware bottleneck. I was playing on a 2020 Intel Mac. League of Legends taxes the CPU and GPU heavily on older Intel Mac hardware, especially when managing macOS CoreAudio pipelines under high load.

When I initially tested browser-based speech synthesis (`window.speechSynthesis`) and the Web Audio API directly on the host machine while playing, the system experienced severe audio buffer underruns. The result was digital static, popping, and a distorted "cackling" sound whenever an alert triggered.

This forced an architectural decision: **Hardware Decoupling**.

The host machine running League of Legends had to act purely as a headless data scraper. It could not render a GUI, and it could not process audio. The UI rendering and audio synthesis had to be offloaded entirely to a secondary client (a mobile browser or Raspberry Pi kiosk) hitting a local Flask server over the network.

---

## Architecture & Technical Engineering

```text
+---------------------------------------------------+
|                  PRIMARY MACHINE                  |
|  +--------------------+     +------------------+  |
|  | League of Client   |     |  Python Backend  |  |
|  | Local API (:2999)  | <-> |  (app.py / Flask)|  |
|  +--------------------+     +--------+---------+  |
+--------------------------------------|------------+
                                       | HTTP / JSON (Local Network)
                                       v
+---------------------------------------------------+
|                 SECONDARY DEVICE                  |
|  +---------------------------------------------+  |
|  |  Kiosk Browser (Phone / Pi)                 |  |
|  |  - Glassmorphic Telemetry HUD               |  |
|  |  - Web Audio API / TTS Priority Queue       |  |
|  +---------------------------------------------+  |
+---------------------------------------------------+

```

### 1. Slashing Latency: Connection Pooling

Initially, standard HTTP GET requests to Riot's local API (`[https://127.0.0.1:2999/liveclientdata/allgamedata](https://127.0.0.1:2999/liveclientdata/allgamedata)`) suffered from severe latency. Every iteration of the loop was initiating a new TLS handshake to port 2999. On macOS, these handshakes added 200ms–800ms per call.

By refactoring the backend to use a persistent `requests.Session()` with connection pooling and dropping the loop sleep interval to 0.1s, connection handshakes were reused. Polling latency dropped from ~1500ms down to ~10ms, allowing a stable 10Hz telemetry loop.

### 2. The Audio Queue Manager

To prevent overlapping audio, a synchronous queue worker was implemented in the frontend:

* **Priority Sorting:** Critical alerts (e.g., Level 6 power spikes, low HP) immediately bypass lower-priority alerts.
* **Staleness Expiration (`MAX_STALE_AGE`):** If a low-priority TTS alert waits longer than 1.5 seconds behind a long voice line, it is dropped. This prevents hearing stale information (like a recall prompt) seconds after the window has closed.
* **Rate-Limiting:** Visual cards and audio alerts are throttled to prevent stacked card collapses and speech overlapping.

### 3. Rule Engine Execution

The backend `EventBus` continuously evaluated game state snapshots against a modular rule manifest:

* **Pre-Match Cheese Check:** Evaluated opponent summoner spells at 0:15 for aggressive combat choices (Ignite/Exhaust) over TP/Flash.
* **Level 2/3 Priority:** Tracked XP deltas between laners to signal instant retreat when the opponent hit power spikes first.
* **Hard 8-Second Recall Deadline:** Calculated opponent death timers and walk-back times to signal the exact second a player must hit 'B' to avoid losing turret plates.
* **Cannon Wave Crash Windows:** Signaled cannon wave spawns 15 seconds prior to arrival at the enemy base, identifying optimal recall windows.

---

## The Realization: Local API vs. Overwolf GEP

As I moved into Phase 4 (Advanced Macro and Jungle Tracking), I attempted to implement features like precise jungle camp respawn tracking, camp sequencing, and minion wave state analysis.

This is where I hit a fundamental wall regarding how third-party tools access League of Legends data:

1. **Riot's Native Local API (Port 2999):** This is what LeagueasyMode used. It is local, lightweight, and completely detached from game memory. However, Riot intentionally cripples this API for competitive integrity. It hides minor jungle camp respawn timers, minion wave positions, and real-time team net worth.
2. **Overwolf's Game Events Provider (GEP) API:** Commercial apps (Blitz, Mobalytics, Porofessor) do not rely on port 2999. They are built on Overwolf, which has an official partnership with Riot allowing memory-level event hooks. The Overwolf GEP broadcasts exact minor camp states (`jungle_camp_0`, `alive: false`, `icon_status: 1`), exact minion kills, and real-time gold metrics.

I faced a choice:

* **Option A:** Rewrite the entire backend into Node.js/Electron and build a full Overwolf Desktop Application. This would give me perfect data, but it would completely destroy the lightweight, zero-bloat, secondary-screen nature of the project. I would end up building a worse version of Mobalytics.
* **Option B:** Stay on the local Flask API and rely on CS math heuristics (`+4 CS` delta tracking) to guess camp clears, which is inherently fragile and prone to desync.

---

## Post-Mortem & Conclusion

When evaluating whether to refactor the project for Overwolf, three realities became clear:

1. **The Niche Was Too Small:** The target audience for this tool—players who want a competitive macro coach, have a PC too weak to run Overwolf overlays, but possess the technical skill to host a local Python Flask server and connect a mobile device over LAN—is virtually non-existent.
2. **Hardware Upgrade:** I am upgrading my primary PC. The original hardware constraint (the 2020 Intel Mac struggling with CoreAudio and League simultaneously) will no longer exist, eliminating my own core use case for an external server.
3. **Reinventing the Wheel:** Commercial tools backed by engineering teams already handle Overwolf event parsing at scale. Continuing to reverse-engineer jungle camps via CS deltas was an exercise in diminishing returns.

### Accomplishments Summary

* **Engineered a 10Hz Local API Scraper:** Built a zero-lag TLS connection pool pulling real-time telemetry from port 2999.
* **Implemented Hardware-Decoupled Audio:** Solved Mac CoreAudio bottlenecking by offloading Web Audio and TTS synthesis to a secondary network client.
* **Built a Zero-Read HUD:** Designed a responsive, glassmorphic UI optimized for peripheral vision and color-coded state indicators.
* **Designed a Modular Macro Rule Bus:** Created isolated, state-aware rules for level spikes, recall windows, and objective prep.

### What I Learned

This project was a massive success as an educational exercise. I gained deep experience in backend event-bus architecture, connection pooling, browser speech synthesis queues, mobile wake-lock workarounds, and modern AI-assisted rapid prototyping ("vibe coding").

Recognizing when a project has served its learning purpose—and choosing to archive it rather than maintain a redundant tool—is a core part of engineering maturity.

---

## Final Project Status & Roadmap

| Feature / Module | Status | Notes |
| --- | --- | --- |
| **Persistent API Poller** | Completed | 10Hz, low-latency TLS connection pool |
| **Event-Bus Architecture** | Completed | Modular rule execution pipeline |
| **Decoupled Web HUD** | Completed | Single-file HTML5/JS UI with Web Audio/TTS |
| **NoSleep / Mobile WakeLock** | Completed | Solved display sleep over HTTP via video loop |
| **Rule: CheeseCheck** | Completed | Tracks aggressive opponent summoner spell choices |
| **Rule: RecallDeadline** | Completed | Calculates death-timer recall windows |
| **Rule: CannonWaves** | Completed | Tracks wave crash recall opportunities |
| **Rule: ObjectiveSync** | Completed | 120s/60s vision and prep timers |
| **Jungle Camp Sequencer** | Deprecated | Blocked by Local API limitations (requires Overwolf GEP) |
| **Wave Reader Matrix** | Deprecated | Blocked by Vanguard/Memory boundaries |
| **Champion Roster Rules** | Deprecated | Archived due to project sunset |
