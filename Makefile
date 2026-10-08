# The commands a reviewer needs. `make help` prints this header.
#
#   make tools         on Linux: the tools the gate needs that uv cannot install, at CI's versions. On a Mac, brew.
#   make bootstrap     once per clone: what the gate needs, the index of docs/, the git hooks. No API key needed.
#   make gate          everything a push must pass (scripts/kit.conf lists the groups). $0, offline.
#   make gate-lint     one group of the gate; also gate-tests, gate-evals and gate-secrets.
#   make docs-index    write the index files of the knowledge bundle in docs/ from its concepts.
#   make docs-status   where each document in docs/ stands: its status, who has checked it, its approval.
#   make docs-find [TYPE=] [STATUS=] [TAG=] [TIER=]   the documents in docs/ that match, one line each.
#   make docs-approve DOC=<file>   record the owner's approval of a document as it now is. The owner's call.
#   make docs-reopen DOC=<file>    put an approved document back to draft. The owner's call.
#   make trace         the north star, what supports it, the use cases, the eval cases, and the gaps.
#   make attest C=<computation> CLAIMED=<value> [P="name=value ..."] [RECEIPT=<file>]   check a number against its run.
#   make kit-update    pull the kit's improvements into this project (copier update).
#
# The gate is defined in one place, scripts/gate.sh; the pre-push hook runs the same script.

include scripts/kit.conf

GATE := scripts/gate.sh

.PHONY: help tools bootstrap gate docs-index docs-status docs-find docs-approve docs-reopen trace attest kit-update

# The header is the comment this file opens with, down to the first line that is not a comment.
help:
	@awk '/^#/ { sub(/^# ?/, ""); print; next } { exit }' Makefile

# gitleaks for the secret scan, and oasdiff in an API project, into ~/.local/bin (scripts/install_tools.sh).
tools:
	@scripts/install_tools.sh gitleaks$(if $(filter 1,$(API_PROJECT)), oasdiff)

bootstrap:
	@scripts/bootstrap.sh

gate:
	@$(GATE)

# One group: `make gate-lint` runs `scripts/gate.sh --only lint`.
gate-lint gate-tests gate-evals gate-secrets:
	@$(GATE) --only $(@:gate-%=%)

# After a concept is added, removed, retitled or described anew; the gate fails on a stale index.
docs-index:
	@scripts/okf_bundle.py index docs

docs-status:
	@scripts/okf_bundle.py status docs

# Every filter given must match: a type in any case, a status, one tag, a trust tier.
docs-find:
	@scripts/okf_bundle.py find docs $(if $(TYPE),--type "$(TYPE)") $(if $(STATUS),--status "$(STATUS)") $(if $(TAG),--tag "$(TAG)") $(if $(TIER),--tier "$(TIER)")

# The owner's calls. An approval is of the concept as it is now, its body and its fields; a later
# change to either shows in the gate.
docs-approve:
	@test -n "$(DOC)" || { echo "docs-approve: name the document: make docs-approve DOC=docs/AUDIT.md" >&2; exit 64; }
	@scripts/okf_bundle.py approve docs "$(DOC)" --by "human:$(OWNER_ID)"

docs-reopen:
	@test -n "$(DOC)" || { echo "docs-reopen: name the document: make docs-reopen DOC=docs/AUDIT.md" >&2; exit 64; }
	@scripts/okf_bundle.py reopen docs "$(DOC)"

trace:
	@scripts/okf_bundle.py trace docs

# Ask a computation's attester whether the receipt of a run backs a number. RECEIPT is where the
# run left its receipt; `make evals` leaves one in evals/out/.
attest:
	@test -n "$(C)" || { echo 'attest: name the computation and the number: make attest C=docs/computations/<name>.md CLAIMED=<value> P="tier=core"' >&2; exit 64; }
	@test -n "$(CLAIMED)" || { echo 'attest: say which number: make attest C=$(C) CLAIMED=<value>' >&2; exit 64; }
	@scripts/okf_bundle.py attest docs "$(C)" --receipt "$(or $(RECEIPT),evals/out/receipt.json)" --claimed "$(CLAIMED)" $(foreach parameter,$(P),--parameter $(parameter))

# With a terminal, a question that the new version adds is asked. Without one (an agent, a script)
# copier cannot ask, so the question takes its default, and this says so.
kit-update:
	@command -v copier >/dev/null 2>&1 || { echo "kit-update: copier is not installed. Install it with:  uv tool install copier" >&2; exit 3; }
	@if [ -t 0 ]; then \
		copier update --skip-answered; \
	else \
		echo "kit-update: no terminal, so a question this version adds takes its default. To answer it yourself, run in a terminal:  copier update"; \
		copier update --skip-answered --defaults; \
	fi





