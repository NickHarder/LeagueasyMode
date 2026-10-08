---
name: audit-security
description: Runs a local security review on request (secret scan with gitleaks, static analysis with semgrep, dependency audit with pip-audit), verifies each result by reading the code, and reports findings by severity with reproductions. Use when the owner explicitly asks for a security audit or scan; never run it as part of the gate or on your own initiative.
disable-model-invocation: true
metadata:
  version: "1.2.0"
---

# Audit security (on demand)

This is the slow, thorough scan. The gate and the pre-push hook stay fast and do not run it; run it
only when the owner asks.

## Before running

1. Agree the scope: by default, the files this project's owner wrote and tracks in git. In a fork, name
   the directories; upstream code is out of scope unless the owner says otherwise.
2. Say what will be downloaded and get a yes: `uvx` fetches semgrep and pip-audit into the uv cache on
   first use, and semgrep fetches its rule packs from semgrep.dev. Install nothing else. If `gitleaks`
   is missing, say so and skip that step rather than installing it.
3. Use a scratch directory outside the repository for reports (`${TMPDIR:-/tmp}/security-audit`).

## Steps

1. **Secrets.** `gitleaks git --no-banner --redact --report-path <scratch>/gitleaks.json`. This reads
   the git history, so an untracked `.env` holding real keys is not scanned. Never print a secret; the
   report is redacted.
2. **Static analysis.**
   `uvx semgrep scan --config p/python --config p/secrets --config p/owasp-top-ten --metrics off --json --output <scratch>/semgrep.json <paths>`.
   Add the pack for whatever else is in scope (`p/dockerfile`, `p/javascript`, `p/typescript`).
3. **Dependencies.** In the Python project's directory:
   `uv export --frozen --no-emit-project --format requirements-txt -q -o <scratch>/requirements.txt`,
   then `uvx pip-audit -r <scratch>/requirements.txt --disable-pip --require-hashes --progress-spinner off`.
4. **Verify.** A scanner result is a candidate, not a finding. Open the code at each location and decide
   whether it is real. Drop a false positive with one line saying why.
5. **Report.** Write `docs/audit/security-review.md`, findings ordered critical, high, medium, low,
   each in this form:

```markdown
### [SR-NN] <short title>
- **Severity:** critical | high | medium | low | info
- **Location:** `path:line`
- **Reproduction:** the exact command that shows it
- **Impact:** what an attacker gains, or what leaks
- **Mitigation:** the smallest fix
```

   The file is a concept of the knowledge bundle and carries `type: Security Review`; the
   `write-okf-concept` skill has the rules. Run `make docs-index` after writing it. Its ids are
   `SR-NN`. `docs/audit/security.md` and `SEC-NN` belong to the security area of `audit-codebase`,
   and an id names one thing.

   Then tell the owner the counts by severity, the critical and high findings in a sentence each, and
   which steps were skipped.

## Rules

- Report, do not fix, unless the owner asks for the fix.
- A finding without a reproduction is not a finding.
- If a real secret is found in the history, say so first and plainly: it must be revoked, and removing
  it from the files does not do that.

## Acceptance

- [ ] Every step ran, or the report says which were skipped and why
- [ ] Every finding was verified against the code and has a reproduction
- [ ] No secret value appears in the report or in the conversation
- [ ] The report carries `type: Security Review`, and the index of `docs/audit/` lists it
