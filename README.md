# LeagueasyMode

A macOS overlay for League of Legends that works out what the scoreboard hides, using only League's
local APIs. It reads the game's own API on `127.0.0.1:2999` and the League client's local API, and
nothing else: no screen capture, no game memory, no web services.

**Status:** being rebuilt. The plan is [docs/plans/overlay-and-inference.md](docs/plans/overlay-and-inference.md);
where the work stands is in [HANDOFF.md](HANDOFF.md). The first, archived version (a second-screen
Flask HUD) is described in [docs/history/first-version-retrospective.md](docs/history/first-version-retrospective.md).

## Record your games

Every estimator is built and scored against recorded games, so recording comes first. On the Mac you
play on, with [uv](https://docs.astral.sh/uv/) installed:

```bash
git clone https://github.com/NickHarder/LeagueasyMode.git && cd LeagueasyMode
uv run leagueasymode record
```

Leave it running and play. It waits for a game, records it, and after the game saves the match
timeline the League client provides. Recordings go to `~/Library/Application Support/LeagueasyMode/recordings/`
and stay on your Mac; `uv run leagueasymode anonymize <recording>` makes a copy with every player's
name replaced, which is the only kind that goes into this repository.

## Develop

```bash
make bootstrap    # once per clone
make gate         # everything a push must pass
uv run leagueasymode replay <recording> --speed 10    # a recorded game, served as a stand-in game API
LEAGUEASYMODE_GAME_API_BASE_URL=http://127.0.0.1:2998 LEAGUEASYMODE_LEAGUE_CLIENT_BASE_URL=http://127.0.0.1:2998 \
  uv run leagueasymode run   # the overlay, against it
```

How the engine, the overlay page and its widgets fit together is in
[docs/references/engine-and-overlay.md](docs/references/engine-and-overlay.md).

`AGENTS.md` has the working rules, and `docs/index.md` what the project knows.
