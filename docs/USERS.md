---
type: Users
title: Users, moments and use cases
description: Who LeagueasyMode is for, the moments in a game when they reach for it, and the use cases each feature must serve, with who it refuses and what each use case beats.
tags: [users, personas, use-cases]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T06:25:12Z }
---

# Users, moments and use cases

Written from what the owner has said and shown while testing on the Mac (2026-10-08 to
2026-10-29). Fields the owner has not answered are marked **Open**, with the question asked;
nothing there is guessed.

## 1. The setting

One player, the owner, on one Mac, playing League of Legends with friends. No team, no staff, no
second screen: the overlay draws over League's own window, so every pixel it uses is taken from
the game. The engine runs on the same Mac and reads only League's local APIs (the game's on port
2999, the client's) and each patch's public stats from Data Dragon; it never reads the screen and
never sends input to the game (the owner, 2026-10-28: "i just dont thin screen recording and
camera vision is allowed"). Games, crash reports and problem reports go, anonymized, to the
owner's private repository, where a daily cloud session reads them.

## 2. Primary persona

### P-01: The player at the keyboard

- **Name and role:** the owner, a League of Legends player who plays to win and wants an edge
  the scoreboard does not give. Signs in to League with their Riot account; the app has no
  account of its own. On GitHub, `NickHarder`, owner of the app's repositories.
- **Setting:** alone, at a MacBook Pro (Apple silicon), League in **windowed** mode (1920 × 925
  seen on 2026-10-28), a Windows keyboard (⌃ is Ctrl, ⌥ is Alt, ⌘ is the Windows key). Plays with
  friends, in the same games or the same lobby.
- **Volume:** long sessions of quick queues: "I just played a ton of arams and switfplays"
  (2026-10-29). Seen: ARAM and its Mayhem, Swiftplay (on the Rift), Practice Tool; no ranked game
  seen yet. **Open:** how many games on a usual day (asked 2026-10-29).
- **A full day, by the clock:** evenings into the night, as far as seen: the app's own log has
  games and reports around midnight on the Mac's clock (UTC−5) on 2026-10-28 and 29. **Open:** a
  usual day. A game's own clock is known: champion select (about 1:30), loading (about 1:00),
  then 15 to 40 minutes of game, then the post-game screen.
- **Tools and screens today, in order:** the League client (lobby, champion select), the game
  window with League's own HUD (scoreboard on Tab, minimap bottom right, kill feed top right,
  ally portraits left, the champion bar bottom centre), then the post-game screen. Outside the
  game: the app's menu, its settings and status pages, and this chat to ask for changes. Knows
  the Overwolf apps: sent photos of Mobalytics' in-game "Player Overview" as the model for Tab
  (2026-10-29).
- **What they type and read:** in a game, almost nothing is typed but keys and chat; they read
  the HUD at a glance, a second or less at a time, and hold Tab for League's scoreboard. With the
  overlay: a glance at the timers and one line an enemy; Tab (or ⌥) for everything else; the ⌃⌥
  marks for an enemy's spells, ⌃⌥⌘L to hide and show, ⌃⌥⌘R to report.
- **Interruptions and environment:** the game is the interruption: a fight, a gank or an
  objective can start at any second. Eyes are on their champion; the edges of the screen get a
  glance. Friends talk in voice or chat. Sound from the game; spoken callouts are off unless
  turned on.
- **Trust posture:** wants exact facts stated flatly and estimates marked as such ("~", "?", a
  percentage); "I don't know" is fine, a wrong number said as fact is not. Distrusts rumour,
  their own words: "dont listen to rumors" (2026-10-28).
- **Tolerances:** a fact on screen must be at most a second or two behind the game (the engine
  asks every half second). The overlay must never take the mouse or the keyboard from the game
  outside edit mode; that cost a game on the first try and is never acceptable, nor is a click
  taken at all while they play ("it messes with my mouse", 2026-10-29). Too much on screen is a
  failure too: "so much info a lot of it is uselss 90% of the time"; "if it is goign to take my
  eyes off fights, it needs to be wort while info" (2026-10-29). An estimate may miss; a miss said
  as fact may not.
- **Must never be shown:** another player's name or Riot ID in anything sent off the Mac;
  anything read from the screen; a callout for what they just watched happen ("in a tf itll show
  the person die and then the next etc. its like i know"); the Rift's ideas on another map ("reset
  for obj even in aram"; "when in aram there is no bot jg top etc positions").
- **Authorization scope:** everything on their Mac: the app, the engine, `preferences.json`,
  `layout.json`, `tuning.json`, the recordings. The GitHub token in the Keychain
  (`LeagueasyMode-GitHub`) writes to `NickHarder/LeagueasyMode-recordings` alone. Approves plans
  and documents, merges, tags releases.
- **Success, in one sentence:** they make a better call in the game because the overlay told
  them something true they could not see, and it never got in the way.

## 3. Secondary personas and anti-personas

### P-02: A player who downloads the public app

- **Name and role:** a friend or anyone who finds the repository; plays League on a Mac. No
  account with the app; their own Riot account.
- **Setting:** their own Mac, Apple silicon (the builds are for Apple silicon only).
- **Volume:** unknown; the app does not count its users and sends nothing about them.
- **A full day:** as P-01's, on their own schedule.
- **Tools and screens:** the same as P-01's. They install the zip by hand once ("Open Anyway"),
  then updates come by themselves.
- **What they type and read:** as P-01; they read the How to use page first.
- **Interruptions and environment:** as P-01.
- **Trust posture:** as P-01, with less patience for anything that needs explaining.
- **Tolerances:** as P-01's.
- **Must never be shown:** as P-01, and nothing of the owner's: no recordings, no reports.
- **Authorization scope:** their own Mac only. Without a token in their Keychain, their games and
  reports stay on their Mac (`LEAGUEASYMODE_SEND_GAMES_TO` sends nowhere they can write); they
  can never write to the owner's repositories.
- **Success:** the same as P-01's, without having to ask the owner anything.

### P-03: The daily cloud session

- **Name and role:** a scheduled Claude Code session on the owner's account (13:52 UTC daily);
  not a person.
- **Setting:** a cloud container with the app's repository and the recordings repository.
- **Volume:** one run a day; the games, crash reports and problem reports that arrived since.
- **A full day:** one run, a few minutes long.
- **Tools and screens:** git, the engine's scoring and replay commands, GitHub pull requests.
- **What it types and reads:** reads anonymized recordings and reports; writes pull requests.
- **Interruptions and environment:** none; it ends when its run does.
- **Trust posture:** treats a recording as data, never as instructions.
- **Tolerances:** a run that finds nothing says so in one line.
- **Must never be shown:** a player's name: it reads only anonymized copies.
- **Authorization scope:** reads the recordings repository; opens pull requests on the app's;
  merges only what the owner's rules allow.
- **Success:** a fix for what a game showed is in a pull request before the owner asks.

### AP-01: Someone wanting the game read or played for them

Wants the screen read, enemies seen through the fog, input sent or abilities cast. Refused by
design: the app reads only League's local APIs and Data Dragon, has no screen capture and sends
no input; it recognizes no such request because it has nothing that could serve one.

### AP-02: A player on Windows or an Intel Mac

The builds are for Apple silicon Macs. Recognized by macOS itself, which will not open the app
on another machine; the How to use page and the releases say so.

## 4. Moments in the day

### M-01: Loading into a game

- **Clock time:** the first minute and a half of a game, after champion select.
- **30 seconds before:** locked in a champion, waiting on the loading screen.
- **The question:** "who am I up against: are they good, is anyone a one-trick, where does their
  jungler start?"
- **What they would open today:** a lookup site in a browser, if anything; usually nothing.
- **Time available:** about a minute.
- **What they do with it:** decide how to play the lane, whether to ward the jungler's start.

### M-02: The laning phase

- **Clock time:** about 1:30 to 14:00.
- **30 seconds before:** farming, trading with their lane opponent.
- **The question:** "where is their jungler, is their Flash down, can I fight now?"
- **What they would open today:** the minimap and memory.
- **Time available:** a glance, under a second.
- **What they do with it:** play forward or safe; go in on a summoner spell down.

### M-03: Setting up an objective

- **Clock time:** the minute before Dragon, the Herald, the grubs or Baron spawns.
- **30 seconds before:** moving with the team, warding.
- **The question:** "when does it spawn, and can they contest?"
- **What they would open today:** the scoreboard (Tab) and their memory of who died when.
- **Time available:** a few seconds.
- **What they do with it:** set up, or give it and take something else.

### M-04: Right after a fight

- **Clock time:** any time after a team fight.
- **30 seconds before:** fighting.
- **The question:** "how long are they down, what can we take?"
- **What they would open today:** the scoreboard's death timers.
- **Time available:** two or three seconds.
- **What they do with it:** take an objective, push, or reset.

### M-05: Before a game, setting the overlay up

- **Clock time:** in the client, between games, or in the first seconds of a game.
- **30 seconds before:** a game ended, or the overlay sat over part of League's HUD.
- **The question:** "can I put this where it does not cover anything, at a size I can read?" (the
  owner, 2026-10-29: "can i move the overlay somehow? drag it to move it or use sliders for x and
  y postion or resize it?")
- **What they would open today:** the menu's Edit layout, which moves but cannot resize.
- **Time available:** a minute between games; seconds in a game.
- **What they do with it:** play the next games with that layout.

### M-06: Something looks wrong

- **Clock time:** any time.
- **30 seconds before:** playing, when the overlay showed something odd or nothing.
- **The question:** "how do I tell you without writing an essay?"
- **What they would open today:** this chat, with a screenshot.
- **Time available:** a key press in a game; a minute after.
- **What they do with it:** press ⌃⌥⌘R and keep playing.

### M-08: Dead, or holding Tab

- **Clock time:** any time the player is dead (10 to 60 seconds), or holds Tab for the scoreboard.
- **30 seconds before:** a fight they lost, or a quiet moment in lane.
- **The question:** "who is ahead, who is good on their champion, which lane is winning?"
- **What they would open today:** League's scoreboard (Tab): items, KDA and creep score, no rank,
  no record, no lane-by-lane gold; or an Overwolf app's overview.
- **Time available:** the whole death timer; a second or two on Tab.
- **What they do with it:** decide where to go when they respawn, whom to help, whom to avoid.

### M-07: After the game

- **Clock time:** the post-game screen.
- **30 seconds before:** the game ended.
- **The question:** "how did it go, minute by minute, and what swung it?"
- **What they would open today:** the client's post-game stats.
- **Time available:** a minute or two.
- **What they do with it:** queue again, a little wiser, or roast a friend.

## 5. Use cases

No eval suite exists yet (`evals/`): each use case names the tests that guard it today, and the
key metric that proves it ([KEY_METRICS.md](KEY_METRICS.md)), where one can be measured. A metric
is scored from the post-game timeline, so it has no value until the owner's games are scored.

### UC-01: Who are they

- **Moments:** M-01, M-08.
- **Questions:** each player's rank, recent record, games and win rate on this champion, whether
  it is their main or a one-trick, a streak; where their jungler usually starts and is at 4:00;
  which lane is ahead in item gold.
- **Data and where it lives:** the League client's match history and ranked stats (phase 9).
- **Required latency:** on screen before the camps spawn (1:30).
- **What a wrong answer costs:** a lane played too safe or too greedy; the player's.
- **Why this and not the alternative:** a lookup site needs a browser, the names typed, and
  minutes; League's scoreboard has no rank or record; an Overwolf app's overview does not run on a
  Mac. Here it is the Tab overview, both teams side by side, on Tab or while dead.
- **Refusal behaviors:** an enemy the client has no games for shows nothing, not a guess; never
  a bare "Unranked" after 3:00.
- **Several turns or chained tools:** no.
- **Guarded today by:** `tests/test_player_intel.py`, `tests/test_jungle_starts.py`, the browser tests of
  rank and record and of the Tab overview.
- **Metric:** none of its own: rank and record are the client's, exact. The jungler's habit
  feeds [DR-02](metrics/DR-02.md).

### UC-02: Where is their jungler, and who is roaming

- **Moment:** M-02.
- **Questions:** where the enemy jungler likely is; which laner is likely away from their lane.
- **Data and where it lives:** the game's API (creep score, items, kills), estimators 7 and 8.
- **Required latency:** within a second of the game's answer.
- **What a wrong answer costs:** a gank walked into, or a play not made; the player's.
- **Why this and not the alternative:** the minimap shows only what is in sight; this marks the
  likely place of who is not.
- **Refusal behaviors:** no circle for an enemy in sight, or for a laner in lane with "jungler
  and roamers only".
- **Several turns or chained tools:** no.
- **Guarded today by:** `tests/test_positions.py`, `tests/test_jungle_path.py`, the minimap
  browser tests.
- **Metric:** [DR-02](metrics/DR-02.md), the enemy jungler's path against the timeline.

### UC-03: Is their spell down

- **Moment:** M-02.
- **Questions:** when the enemy's Flash, other summoner spell or ultimate is back; their
  ultimate's rank.
- **Data and where it lives:** the player's mark (⌃⌥ keys or a click), the patch's cooldowns,
  the enemy's level and items.
- **Required latency:** the timer starts within a second of the mark.
- **What a wrong answer costs:** a fight taken into a Flash that was up; the player's.
- **Why this and not the alternative:** memory, or a chat ping, which counts down nowhere.
- **Refusal behaviors:** no mark before the patch's cooldowns are known (the engine answers 409);
  no rank shown for an ultimate ranked another way.
- **Several turns or chained tools:** two keys, or one click.
- **Guarded today by:** `tests/test_cooldowns.py`, `tests/test_click_to_mark.py`, the mark
  browser tests.
- **Metric:** none: a mark is the player's, and its timer the patch's cooldown, exact.

### UC-04: Can we take it

- **Moments:** M-03, M-04.
- **Questions:** when each objective spawns; how long the enemies are down; whether they can
  contest.
- **Data and where it lives:** the game's event feed and death timers; estimators 10 and 11.
- **Required latency:** within a second; the minute-before callout on time.
- **What a wrong answer costs:** an objective given or a team caught; the team's.
- **Why this and not the alternative:** the scoreboard has death timers but not spawn times, and
  needs Tab held.
- **Refusal behaviors:** off the Rift, no Rift timers; one callout per fight, after it, with at
  least two enemies down.
- **Several turns or chained tools:** no.
- **Guarded today by:** `tests/test_objectives.py`, `tests/test_callouts.py`,
  `tests/test_contests.py`, the strip's browser tests.
- **Metric:** [DR-04](metrics/DR-04.md), the contest calls against what happened.

### UC-05: Fight or not

- **Moments:** M-02, M-04.
- **Questions:** who wins an even fight now; the gold and item lead.
- **Data and where it lives:** combat stats from Data Dragon and the game's API; estimator 10.
- **Required latency:** within a second.
- **What a wrong answer costs:** a lost fight; the team's.
- **Why this and not the alternative:** the scoreboard's items, summed in the head mid-game.
- **Refusal behaviors:** no fight chance with fewer than two alive on a side.
- **Several turns or chained tools:** no.
- **Guarded today by:** `tests/test_fights.py`, `tests/test_win_chance.py`.
- **Metric:** [DR-03](metrics/DR-03.md), the fight calls against the fights that followed.

### UC-06: The overlay where I want it, at a size I can read

- **Moment:** M-05.
- **Questions:** put each widget where it covers nothing of League's HUD; make it bigger or
  smaller; see the game through it.
- **Data and where it lives:** `layout.json` beside the preferences; League's window bounds.
- **Required latency:** a drag or a slider shows its result as it moves.
- **What a wrong answer costs:** part of the HUD hidden for a whole game, or text too small to
  read at a glance; the player's.
- **Why this and not the alternative:** a fixed layout that covers the kill feed. Now: drag and
  resize in Edit layout, exact sliders in Settings, see-through backgrounds, a widget turned off,
  League's HUD shaded and kept clear.
- **Refusal behaviors:** a widget is never placed off League's window nor left on League's HUD;
  the overlay takes no click at a glance.
- **Several turns or chained tools:** a few drags or slider moves, once.
- **Guarded today by:** `tests/test_layout_page.py`, `tests/test_settings_page.py`,
  `tests/test_layout.py`.
- **Metric:** [GR-02](metrics/GR-02.md), problem reports a game, guards it: the overlay in the
  way is what a report says.

### UC-07: Tell the developer in one press

- **Moment:** M-06.
- **Questions:** none asked of the player; the report says what the app saw.
- **Data and where it lives:** the engine's log, the status page, the game so far; sent to the
  recordings repository.
- **Required latency:** made and sent within a few seconds.
- **What a wrong answer costs:** a fault that cannot be found; the owner's.
- **Why this and not the alternative:** a screenshot and a paragraph in this chat.
- **Refusal behaviors:** nothing with a player's name or a home folder in it is sent.
- **Several turns or chained tools:** no.
- **Guarded today by:** `tests/test_problem_report.py`, `tests/test_sender.py`.
- **Metric:** [GR-01](metrics/GR-01.md), engine crashes a game, counted from what it sends.

### UC-08: How did the game go

- **Moment:** M-07.
- **Questions:** the game minute by minute; what swung it; a line to roast a friend.
- **Data and where it lives:** the recording and the client's post-game timeline.
- **Required latency:** the window ready when the post-game screen is.
- **What a wrong answer costs:** a wrong lesson; the player's.
- **Why this and not the alternative:** the client's post-game screen gives totals, not the
  turning points.
- **Refusal behaviors:** nothing about a player outside the game.
- **Several turns or chained tools:** no.
- **Guarded today by:** `tests/test_game_summary.py`, the summary page's browser tests, the roast
  tests.
- **Metric:** [DR-01](metrics/DR-01.md), games scored: no game recorded and sent, no game to tell.

### UC-09: Only what holds on this map

- **Moments:** M-02, M-04, M-08, on ARAM, its Mayhem, Arena and Swiftplay.
- **Questions:** the same as on the Rift, less what does not exist there: no lanes, no jungle, no
  epic monsters, no recall in ARAM.
- **Data and where it lives:** the game's `mapNumber` (11 is the Rift; 12 is ARAM; 30 Arena).
- **Required latency:** from the first answer of the game.
- **What a wrong answer costs:** noise that teaches the player to ignore the overlay ("reset for
  obj even in aram"); the player's.
- **Why this and not the alternative:** the Rift's overlay shown everywhere.
- **Refusal behaviors:** off the Rift, no roles, no Rift timers but the inhibitors' (marked "~"
  until a recorded ARAM game confirms their respawn time), no team call about objectives or a
  reset, no estimate tuned on the Rift.
- **Several turns or chained tools:** no.
- **Guarded today by:** `tests/test_other_maps.py`, the off-the-Rift browser tests,
  `tests/test_roast_team_calls.py`.
- **Metric:** [NS-01](metrics/NS-01.md) counts its games; the drivers are Rift-only.

### Considered and cut

- **A callout for each death in a fight:** the player saw it happen ("its like i know").
- **Every line on every enemy row, all game:** "useless 90% of the time"; kept behind "Detailed
  enemy rows".
- **Spell casts detected by themselves:** the game's local API reports no enemy cast; revisit if
  a recording shows a field that does.
- **Reading the screen for vision or cooldowns:** the owner rules it out (AP-01).
- **Enemy camp respawn timers by default:** the plan's caution on Riot's 25.17 change; off.
- **Every detail on screen all game:** behind Tab or ⌥ since 2026-10-29 ("maybe extra details
  onyl show if i hit tab"); "Details only while Tab or ⌥ is held" off brings them back.

## 6. Traceability

| Use case | Persona | Moments |
|---|---|---|
| UC-01 | P-01, P-02 | M-01, M-08 |
| UC-02 | P-01, P-02 | M-02 |
| UC-03 | P-01, P-02 | M-02 |
| UC-04 | P-01, P-02 | M-03, M-04 |
| UC-05 | P-01, P-02 | M-02, M-04 |
| UC-06 | P-01, P-02 | M-05 |
| UC-07 | P-01, P-03 | M-06 |
| UC-08 | P-01, P-02 | M-07 |
| UC-09 | P-01, P-02 | M-02, M-04, M-08 |

## 7. The demo

To be written against a real recorded Rift game once one has arrived in the recordings
repository: the only recording so far is a Practice Tool game cancelled at 0:00.
