"""One estimator's score over the newest games of the accuracy history, weighed by their samples.

The computation behind the key metrics DR-02, DR-03 and DR-04 (`docs/KEY_METRICS.md`). It reads
`accuracy-history.jsonl` (`src/leagueasymode/accuracy_history.py`), whose lines name a recording
file, a game id, a version and the scores, never a player. It writes the result as JSON, and a
receipt for `make attest`: the arguments, the output's path and its SHA-256.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Final

DEFAULT_OUTPUT: Final = Path("evals/out/accuracy-score.json")
DEFAULT_RECEIPT: Final = Path("evals/out/receipt.json")


def score(history: Path, estimator: str, last: int) -> dict[str, object]:
    """Return the estimator's sample-weighed mean over its newest `last` games, and how many."""
    try:
        lines = history.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    found: list[tuple[int, float]] = []
    for line in lines:
        try:
            game = json.loads(line)
        except ValueError:
            continue
        for entry in game.get("scores", []):
            if entry.get("estimator") == estimator and entry.get("sample_count", 0) > 0:
                found.append((int(entry["sample_count"]), float(entry["value"])))
    newest = found[-last:]
    sample_total = sum(samples for samples, _ in newest)
    return {
        "estimator": estimator,
        "games": len(newest),
        "samples": sample_total,
        "value": (
            sum(samples * value for samples, value in newest) / sample_total
            if sample_total
            else None
        ),
    }


def main() -> int:
    """Score, write the result and the receipt, and return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--estimator", required=True)
    parser.add_argument("--last", type=int, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    arguments = parser.parse_args()
    output = json.dumps(score(arguments.history, arguments.estimator, arguments.last), indent=2)
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
