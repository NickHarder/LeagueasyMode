"""The attester of the accuracy score (`docs/computations/accuracy-score.md`).

Provenance: the arguments the run received are the computation's, with each parameter filled into
its own word. Fidelity: the output the receipt names is the one the run wrote (its SHA-256), and
the claimed value is the score that output holds.
"""

import hashlib
import json
import shlex
from pathlib import Path
from typing import Final

SCRIPT_WORD: Final = "docs/computations/accuracy_score.py"
TOLERANCE: Final = 1e-9


def expected_arguments(computation: str, parameters: dict[str, object]) -> list[str]:
    """Return the arguments the computation passes its script, with the parameters filled in."""
    words = shlex.split(computation)
    after_script = words[words.index(SCRIPT_WORD) + 1 :]
    return [
        str(parameters[word[1:-1]])
        if word.startswith("{") and word.endswith("}") and word[1:-1] in parameters
        else word
        for word in after_script
    ]


def attest(
    *,
    computation: str,
    parameters: dict[str, object],
    receipt: dict[str, object],
    claimed_value: object,
) -> dict[str, object]:
    """Return whether the claimed value is the one the sanctioned run produced."""
    metric = "value"
    expected = expected_arguments(computation, parameters)
    if receipt.get("arguments") != expected:
        return {
            "ok": False,
            "reason": "the run's arguments are not the computation's",
            "details": {"expected": expected, "ran": receipt.get("arguments")},
        }
    output_file = Path(str(receipt.get("output_file", "")))
    try:
        output_bytes = output_file.read_bytes()
    except OSError as error:
        return {"ok": False, "reason": f"the output cannot be read: {error}", "details": {}}
    if hashlib.sha256(output_bytes).hexdigest() != receipt.get("output_sha256"):
        return {"ok": False, "reason": "the output is not the one the run wrote", "details": {}}
    produced = json.loads(output_bytes).get(metric)
    is_same = (
        isinstance(produced, int | float)
        and isinstance(claimed_value, int | float)
        and abs(float(produced) - float(claimed_value)) <= TOLERANCE
    )
    return {
        "ok": is_same,
        "reason": None if is_same else f"the run produced {produced}, not {claimed_value}",
        "details": {"metric": metric, "produced": produced},
    }
