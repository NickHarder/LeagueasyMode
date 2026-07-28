# Building LeagueasyMode Without Reading the Docs (An AI-Driven Experiment)

## 1. Introduction: The Vibe Coding Era

Welcome to modern software engineering, where the primary qualification is knowing how to talk to a robot while staring blankly at a blinking cursor. Why spend precious hours reading API documentation, studying rate limits, or understanding architectural best practices when you can just manifest a full-stack Flask application through pure conversational bluffing?

This is the birth story of **LeagueasyMode**—a high-end, role-specific tactical telemetry cockpit designed for a Raspberry Pi kiosk. It polls the local Riot Live Client Data API at 10Hz to feed your ears audio-first tactical alerts instead of cluttering your screen. The catch? I built the entire thing without ever opening a single page of official documentation. And trust me, it went about as smoothly as a first-time Yasuo in your ranked promos.

---

## 2. Why Your Mac "Cackles" (The Hardware Bottleneck)

If you tested the dashboard directly in a browser on your Mac while League was running, you ran right into a classic hardware bottleneck. League of Legends consumes massive amounts of CPU/GPU resources and hooks heavily into macOS CoreAudio. When you layer browser-based speech synthesis (`window.speechSynthesis`) and the Web Audio API on top of an already stressed Mac running a full-screen game, the audio buffer underruns. This results in that digital static, popping, and demonic "cackling" sound.

This is the exact justification for our hardware-decoupled architecture: your Mac should never render the UI or touch the audio engine. Offloading this entirely to the Raspberry Pi and its dedicated portable monitor keeps your Mac completely silent and focused strictly on running the game.

---

## 3. The Tech Stack & The Blind Spots: Pros & Cons of Zero-Doc AI Development

* **The Stack:** Python, Flask, a 10Hz loop hitting the local Riot Live Client Data API (`[https://127.0.0.1:2999/liveclientdata/](https://127.0.0.1:2999/liveclientdata/)`), and a browser-based Web Audio/TTS engine running on a secondary Raspberry Pi kiosk.
* **The Pro (Ludicrous Speed):** Bootstrapping a server, handling self-signed SSL handshake certificates, and spitting out clean Flask boilerplate happens at the speed of thought. You skip the tedious setup phase entirely and jump straight into feeling like a hacker in a movie.
* **The Con (The Reality Check):** Building completely blind means you find out about architectural roadblocks only *after* you slam face-first into them. For instance, discovering mid-way through development that Riot intentionally hides live team gold and net worth server-side for competitive integrity. Cue a sudden, dramatic pivot to item component costs and pacing deltas because the API straight-up refuses to give us the numbers we want.

---

## 4. Engineering Around API Constraints & Failed Architectural Attempts

When you don't read the manual, you learn the hard way what developers are actually allowed to do and what hardware will tolerate.

### Failed Attempt 1: Native macOS Notifications (`osascript & afplay`)

* **The Bug:** macOS aggressively suppresses notification banners when an external monitor is used in clamshell mode (laptop closed) or a full-screen game is running.
* **The Audio Mess:** Shell commands fire asynchronously. If two alerts triggered simultaneously (e.g., a chime and a voice callout), they played over each other in a garbled mess.
* **The Polling Lag:** Standard Python HTTP requests required a TLS handshake for every loop. Every loop iteration was firing four separate `requests.get()` HTTPS calls to `127.0.0.1:2999`. Without a persistent connection session, Python was forced to open, negotiate SSL/TLS handshakes, and tear down four TCP connections per second. On macOS, those handshakes alone took 200ms–800ms per loop, and combined with `time.sleep(1.0)`, your actual loop cycle was lagging up to 2 seconds behind real-time.

### The Fix for Polling Lag:

We initialize a persistent `requests.Session()` with connection pooling and drop the loop sleep to 0.1s (10 FPS polling). Polling latency drops from ~1500ms down to ~10ms.

### Failed Attempt 2: The GUI Overlay (`Tkinter` / `PyQt`)

* **The Apple Silicon Bottleneck:** Forcing a transparent, always-on-top Python window over a high-refresh-rate Metal application (League) nukes Mac performance. It causes micro-stutters.
* **The Window Manager:** macOS "Spaces" frequently isolate full-screen apps, hiding the overlay anyway.

### The Ban Hammer Reality (Chat Automation):

My initial million-dollar idea was simple: have the app automatically type strategic callouts into team chat. Turns out, Riot has this little thing called "Terms of Service" that strictly prohibits third-party tools from automating chat inputs or actions. Automated chat injection is a one-way ticket to a permanent ban, so we kept it strictly read-only and passive.

---

## 5. The Hardware Decoupling & The "Sim-Racer" Setup

* **Realization:** The Mac shouldn't render the UI or process the audio. It should only be the data scraper.
* **Solution:** Built a lightweight Flask local web server. The Python engine uses a persistent HTTP `requests.Session()` (dropping polling latency from ~1500ms to ~10ms).
* **The Final Hardware Stack:** A Raspberry Pi connected to a portable monitor, booting directly into Chromium Kiosk Mode (full-screen, no desktop). It hits the Mac's local IP (`[http://192.168.](http://192.168.)x.x:5000`).
* **Why it wins:** 0% FPS impact on the Mac. The browser handles a synchronous Web Audio/Speech API queue so voice lines play back-to-back perfectly.

---

## 6. Solving the Audio Overlap and Notification Clutter

* **Notification Collapse Fix (Rate Limiter & Priority Queue):** macOS groups notifications when too many arrive quickly. To fix this, we built an async Notification Queue Manager. Visual macOS banners are rate-limited to a minimum 3.0-second gap so macOS never collapses them into stacked cards.
* **Custom Audio Chime Library:** Instead of generic beeps, the script hooks directly into native sound systems. Every alert type has its own distinct chime (Glass, Hero, Submarine, Ping, Tink, Basso). You can recognize what happened just by listening.
* **Synchronous Queue Worker:** Inside the background worker thread, audio elements run sequentially without background amp overlapping. This forces audio to play cleanly back-to-back in exact chronological order without overlapping.
* **Staleness Drop (`MAX_STALE_AGE`):** If a low-priority chime sits in the queue behind a longer voice callout for more than 1.5 seconds, the engine automatically discards its voice line. This guarantees you never hear an 8-second recall warning 4 seconds late.
* **Priority Sorting:** Emergency alerts (e.g., Low HP / Level 6 Spikes) jump to the front of the queue ahead of lower-priority item buys or CS checks.

---

## 7. Design Philosophy & Dynamic Objectives

* **Design Philosophy:** "Zero Redundancy & High Contrast." The UI mimics a Grafana dashboard or stock terminal—dark backgrounds, monospace fonts for jitter-free timers, strict color-coding. Rule design: The game already yells "PENTAKILL" and shows objective graphics. This tool only tracks hidden Master+ macro windows that require manual tab-checking or mental math.
* **Dynamic Objectives & Clutter Reduction:** Seeing a 20-minute timer for Baron when you're sitting at 3 minutes in lane is useless visual noise. We redesigned the Macro Objectives panel:
* **Early/Mid Game Focus:** It prioritizes Dragon and Void Grubs (which spawn at 5:00).
* **Dynamic Reveal:** Rift Herald and Baron Nashor automatically hide themselves or stay grayed out with clean status tags until the game clock actually approaches their spawn windows (Herald at 14:00, Baron at 20:00).



---

## 8. The "LeagueasyMode" Rules Engine

These are the strict tactical rules the Python engine evaluates 10 times a second:

### Pre-Game & Early Lane (0:00 – 3:00)

* **Pre-Match Cheese Check (0:15):** Scrapes the direct lane opponent's summoner spells. If they took Ignite, Exhaust, or Barrier instead of Teleport/Flash, it triggers a "Cheese Risk" alert.
* **Level 2 & 3 Priority Tracker:** Constantly compares your XP level to your direct opponent. If they hit Level 2 or Level 3 before you do, an instant critical chime fires to back off.
* **Early Scuttle Sync (2:35):** Alerts that Scuttles are spawning in 20 seconds (at 2:55) to prep jungle pathing or lane priority.
* **Level 1 Ward Expiration (2:50):** Assumes standard 1:20 ward placements. Level 1 Yellow Trinkets last exactly 90 seconds, so a 2:50 alert signals that the map is dark and early gank windows are wide open.

### Mid-Game Macro & Lane Management

* **Hard 8-Second Recall Deadline:** (Tracks direct opponent only). If the enemy laner dies, it watches their respawn timer. Exactly at the 8.0s mark, it alerts you. This is the absolute deadline to start your recall if you want to base and get back to lane without losing plates.
* **Cannon Wave Crash Windows (Pre-15 mins):** Cannon waves spawn every 90 seconds (2:05, 3:35, 5:05...). The engine pings you 15 seconds before a cannon wave spawns at the enemy base. This is the optimal Master-tier window to crash your wave and recall.
* **Bounty Shutdown Tracker:** Scans the enemy team for high-net-worth targets. If an enemy accumulates a 700g+ bounty, it fires a tactical alert to shift the team's win-condition focus to shutting them down.

### Objectives & Late Game

* **120-Second Vision Prep:** Alerts 2 minutes before a Dragon or Baron spawns. This is the exact macro window required to base, buy Control Wards, and walk to the river to establish a choke point.
* **60-Second Coinflip Check:** 1 minute before Dragon/Baron, it checks if the enemy Jungler is alive or dead. If alive, it warns of a "Coinflip Risk." If you are the Jungler, it adds a reminder to save Smite.
* **Inhibitor 60s Rally Warning:** Tracks destroyed inhibitors. Exactly 4 minutes after destruction, it warns that the inhibitor respawns in 60 seconds (at the 5:00 mark) so you can rally the team to push.
* **Hyper-Carry Level 16 Timebomb:** Monitors late-game scaling threats (Kayle, Kassadin, Smolder, Vayne, Vladimir). When they hit Level 16, a critical alert fires, signaling the enemy team has hit their ultimate power spike.

---

## 9. Implementation Roadmap

* **Phase 1: Local Foundation:** Setup of project environment, clean directory structure, and requirements dependencies.
* **Phase 2: The Core Engine (`app.py`):** Writing the Python backend using a persistent HTTP session, implementing the Master+ rule set, and exposing JSON data via Flask (`/api/state`).
* **Phase 3: The Telemetry Dashboard (`templates/index.html`):** Building the responsive single-file CSS/JS frontend layout, Grafana-inspired aesthetic, and browser-based Web Audio/Speech API queue handlers.
* **Phase 4: Raspberry Pi Kiosk Deployment:** Configuring the Raspberry Pi OS to boot directly into Chromium's Kiosk Mode, auto-loading the Mac's local IP address on startup.
* **Phase 5: GitHub Packaging:** Cleaning up the project codebase for open-source distribution with a robust `README.md` and `.gitignore`.

---

## 10. Conclusion: Lessons Learned from the Vibe Coding Frontier

Can you build a functional, highly specialized real-time telemetry tool completely through AI conversation without ever cracking open a documentation file? Absolutely.

Does it make for a wildly entertaining engineering process full of blind optimism and sudden architectural panic? You bet. While skipping the docs means you will inevitably step on rakes that could have easily been avoided, it also forces you to invent clever hardware-decoupled workarounds you would never have thought of otherwise.