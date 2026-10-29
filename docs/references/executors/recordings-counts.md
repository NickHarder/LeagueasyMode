---
type: Executor
title: Running the recordings counts
description: How to run the recordings counts against a clone of the recordings repository, and the receipt a run hands back.
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T07:08:19Z }
---

# Running the recordings counts

1. Clone or update the recordings repository (it is private; the owner's account reads it).
2. Run the computation with the parameters filled in, from the repository's root:

       uv run python docs/computations/recordings_counts.py --recordings ../leagueasymode-recordings --since 2026-10-28 --until 2026-10-30

   It writes the counts to `evals/out/recordings-counts.json` and prints them.
3. Attest a value read from them, naming the same parameters and the metric:

       make attest C=docs/computations/recordings-counts.md CLAIMED=1 P="recordings=../leagueasymode-recordings since=2026-10-28 until=2026-10-30 metric=games"

The receipt, `evals/out/receipt.json`, holds:

| Field | What it is |
|---|---|
| `arguments` | The arguments the script received, which the attester compares with the computation's |
| `output_file` | Where the counts were written |
| `output_sha256` | The SHA-256 of that file as written |
