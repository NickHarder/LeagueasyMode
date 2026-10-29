---
type: Executor
title: Running the accuracy score
description: How to run the accuracy score on an accuracy history, and the receipt a run hands back.
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T07:09:16Z }
---

# Running the accuracy score

1. Take the accuracy history: on the Mac, `~/Library/Application Support/LeagueasyMode/accuracy-history.jsonl`;
   or score the recorded games with `uv run leagueasymode score <recording> --keep`.
2. Run the computation with the parameters filled in, from the repository's root:

       uv run python docs/computations/accuracy_score.py --history accuracy-history.jsonl --estimator "jungle path" --last 20

   It writes the result to `evals/out/accuracy-score.json` and prints it.
3. Attest the value it printed:

       make attest C=docs/computations/accuracy-score.md CLAIMED=<value> P="history=accuracy-history.jsonl estimator=jungle\ path last=20"

The receipt, `evals/out/receipt.json`, holds `arguments` (what the script received),
`output_file` and `output_sha256`.
