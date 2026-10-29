---
type: Audit Area
title: "Security"
description: What the overlay's local server, its TLS to League, its GitHub token, its anonymization, its auto-update, its Claude call and its web view expose, each probe run against the code as it stands.
tags: [audit, security]
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T06:44:11Z }
---

# Security audit

**This audit is late.** The audit gate is meant to come before any product code exists. Here the
engine (`src/leagueasymode`), the macOS app (`overlay/macos`) and the release pipeline already
ship, so the findings below describe live code. They are not constraints on a design that is still
to come.

Scope: the seven probes in the brief. Every reproduction was run in this repository on
2026-10-29, and the output quoted is what came back. The probes that hold are listed first. The
three findings follow.

## Probes that hold

| # | Probe | Result |
|---|---|---|
| 1 | Local overlay server: bind, Host check, CSRF, CORS | **Holds.** See below. |
| 2 | TLS to the game (2999) and the League client | **Holds.** Riot's root is pinned, and verification is never turned off. |
| 3 | GitHub token never logged or written; no secret in the history | **Holds.** |
| 4 | Anonymization of sent games fails closed | **Holds** for games. Problem reports fail open (SEC-02). |
| 5 | Auto-update checks the archive before installing | Integrity only, not authenticity (SEC-01). |
| 6 | `claude` CLI call: what is sent, injection | **Holds.** |
| 7 | WKWebView: native bridges, remote pages | **Holds.** |

**1. Overlay server.** `cli.py:246` binds `web.TCPSite(runner, LOCAL_HOST, …)` with
`LOCAL_HOST = "127.0.0.1"` (`cli.py:112`). The middleware `_refuse_other_hosts`
(`overlay_server.py:434`) refuses any Host header other than `127.0.0.1` or `localhost`, which
stops DNS rebinding. Each route that changes state needs `X-LeagueasyMode-Request` set to its own
value. Those routes are `POST /marks`, `/report` and `/games/send`, and `PUT /preferences`,
`/layout`, `/friends` and `/claude-take`. The server sends no `Access-Control-*` header and does not
answer `OPTIONS`, so a cross-site page cannot get past the preflight that the custom header
triggers. A probe ran the real `create_overlay_application` through aiohttp, using the test
helper `tests/local_servers.serve`:

```
GET /state Host=evil.example:1234           -> 403
GET /state Host=127.0.0.1.evil.example      -> 403
OPTIONS /preferences (preflight, evil origin) -> 405, no Access-Control-Allow-Origin
PUT /preferences, POST /marks, /games/send, /report without the header -> 403
GET /state Origin=https://evil.example      -> 200, no Access-Control-Allow-Origin (unreadable cross-site)
```

What remains is local: any process on the Mac can send the header. That is within the threat
model, because the user who runs that process already owns these files.

**2. TLS.** `riot_tls.py:47` trusts Riot's "LoL Game Engineering Certificate Authority" alone,
with `CERT_REQUIRED`. Hostname checking is off because both servers are on 127.0.0.1, so the
signature does the work. The embedded PEM's SHA-256 matches the fingerprint in the docstring:
`uv run python -c "…hashlib.sha256(ssl.PEM_cert_to_DER_cert(p))…"` printed
`CA:8C:9D:32:…:4E:A3`. Searching `src` and `overlay` for `CERT_NONE|ssl=False|verify=False|_create_unverified`
finds nothing. `tls_context=None` appears only for an `http://` stand-in (`cli.py:490`), and
`game_api.py:95` and `league_client.py:265` then fall back to `ssl=True`, which is default
verification, never to no verification.

**3. Secrets.**
- The token is read with `security find-generic-password … -w`. The call is an argument list,
  with no shell (`recording/sender.py:109`). The token is used only in the `Authorization` header
  (`sender.py:402`).
- The token is never written to disk, the status page or a problem report. A grep of every
  `logger`, `_note`, `write_text` and status string that mentions "token" finds only fixed text.
- `bash scripts/secrets_scan.sh --all` printed `secrets: no leaks found in 137 commits`. That is
  every non-merge commit (`git rev-list --all --no-merges | wc -l` printed 137).
- Separately, `git log --all -p | grep -E "gh[pousr]_…|github_pat_…|sk-ant-…|AKIA…|BEGIN … PRIVATE KEY"`
  matched nothing.
- The bare `secrets_scan.sh` scans only the range a push would send. Here it printed
  `nothing to scan`, which is correct but is not a scan of the history.

**4. Anonymization.** `uv run pytest -q tests/test_anonymize.py tests/test_problem_report.py`
printed `11 passed in 1.15s`. Sent games fail closed: on `IdentityLeakError` the sender withholds
the game (`sender.py:375`), and the problem report leaves the game out (`problem_report.py:221`).
Crash reports leave out the error's message by design (`crash_reports.py:8`). The logs inside a
problem report are scrubbed by plain string replacement, and that path fails open (SEC-02).

**6. `claude` CLI.** `roast/claude_take.py:218` uses `asyncio.create_subprocess_exec` with an
argument list and no shell. The prompt goes in on standard input. What is sent is the approved
gameplay line, with every champion name and number taken out into `{c1}`/`{n1}` slots
(`slot_out`), plus the owner's style text. The style is capped at 200 characters
(`claude_take.py:75`). No player name is sent. The feature is off by default (`enabled: bool = False`).
`model` is passed as a separate argument after `--model` and can be set only from the
header-guarded settings page. Residual risk: a model value that begins with `--` reaches the CLI's
own option parser. Passing it as `--model=<value>` would close that. No finding was raised,
because only the local owner can set the value.

**7. WKWebView.** The page gets exactly two message handlers: speech
(`SpeechBridge.swift:7`, which speaks a validated string) and click regions
(`OverlayPanel.swift:59-66`, which takes validated rectangles). It gets no file, shell or URL
bridge.
- The app loads only the URL the engine announces, and `EngineAnnouncement.swift:25-26`
  requires `http` and host `127.0.0.1`.
- The pages have no HTML sinks: `grep -rnE "innerHTML|insertAdjacentHTML|outerHTML|document\.write|eval\(|new Function" src/leagueasymode/overlay_web | wc -l`
  printed `0`. Player and champion names therefore cannot inject markup.
- There is no navigation policy delegate (`decidePolicyFor`), so a link in the page would
  navigate in place, and the two handlers would answer that page too. The bundled pages contain
  no such links today. A `decidePolicyFor` that allows only `http://127.0.0.1` is cheap
  hardening, and is noted here rather than raised as a finding.

## Findings

### [SEC-01] Auto-update proves integrity, not authenticity, and installs without Gatekeeper
- **Severity:** medium
- **Location:** `overlay/macos/Sources/LeagueasyOverlay/UpdateInstaller.swift:42-75`;
  `overlay/macos/Sources/OverlayCore/BuildUpdate.swift:73-82`; `.github/workflows/ci.yml:243-247`;
  `overlay/macos/scripts/build_app.sh:94-96`
- **Reproduction:**
  `timeout 30 gh api "repos/NickHarder/LeagueasyMode/releases?per_page=1" --jq '.[0] | {tag: .tag_name, prerelease, assets: [.assets[].name]}'`
  printed `{"assets":["LeagueasyMode-0.1.0-build-197.zip","LeagueasyMode-0.1.0-build-197.zip.sha256"],"prerelease":true,"tag":"build-197"}`.
  The archive and its checksum are assets of the same release.
  `grep -n -E "codesign|shasum" .github/workflows/ci.yml overlay/macos/scripts/build_app.sh`
  shows `shasum -a 256 "$archive" > "$archive.sha256"` next to `gh release create`, and
  `codesign --force --sign - "$app"`, which is an ad hoc signature with no identity.
- **Impact on the project:**
  - The SHA-256 check guards against a corrupted download, which HTTPS already prevents. It does
    not guard against a malicious release, because whoever can publish the zip publishes its
    checksum too.
  - `codesign --verify --strict --deep` passes any internally consistent ad hoc signature,
    because no designated requirement or team identity is checked.
  - The app downloads the update itself, so the file carries no quarantine flag and opens without
    Gatekeeper's prompt (`UpdateInstaller.swift:9-10`).
  - Every CI build of `main` is published as a `build-*` prerelease that installed apps offer to
    install.
  - Together, anyone with `contents: write` on `NickHarder/LeagueasyMode` can run code on every
    Mac that clicks "Install update", with no warning from macOS. That includes a leaked
    workflow token or a compromised Action in the build job.
- **Mitigation:** do this before the app is offered beyond the owner (persona P-02 in
  `docs/USERS.md`).
  - Sign each release's checksum with a key the owner keeps outside GitHub, such as minisign or
    Ed25519 through CryptoKit, and pin the public key in the app.
  - Or sign with a Developer ID and verify with
    `codesign --verify -R '=anchor apple generic and certificate leaf[subject.OU] = "<TEAM>"'`.
  - Until then, consider offering only owner-tagged releases (`release.yml`) and not every `main`
    build.

### [SEC-02] Problem-report logs are scrubbed with this run's names only, and fail open
- **Severity:** low
- **Location:** `src/leagueasymode/problem_report.py:92-107` (`scrub`) and `:153-161`;
  `src/leagueasymode/cli.py:342`; `src/leagueasymode/engine.py:541`
- **Reproduction:**

  ```
  cd /home/user/leagueasymode && uv run python - <<'EOF'
  import datetime, tempfile; from pathlib import Path
  from leagueasymode.problem_report import make_problem_report
  from leagueasymode.engine_status import StatusBoard
  root = Path(tempfile.mkdtemp()); (root / "logs").mkdir()
  (root / "logs/engine.log").write_text("error: input_value='Bo'\n")
  (root / "logs/engine.1.log").write_text("error: input_value='PlaceholderRival#NA1'\n")
  report = make_problem_report(recordings_directory=root / "rec", note="", app_facts={},
      status_report=StatusBoard(home_directory=root).report(), engine_log=root / "logs/engine.log",
      identities={"Bo"}, home_directory=root, now=datetime.datetime.now(datetime.UTC))
  for name in ("engine-log.txt", "previous-engine-log.txt"):
      print(name, "->", (report / name).read_text().strip())
  EOF
  ```

  This printed `engine-log.txt -> error: input_value='Bo'` and
  `previous-engine-log.txt -> error: input_value='PlaceholderRival#NA1'`. Both names survive.
- **Impact on the project:**
  - The identities come from `engine.seen_identities`, which holds only the names in this run's
    game-API answers. `previous-engine-log.txt` comes from the run before, so it is scrubbed with
    the wrong set. After a restart, that set is empty.
  - Names the engine learns from the League client (player lookups in `player_intel.py`, the
    friends list) are never in the set.
  - Names shorter than 3 characters are never replaced (`SHORTEST_SCRUBBED_NAME`).
  - The engine log does carry error messages. `ErrorReporter.report` logs with
    `exc_info` (`crash_reports.py:143`), and pydantic's `ValidationError` includes
    `input_value=…`, as a probe in this audit showed. A third party's Riot ID can therefore reach
    the owner's private repository inside a report, unlike a game, which is withheld when a name
    cannot be removed.
  - Exposure is limited: the report is user-initiated and goes to a private repository the owner
    controls.
- **Mitigation:**
  - Scrub both logs with the union of this run's names, the League client's names, and the names
    in the newest recording.
  - Or treat log tails like games: put a log in a report only if no `Name#TAG`-shaped string
    remains, and otherwise leave it out and say so in `report.json`.
  - Add a test with a previous-run name.

### [SEC-03] The packaged engine's dependencies are pinned by version, not by hash
- **Severity:** low
- **Location:** `overlay/macos/scripts/build_app.sh:63-64`;
  `overlay/macos/Sources/OverlayCore/EngineCommand.swift:68-71`
- **Reproduction:**
  `grep -n -iE "constraint|requirements|hash" overlay/macos/scripts/build_app.sh` printed
  `uv export --frozen --no-dev --no-emit-project --no-hashes …` writing `constraints.txt`.
  `EngineCommand.swift` runs `uv tool run --from <wheel> --constraints constraints.txt`, which
  resolves and downloads the dependencies from PyPI on the user's Mac at first start.
- **Impact on the project:** the downloaded files are checked against nothing the build recorded.
  PyPI forbids re-uploading a file name, but a maintainer, or an attacker holding a maintainer's
  account, can add a new wheel (another platform tag) to a version that is already pinned. Such a
  wheel would be installed and would run with the user's privileges, without any change in this
  repository.
- **Mitigation:** export with hashes and install with `--require-hashes`. Alternatively, bundle the
  resolved wheels inside the app, which also removes the network need at first start. This can be
  deferred while the only user is the owner.

## Not covered

- macOS entitlements, sandboxing, and the Keychain item's access control list were not checked:
  there is no Mac in this environment.
- The CI workflows' third-party Actions are pinned by SHA, but their permissions were not audited
  beyond the release job's `contents: write`.
