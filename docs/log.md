# History

What changed in this project and why, newest first. A commit shows the difference; an entry here
gives the reason. The `handoff` skill adds to it at every checkpoint, and the `write-okf-concept`
skill has the format.

## 2026-10-08

- Phase 5.4, the You panel (estimator 13): which of armor, magic resist and health buys the most
  effective health per hundred gold against the enemy's damage mix, from your exact stats and the
  patch's basic items' prices; how long you have held 1,300 gold or more alive; and your creep
  score a minute against your recent games, for which the match history's minions and monsters
  and each game's length are now read. A panel on the left shows them.
- Phase 5.3, objective contests (estimator 11): for Dragon, the Elder and Baron up or within 0:30,
  the monster's 2026 health (patch 26.1's notes, unconfirmed) less a Smite over your living
  team's damage through its resistances, against each enemy's chance to reach the pit first,
  from the position filter's chances over the map (now exposed for this) or their respawn. The
  objective strip shows it; the harness scores it on your team's takes against whether the other
  team fought at the pit.
- Phase 5.2, fights (estimator 10): an even fight now, every living player at full health. Each
  player's damage a second, physical and magic, from their combat stats and Riot's rating of
  the champion's damage (Data Dragon's `info`, now read), and their effective health against
  the other team's mix; by Lanchester's square law the side with more damage times health wins,
  the chance a logistic of the ratio's logarithm. The enemy strip's header shows it with the
  enemy's damage mix; the harness scores it on the timeline's fights (kills close in time and
  place), against the team that lost fewer. The per-player combat stats helper moved into
  `combat_stats.py` for the fights and the harness to share.
- Phase 5.1, win chance (estimator 12): a logistic model over the gold lead as a share of the
  gold earned, levels, turrets, inhibitors, dragons, the soul, the Baron and Elder buffs, players
  alive and the side, with hand-set weights (a 2.5k lead at 15:00 wins about 3 in 4, as seasons 7
  to 10 did). The gold lead is an estimate with a band, so the chance is averaged over it. The
  enemy strip's header shows it with its two biggest reasons; the harness scores it against each
  game's result by its Brier score. Refit on recordings comes in 5.5.
- Phase 5's plan, a draft for the owner: win chance, fights, objective contests and the You panel,
  hand-set first and refit on recorded games, with four proposals where the owner decides. Phase
  4's pull requests (#17 to #20) are merged.
- Phase 4.6, the minimap layer: `leagueasymode run` reads League's own settings (`game.cfg`) for
  the minimap's scale and side, and draws there each enemy's likeliest region, the camps down and
  the enemy control wards. Regions, camps and wards now carry their place on the map. Its size
  against League's minimap is a first guess for the owner to check on the Mac. Phase 4 is built.
- Phase 4.5, control wards (estimator 9): a player's control ward count dropping while alive is a
  placement, placed where the position estimate likely has them then; one per player at a time,
  shown up to five minutes. The strip lists the enemies' latest. Scored against the timeline's
  placements, which record when but not where.
- Phase 4.4, the jungle path (estimator 8): each jungler's creep score bursts decoded into the
  camps that fit them (camp spawns and respawns, travel along the map, clear times), the likeliest
  path wasting the least time and staying in their own jungle. The respawn rule needs the whole
  path, so the decoding is a beam search rather than plain Viterbi. The enemy jungler's row shows
  their path and next camp; the strip shows the camps down and when each is back (dead camp
  timers, as the open policy allows). Scored by how far the timeline puts the jungler from each
  decoded camp.
- Phase 4.3, positions (estimator 7): where each player likely is, a chance for each of the
  map's points spread from their latest clue at their move speed and weighed by their role's
  habits. The plan named a particle filter; over 81 points the exact histogram filter does the
  same work without sampling noise, and its tests are exact. Each enemy unseen for 0:10 shows
  their likeliest region; the enemy unseen and away who could reach your lane soonest is called
  out as missing, at most once every 30 seconds. Scored against the timeline's positions.
- Phase 4.2, clues to positions: the moments the feed or the scoreboard pins a player's place
  (an objective's takers at it, a turret's victim at it, a respawn or trip to base in base,
  creep score in a lane or the jungle), each on the map. Each enemy's row shows the latest. The
  lookup of a player by the feed's name moved onto the game's snapshot, shared by gold and clues.
- Phase 4's plan, a draft for the owner: the map, the clues, positions (a particle filter), the
  jungle path, control wards and the minimap layer, with three proposals where the owner decides.
  Built on its best guesses meanwhile, as the owner asked.
- Phase 4.1, the map: a hand-built walkable graph of Summoner's Rift, the blue half written down
  and the red half its turn about the center, with shortest walks between any two points. Backs
  now take their way home from it, instead of a guessed distance per role. The scoring harness
  measures how far the timeline's positions lie from its paths.
- Phase 3.8, the build path (estimator 5): each player's likely next finished item, from the
  components they hold toward it, what they built on the champion in their recent games (the
  match history now keeps each game's items), and their champion's class (Data Dragon's tags);
  what is left to pay, the chance they hold it now, and when they will. An enemy who becomes
  likely to afford it is called out. Scored against the next finished item the timeline shows them
  buy. Phase 3 is built.
- Phase 3.7, backs (estimator 6): a purchase made alive is a trip to base, since buying needs the
  fountain (not the start's, a death's, or one just after respawning). Each enemy's row says when
  they went back and when they return, a walk from the fountain at their move speed; the enemy
  jungler's trips are called out, since the map rarely shows them. Scored against the timeline's
  purchases both ways.
- Phase 3.6, hidden experience (estimator 4): every player's experience, how far they are to
  their next level and when they reach 6, 11 and 16. Each level-up seen pins it; between them it
  grows at the player's own measured rate while they are alive, a prior by role until a level-up
  is seen. An enemy within 1:30 of a power level shows it on their row, and one sure to be within
  0:20 is called out. Scored against the timeline's experience for every player.
- Phase 3.5, hidden gold (estimator 3): each player's earned and unspent gold, exact for you and
  estimated with a band for the others. An income model with this season's numbers (patch 26.16's
  passive and minion gold, 25.9's bounties by level; the unconfirmed ones marked) is corrected by
  what the inventory proves: its cost is a floor, and the end of a shopping trip is weighed
  against the model as a Kalman filter weighs a measurement. Gold per creep is tuned live on your
  own exact gold, since it is the same for every laner and every jungler. The scoring harness
  scores it against the timeline's gold for every player but you, band included. The chance of
  affording the next item is worked out but shown with 3.8, which predicts the item.
- Phase 3.4, the scoring harness: `leagueasymode score <recording>` scores the role estimator (its
  positions hidden, against the game's own or its details') and the combat stats estimate (against
  the exact stats the game gives for the player on this machine) on a recorded game. The thresholds
  CI will hold them to wait for the first batch of recordings.
- The owner asked for the work to go on without waiting for merges: each slice gets its pull
  request into `main` as it is ready. Recorded in the handoff's settled points.
- Phase 3.3, suggestions: callouts that name an action when the facts line up (an objective in a
  numbers window, their jungler dead, a Flash or ultimate just marked, a Baron or Elder buff just
  taken), worded on a best guess for the owner to tune, text only. The callouts' docstring no
  longer says the overlay never instructs, since the owner's policy now allows it.
- Phase 3.2, marked cooldowns: ⌃⌥ and a digit picks an enemy in role order, then ⌃⌥ F, D or R
  marks their Flash, other summoner spell or ultimate; the engine times it from the patch's
  cooldowns, the enemy's level and their items' haste, shows it on their row and calls it out when
  it is back. A patch's Data Dragon files are now `championFull.json`, `item.json` and
  `summoner.json`. The macOS app's hot keys each check that a press is their own; before, with more
  than one, any press ran the first handler's action.
- The owner lifted the ask-before-push rule for this project: pushes and pull requests are free,
  deletions on GitHub and force pushes are not. Recorded in `AGENTS.md`, rule 1.
- Phase 3.1, loading-screen intel: each player's rank, recent record, streak, games on their
  champion and whether they are off-role, from the League client's own lookups, never a developer
  key. Each player is asked about once, one request at a time; the recorder keeps the answers to
  confirm their shapes, and shares them with the engine so the client is not asked twice. The
  replay now serves a recorded path with its query.
- Phase 3's plan approved by the owner, with their answers: the hotkey scheme as proposed,
  suggestions worded by best guess to iterate on, and other players' stats looked up through the
  League client's own session rather than a developer key, to keep clear of rate limits.
- Phase 3 planned in [plans/phase-3-economy-and-open-policy.md](plans/phase-3-economy-and-open-policy.md):
  the hidden economy from the approved plan, plus what the owner's open policy adds (loading-screen
  intel, cooldowns the player marks, suggestions), with the three that help from the first game
  proposed first.
- Pull requests #2, #3 and #4 merged; #3 and #4 went into the branches they were stacked on, so
  pull request #5 brings `feat/exact-facts`, which holds all of them, into `main`.
- The owner's answers: `truststore` stays; Data Dragon may be allowed in this environment's network
  settings; and the plan's decision 4, what may show during a game, is "everything": anything that
  can be calculated, estimated, derived, inferred or interpolated, where it is useful. Enemy
  ultimate and summoner spell timers and instructions to the player are no longer ruled out.
- This season's timers and phase 2.8 pushed and opened as pull request #4, stacked on #3.
- Phase 2.8, estimator 2: each player's combat stats, exact for the player on this machine and
  estimated for the others from their champion, level and items. The owner chose where champion
  base stats come from: Riot's Data Dragon, fetched by the engine once a patch and kept on disk.
  It is the overlay's one request beyond the Mac, said so in the README, and can be turned off.
  The engine now loads the patch's data at every game's start, so a patch day needs no restart.
- This season's spawn times confirmed by the owner: Voidgrubs 8:00, Herald 15:00, Baron 20:00, no
  longer marked "~". The Voidgrubs now leave at 14:45 and an untaken Herald at 19:45, 15 seconds
  before the next monster, as in past seasons; the browser test that showed the Herald up at 23:15
  now shows Baron up instead.
- Phase 2 pushed and opened as pull request #3, stacked on #2 so that its diff shows phase 2 alone.
- Phase 2 stands built but for structures, left out because League's own scoreboard shows tower
  counts and the lane naming is unconfirmed, and combat stats, which wait on the owner's choice of
  a source for champion base stats. The handoff and the phase 2 plan say where each slice is.
- Phase 2.7, estimator 1: each player's role where the queue gives none, by the assignment of
  least cost over Smite, the support item, summoner spells and CS rank, with a per-player
  confidence. A team-wide margin first made the only Smite user a "guess" when top and mid could
  swap; each player now has their own margin.
- Phases 2.4 and 2.5: the patch's item catalog, from the League client or from a replay that now
  serves the recorded client resources too; each player's item gold and finished items, each
  team's item gold, and a callout when an enemy finishes an item. Items already owned when the
  catalog arrives are not called out, which the first browser run showed was happening.
- Phase 2.3, callouts: short notices when an enemy reaches 6, 11 or 16, a numbers window opens,
  or an objective comes within a minute, each once per game and shown for six game seconds. They
  state facts; the policy keeps instructions out.
- Phase 2.2: each player's card (side, role, level, respawn) and the numbers window, shown as a
  pill at the head of the strip and an enemy strip on the right. The strip is now centered across
  the whole width, where before it was held to half the screen and wrapped its pills.
- Phase 2.1, the objective strip: Baron, Herald and Voidgrubs timers, each team's Baron and Elder
  buff, and inhibitors down, beside the dragon. This season's spawn times are provisional and
  marked so. Also fixed: shutting the server down waited up to 15 seconds for each page still
  listening; the streams now end at once.
- Phase 2's slices planned in [plans/phase-2-exact-facts.md](plans/phase-2-exact-facts.md), on
  `feat/exact-facts`, stacked on pull request #2 while it waits for review.
- Pushed and opened as pull request #2. CI's first run is green on all 10 jobs: the Swift app
  compiled on macOS 15 and its 9 unit tests passed, and the overlay page rendered in Chromium. The
  build's strict-concurrency warnings are noted in `HANDOFF.md` for the move to Swift 6.
- The tracer bullet's macOS side: a menu bar app in Swift (`overlay/macos/`) that starts the engine
  and shows the overlay page in a transparent, click-through window that never takes focus, with a
  ⌃⌥⌘L shortcut and a choice of window level for trying each League display mode. It is written but
  not yet compiled anywhere: this environment has no Swift, so CI's new macOS job is its first
  build. [references/macos-app.md](references/macos-app.md) has the steps for the test on a Mac.
- The tracer bullet's engine side: the dragon and Elder timer, from the game's answer through the
  engine and the local server to the overlay page, tested end to end against a replay and in
  Chromium. `leagueasymode run` and `leagueasymode replay` added;
  [references/engine-and-overlay.md](references/engine-and-overlay.md) describes them.
- Added the recorder (`leagueasymode record`) and anonymized copies (`leagueasymode anonymize`),
  described in [references/recordings.md](references/recordings.md). One change from the plan,
  which said "a standard-library-only recorder": the recorder is the engine's own client code,
  run with `uv run`, because uv sets up its dependencies in the same one command and the recorder
  and the engine then share one tested client of the game's API instead of two.
- Rebuilt from ai-kit v0.11.1 with the Python layer (no evals, demo or MCP layers). The first
  version's Flask HUD, rules and champion files are removed: the approved plan
  ([plans/overlay-and-inference.md](plans/overlay-and-inference.md)) starts the engine over and keeps
  nothing from the old rules by default. Its README is kept word for word as
  [history/first-version-retrospective.md](history/first-version-retrospective.md).
