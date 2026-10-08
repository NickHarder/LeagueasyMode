---
name: audit-codebase
description: Audits the system the project builds on (security, performance, architecture, data quality, compliance) with one sub-agent per area, then writes docs/AUDIT.md with reproducible findings and what each one changes in the plan. Use when producing or updating the audit hard gate, before any product code exists.
disable-model-invocation: true
metadata:
  version: "2.0.0"
---

# Audit the codebase (hard gate)

Produce `docs/AUDIT.md` before any product code exists. The audit covers what the project builds on:
an existing codebase, or, for a new project, the APIs, datasets, model providers and deploy target it
will depend on.

`docs/AUDIT.md` is a concept of the knowledge bundle and carries `type: Audit`. Each area's file,
`docs/audit/<area>.md`, is one too, with `type: Audit Area`, and the audit links to it.
The `write-okf-concept` skill has the rules for the frontmatter, the index and the log.

## Evidence rule

A finding without a reproduction is not a finding. Each finding uses this template:

```markdown
### [AREA-NN] <short title>
- **Severity:** critical | high | medium | low | info
- **Location:** `path:line`, or the query or request
- **Reproduction:** the exact command or query that demonstrates it
- **Impact on the project:** what the product would get wrong, leak, or fail to do in time
- **Mitigation:** what a later phase must do, or an explicit deferral
```

A finding is a candidate until you have run its reproduction and read the real output.

## Parallel execution

Launch one sub-agent per area. Each writes `docs/audit/<area>.md` using only evidence it verified
against the running system and this codebase. The default areas, and what each must answer:

- **Security** (`SEC`): authentication and authorization, data exposure, secrets in the repository,
  handling of sensitive data.
- **Performance** (`PERF`): where the system is slow, the shape and volume of the data, what bounds
  the product's latency.
- **Architecture** (`ARCH`): how the code is organized, where data lives, the integration points the
  product can use, and the ones that turn out not to exist.
- **Data quality** (`DQ`): null rates, orphans, duplicates, implausible values, date sanity. Start from
  a committed, re-runnable profile script (`docs/audit/data_profile.sql` or the equivalent).
- **Compliance** (`CMP`): audit logging, retention, and what it means to send this data to a model
  provider.

Drop an area that does not apply and say why in `docs/AUDIT.md`. Before launching, write each area's
required probes from the brief and from a first read of the code, phrased as things to confirm, not to
assume.

## Synthesis: `docs/AUDIT.md`

1. **Summary, about 500 words** (450 to 550; count them). The findings that matter most to the
   product. Not a dump.
2. **How this changes the plan.** A table: finding → the decision it forces. If a finding changes
   nothing, say so.
3. **One section per area**, as a table `| Id | Severity | Finding | Response |`, with a link to the
   full findings in `docs/audit/<area>.md`.
4. **Test-data defense**, when the project uses synthetic or seeded data: why it is safe, how it is
   reproduced (seed, script), which of its flaws become product failure modes, and what it cannot show.

## Acceptance

- [ ] `docs/AUDIT.md` is committed, carries `type: Audit`, and links each area's file
- [ ] `make docs-index` was run, and `docs/log.md` has the audit's entry
- [ ] The summary is 450 to 550 words
- [ ] Every finding has a location and a reproduction that was run
- [ ] The profile script is committed and was executed
- [ ] No product code exists yet
