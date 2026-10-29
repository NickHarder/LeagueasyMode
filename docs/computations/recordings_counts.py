"""Count what reached the recordings repository in a window: games, crash reports, problem reports.

The computation behind the key metrics DR-01, GR-01 and GR-02 (`docs/KEY_METRICS.md`). It reads
only file names, which hold the time each was made and nothing about any player:

    games/game-<YYYY-MM-DDTHH-MM-SSZ>-anonymized.jsonl.xz
    crash-reports/crash-<YYYY-MM-DDTHH-MM-SSZ>-<n>.json
    reports/report-<YYYY-MM-DDTHH-MM-SSZ>/

It writes the counts as JSON, and a receipt for `make attest`: the arguments it was run with, the
output's path and its SHA-256.
"""

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Final

TIME_PATTERN: Final = re.compile(r"(\d{4}-\d{2}-\d{2})T\d{2}-\d{2}-\d{2}Z")
DEFAULT_OUTPUT: Final = Path("evals/out/recordings-counts.json")
DEFAULT_RECEIPT: Final = Path("evals/out/receipt.json")
TEN_GAMES: Final = 10


def made_on(name: str) -> datetime.date | None:
    """Return the day a file name says it was made, or None when it says none."""
    found = TIME_PATTERN.search(name)
    return datetime.date.fromisoformat(found.group(1)) if found else None


def count_in(folder: Path, since: datetime.date, until: datetime.date) -> int:
    """Return how many entries of a folder were made from `since` up to, not including, `until`."""
    if not folder.is_dir():
        return 0
    days = [made_on(entry.name) for entry in folder.iterdir()]
    return sum(1 for day in days if day is not None and since <= day < until)


def counts(recordings: Path, since: datetime.date, until: datetime.date) -> dict[str, object]:
    """Return the window's counts, and the rates the guardrails read."""
    games = count_in(recordings / "games", since, until)
    crash_reports = count_in(recordings / "crash-reports", since, until)
    reports = count_in(recordings / "reports", since, until)
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "games": games,
        "crash_reports": crash_reports,
        "reports": reports,
        "crashes_per_game": crash_reports / games if games else None,
        "reports_per_ten_games": reports * TEN_GAMES / games if games else None,
    }


def main() -> int:
    """Count, write the counts and the receipt, and return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recordings", type=Path, required=True)
    parser.add_argument("--since", type=datetime.date.fromisoformat, required=True)
    parser.add_argument("--until", type=datetime.date.fromisoformat, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    arguments = parser.parse_args()
    output = json.dumps(counts(arguments.recordings, arguments.since, arguments.until), indent=2)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(output + "\n", encoding="utf-8")
    receipt = {
        # Only the arguments the computation names; where the output and receipt go is not one.
        "arguments": sys.argv[1:7],
        "output_file": str(arguments.out),
        "output_sha256": hashlib.sha256(arguments.out.read_bytes()).hexdigest(),
    }
    arguments.receipt.parent.mkdir(parents=True, exist_ok=True)
    arguments.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(output + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
