# Audit Area

* [Architecture](architecture.md) - How the engine, the widgets and the macOS app are layered, where each file on the Mac is written, which League APIs the code relies on and which of them a real recording has confirmed, and how the engine-to-page contract is held.
* [Compliance](compliance.md) - Where LeagueasyMode stands against Riot's third-party policies, what personal data of other players it keeps and sends, what reaches a model provider, and what a user can see of it.
* [Data quality](data-quality.md) - How much of what the estimators assume about the game's and the League client's answers is confirmed by real recordings, where the built test data disagrees with them, and what that leaves unproven.
* [Performance](performance.md) - Measured cost of the engine's answer, the overlay stream, the page, the recording and the after-game send round, against the 0.5 s poll and the player's machine.
* [Security](security.md) - What the overlay's local server, its TLS to League, its GitHub token, its anonymization, its auto-update, its Claude call and its web view expose, each probe run against the code as it stands.

# Files

* [data_profile.py](data_profile.py)
