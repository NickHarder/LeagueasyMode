---
type: Attested Computation
title: The accuracy score
description: One estimator's score against the post-game timeline over the newest games of the accuracy history, weighed by each game's samples.
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T07:09:16Z }
runtime: shell
parameters:
  - { name: history, type: string, required: true }
  - { name: estimator, type: string, required: true }
  - { name: last, type: integer, required: true }
executor:
  resource: /references/executors/accuracy-score.md
  receipt: [arguments, output_file, output_sha256]
attester:
  resource: /references/attesters/accuracy_score.py
---

# The accuracy score

Backs [DR-02](/metrics/DR-02.md) (`estimator="jungle path"`), [DR-03](/metrics/DR-03.md)
(`fights`) and [DR-04](/metrics/DR-04.md) (`objective contests`). `history` is the accuracy
history, `accuracy-history.jsonl` in the app's folder on the Mac or the daily session's copy;
`last` is how many of the newest games with that estimator's score count. The script:
[accuracy_score.py](accuracy_score.py). A value of `null` means no game has been scored.

# Computation

    uv run python docs/computations/accuracy_score.py --history {history} --estimator {estimator} --last {last}
