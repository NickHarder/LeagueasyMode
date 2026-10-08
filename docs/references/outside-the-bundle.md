---
type: Reference
title: What lives outside the bundle
description: The Markdown files of this repository that are not concepts of the bundle, each with who reads it where it is.
tags: [layout]
status: stable
generated: { by: ai-kit/v0.11.1 }
outside:
  - { path: README.md, read_by: "The code host, as the front page of the repository" }
  - { path: "**/README.md", read_by: "The code host, when a directory is browsed. It points at a concept and holds no knowledge of its own" }
  - { path: AGENTS.md, read_by: "Claude Code and Cursor, directly, at the start of every session" }
  - { path: HANDOFF.md, read_by: "Every session, first. It is the state of the work, not knowledge" }
---

# What this is

Everything this project knows is a concept of this bundle. A Markdown file anywhere else is there
because a tool reads it at that place. The `outside` list above names each one with the tool, and
`make gate` holds the repository to it: a Markdown file that is neither a concept under `docs/` nor
on the list breaks the `layout` rule.

A directory whose name starts with a dot belongs to a tool, as `.claude/` does with its skills. So
do `node_modules` and `__pycache__`. The gate looks at nothing inside them.

# What is not here, on purpose

`CLAUDE.md` and `CLAUDE.local.md`. Claude Code reads `AGENTS.md` only while neither is in the
project, so the gate fails on either, even on one that git ignores. Personal notes go in your own
instructions, outside the project.

# Where a new document goes

Under `docs/`, in the directory for its kind, as the `write-okf-concept` skill describes. Do not
write a document beside the code it is about: a reader looks here, and so does the gate.

# Adding to the list

Add a line only when a tool needs a file where it is. Give the `path`, and in `read_by` the tool that
reads it there. An entry with no `read_by` fails the gate.

| A `path` that | Covers | Example |
|---|---|---|
| names a file | That file, from the repository's root | `AGENTS.md` |
| ends in `/` | Everything under that directory | `vendor/docs/` |
| starts with `**/` | A file of that name in any directory | `**/README.md` |
