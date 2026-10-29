---
type: Attested Computation
title: The recordings counts
description: Games, crash reports and problem reports that reached the recordings repository in a window of days, and the guardrails' rates, counted from file names alone.
status: draft
generated: { by: claude-code/cloud, at: 2026-10-29T07:08:19Z }
runtime: shell
parameters:
  - { name: recordings, type: string, required: true }
  - { name: since, type: string, required: true }
  - { name: until, type: string, required: true }
  - { name: metric, type: string, required: true }
executor:
  resource: /references/executors/recordings-counts.md
  receipt: [arguments, output_file, output_sha256]
attester:
  resource: /references/attesters/recordings_counts.py
---

# The recordings counts

Backs [DR-01](/metrics/DR-01.md), [GR-01](/metrics/GR-01.md) and [GR-02](/metrics/GR-02.md).
`recordings` is a clone of `NickHarder/LeagueasyMode-recordings`; `since` and `until` are days
(`YYYY-MM-DD`, UTC), `until` not included; `metric` is one of `games`, `crash_reports`,
`reports`, `crashes_per_game`, `reports_per_ten_games`. The script reads file names only:
[recordings_counts.py](recordings_counts.py).

# Computation

    uv run python docs/computations/recordings_counts.py --recordings {recordings} --since {since} --until {until}
