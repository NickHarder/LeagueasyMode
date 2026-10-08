#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Hold a directory to the Open Knowledge Format (OKF), version 0.2.

    scripts/okf_bundle.py check docs [--evals evals] [--repository .]    report what breaks a rule
    scripts/okf_bundle.py trace docs [--evals evals]    north star down to the cases  (make trace)
    scripts/okf_bundle.py index docs                    write the index files      (make docs-index)
    scripts/okf_bundle.py status docs                   where each concept stands (make docs-status)
    scripts/okf_bundle.py find docs [--type T] [--status S] [--tag G] [--tier R] [--json]
                                                        the concepts that match   (make docs-find)
    scripts/okf_bundle.py approve docs <concept> --by human:<id> [--at <time>] (make docs-approve)
    scripts/okf_bundle.py reopen docs <concept>                                (make docs-reopen)
    scripts/okf_bundle.py attest docs <concept> --receipt <file> --claimed <value>   (make attest)

`docs/` is this project's knowledge bundle: Markdown files with YAML frontmatter, read a level at a
time through `index.md`. The gate's lint group runs the check (scripts/gate.sh), and so does CI.
Approving and reopening are the owner's calls: an agent runs neither on its own.

The file runs through uv, which reads the dependency named above and the versions pinned in
scripts/okf_bundle.py.lock, so it needs no virtualenv and works in a project with no Python layer.
`make bootstrap` readies it once; after that it runs offline.

The rules are in scripts/okf/: findings.py names every one, and the comment that opens each module
says what its rules report. `frontmatter` and `type` are the format's own. `index` and `log` hold
those two files to the shape the format gives them, and ask for more than it does: an index in every
directory. The rest are this project's own, and stricter than the format, which lets a reader take a
bundle that breaks them.

`approve` records the time it is run at, or the one `--at` gives, and refuses a concept that breaks
a rule. `attest` checks one number: it loads a computation's contract, refuses what the contract
does not allow, and asks the contract's attester whether the receipt of a run backs the claimed
value. `--version` prints the version of the format.

With `--evals`, the check also reads the eval cases beside the bundle: what each one guards and
which metric it feeds. With `--repository`, it is told where the repository is, and holds the
bundle to its `layout`; the gate and CI always say.

A note breaks no rule and fails no gate: a concept past its `stale_after`, one changed since its
approval by a writer who is named, a file in its `sources` that git says changed after it or that
is gone, or a gap in the trace whose floor is off. `index.md` and `log.md`
are reserved names at every level and are not concepts.

Exit 0: no findings; or the value is attested. Exit 1: findings, one a line, as path:line: rule
message, after the notes; or the value is refused. Exit 2: no command was given, the bundle could
not be read, or a command was given what it cannot work on.
"""

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Final

from okf.approval import ApprovalError, approval_findings, approval_notes, approve, reopen
from okf.computation import CannotAttestError, attest_value, computation_findings
from okf.conformance import conformance_findings
from okf.documents import Bundle, Document, UnreadableBundleError, read_bundle
from okf.drift import drift_notes
from okf.findings import APPROVAL, Finding, Note
from okf.index import OKF_VERSION, index_findings, write_indexes
from okf.layout import layout_findings
from okf.logs import log_findings
from okf.policy import policy_findings
from okf.query import ConceptFilter, found_fields, found_line, matching_concepts
from okf.standing import standing_rows
from okf.trace import Trace, read_trace, trace_findings, trace_notes, trace_report
from okf.trust import (
    HUMAN_PREFIX,
    HUMAN_REVIEWED,
    MACHINE_CONFIRMED,
    STATUSES,
    UNVERIFIED,
    is_actor,
    stale_notes,
    time_of,
    trust_findings,
)

EXIT_CLEAN: Final = 0
EXIT_FINDINGS: Final = 1
EXIT_COULD_NOT_RUN: Final = 2

CHECK_COMMAND: Final = "check"
TRACE_COMMAND: Final = "trace"
INDEX_COMMAND: Final = "index"
STATUS_COMMAND: Final = "status"
FIND_COMMAND: Final = "find"
APPROVE_COMMAND: Final = "approve"
REOPEN_COMMAND: Final = "reopen"
ATTEST_COMMAND: Final = "attest"
COMMAND_HELP: Final = {
    CHECK_COMMAND: "report everything in the bundle that breaks a rule",
    TRACE_COMMAND: "print the trace from the north star down to the eval cases, and its gaps",
    INDEX_COMMAND: "write each directory's index.md from the concepts in it",
    STATUS_COMMAND: "list each concept's status, how far it is checked, and its approval",
    FIND_COMMAND: "list the concepts whose type, status, tag and trust tier match",
    APPROVE_COMMAND: "record the owner's approval of one concept as it now is",
    REOPEN_COMMAND: "put an approved concept back to draft, for a change the owner asked for",
    ATTEST_COMMAND: "check that a claimed value came from running a computation as sanctioned",
}
COMMANDS_ON_ONE_CONCEPT: Final = (APPROVE_COMMAND, REOPEN_COMMAND, ATTEST_COMMAND)
COMMANDS_THAT_READ_THE_EVALS: Final = (CHECK_COMMAND, TRACE_COMMAND)
WRITTEN_TIME_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"
TRUST_TIERS: Final = (UNVERIFIED, MACHINE_CONFIRMED, HUMAN_REVIEWED)


class UnusableArgumentError(Exception):
    """A command was given something it cannot work on; the message says what."""


def findings_in(trace: Trace, repository_directory: Path | None = None) -> list[Finding]:
    """Return everything in the bundle that breaks a rule, in the order of the files.

    The layout is held only when the repository's directory is given.

    Raises:
        UnreadableBundleError: If an index or a log cannot be read, or the repository's directory
            is not there.
    """
    bundle = trace.bundle
    concept_findings = [
        finding
        for concept in bundle.concepts
        for finding in (
            *conformance_findings(concept),
            *policy_findings(bundle, concept),
            *trust_findings(bundle, concept),
            *approval_findings(concept),
            *computation_findings(bundle, concept),
        )
    ]
    return sorted(
        [
            *concept_findings,
            *index_findings(bundle),
            *log_findings(bundle),
            *trace_findings(trace),
            *(
                layout_findings(bundle, repository_directory)
                if repository_directory is not None
                else []
            ),
        ],
        key=lambda finding: finding.sort_key(),
    )


def notes_in(trace: Trace, now: datetime.datetime) -> list[Note]:
    """Return what a reader should know about the bundle that breaks no rule."""
    return sorted(
        [
            *(
                note
                for concept in trace.bundle.concepts
                for note in (
                    *stale_notes(concept, now),
                    *approval_notes(concept),
                    *drift_notes(trace.bundle, concept),
                )
            ),
            *trace_notes(trace),
        ],
        key=lambda note: note.sort_key(),
    )


def check_bundle(
    bundle_directory: Path, evals_directory: Path | None, repository_directory: Path | None
) -> int:
    """Check the bundle, and the eval cases beside it when there are any, against every rule.

    Raises:
        UnreadableBundleError: If the bundle or the eval suite cannot be read.
    """
    trace = read_trace(read_bundle(bundle_directory), evals_directory)
    findings = findings_in(trace, repository_directory)
    notes = notes_in(trace, datetime.datetime.now(datetime.UTC))
    concept_count = len(trace.bundle.concepts)
    noted = f", {len(notes)} note(s)" if notes else ""
    # The notes go first. The gate shows the end of a red group's output, and what turned it red
    # must be there however many notes there are.
    sys.stdout.write("".join(f"{note.render()}\n" for note in notes))
    sys.stdout.write("".join(f"{finding.render()}\n" for finding in findings))
    if findings:
        sys.stdout.write(f"okf: {len(findings)} finding(s) in {concept_count} concept(s){noted}\n")
        return EXIT_FINDINGS
    sys.stdout.write(f"okf: {concept_count} concept(s), no findings{noted}\n")
    return EXIT_CLEAN


def show_trace(bundle_directory: Path, evals_directory: Path | None) -> int:
    """Print the trace from the north star down to the eval cases, and what it does not reach.

    Raises:
        UnreadableBundleError: If the bundle or the eval suite cannot be read.
    """
    trace = read_trace(read_bundle(bundle_directory), evals_directory)
    sys.stdout.write("".join(f"{line}\n" for line in trace_report(trace)))
    return EXIT_CLEAN


def write_index_files(bundle_directory: Path) -> int:
    """Write every index of the bundle that is missing or out of date, and say which.

    Raises:
        UnreadableBundleError: If the bundle cannot be read.
    """
    written_files, index_count = write_indexes(read_bundle(bundle_directory))
    if written_files:
        sys.stdout.write("".join(f"wrote {written_file}\n" for written_file in written_files))
        sys.stdout.write(f"okf: wrote {len(written_files)} index file(s)\n")
        return EXIT_CLEAN
    sys.stdout.write(f"okf: {index_count} index file(s), all current\n")
    return EXIT_CLEAN


def show_standing(bundle_directory: Path) -> int:
    """List where each concept of the bundle stands.

    Raises:
        UnreadableBundleError: If the bundle cannot be read.
    """
    rows = standing_rows(read_bundle(bundle_directory), datetime.datetime.now(datetime.UTC))
    sys.stdout.write("".join(f"{row}\n" for row in rows))
    return EXIT_CLEAN


def find_concepts(bundle_directory: Path, concept_filter: ConceptFilter, *, as_json: bool) -> int:
    """List the concepts that match every filter given, as index lines or as JSON.

    Raises:
        UnreadableBundleError: If the bundle cannot be read.
    """
    bundle = read_bundle(bundle_directory)
    found_concepts = matching_concepts(bundle, concept_filter)
    if as_json:
        found = [found_fields(concept) for concept in found_concepts]
        sys.stdout.write(f"{json.dumps(found, ensure_ascii=False, indent=2)}\n")
        return EXIT_CLEAN
    sys.stdout.write("".join(f"{found_line(concept)}\n" for concept in found_concepts))
    sys.stdout.write(f"okf: {len(found_concepts)} of {len(bundle.concepts)} concept(s) match\n")
    return EXIT_CLEAN


def concept_at(bundle: Bundle, concept_path: Path) -> Document:
    """Return the concept of the bundle that a path names.

    Raises:
        UnusableArgumentError: If the path is not a concept of the bundle.
    """
    named_file = concept_path.resolve()
    matching_concepts = [
        concept for concept in bundle.concepts if concept.path.resolve() == named_file
    ]
    if not matching_concepts:
        message = f"{concept_path} is not a concept of the bundle in {bundle.directory}"
        raise UnusableArgumentError(message)
    return matching_concepts[0]


def approval_time_text(given_time_text: str | None) -> str:
    """Return the time an approval is recorded at: the one given, or now.

    Raises:
        UnusableArgumentError: If the time given is not a time with an offset.
    """
    if given_time_text is None:
        return datetime.datetime.now(datetime.UTC).strftime(WRITTEN_TIME_FORMAT)
    if time_of(given_time_text) is None:
        message = (
            f"--at takes a time with an offset, such as 2026-10-04T12:00:00Z, not {given_time_text}"
        )
        raise UnusableArgumentError(message)
    return given_time_text


def approve_concept(
    bundle_directory: Path, concept_path: Path, actor: str, given_time_text: str | None
) -> int:
    """Record the owner's approval of one concept, unless the concept breaks a rule.

    Raises:
        UnreadableBundleError: If the bundle cannot be read.
        UnusableArgumentError: If the approver is not a person, the time is not one or is before
            the text was written, the path is not a concept, or the frontmatter cannot be changed
            safely.
    """
    if not is_actor(actor) or not actor.startswith(HUMAN_PREFIX):
        message = f"an approval is a person's: --by takes human:<id>, not {actor}"
        raise UnusableArgumentError(message)
    time_text = approval_time_text(given_time_text)
    bundle = read_bundle(bundle_directory)
    concept = concept_at(bundle, concept_path)
    # A text that changed under an earlier approval is exactly what a new approval settles.
    blocking_findings = [
        finding
        for finding in findings_in(read_trace(bundle, None))
        if finding.path == concept.path and finding.rule != APPROVAL
    ]
    if blocking_findings:
        sys.stdout.write("".join(f"{finding.render()}\n" for finding in blocking_findings))
        sys.stdout.write(
            f"okf: not approved: {concept.path} breaks {len(blocking_findings)} rule(s); fix them"
            " first\n"
        )
        return EXIT_FINDINGS
    try:
        approved_status = approve(concept, actor, time_text)
    except ApprovalError as error:
        raise UnusableArgumentError(str(error)) from error
    sys.stdout.write(
        f"okf: approved {concept.path} as {actor} at {time_text}; it is {approved_status}\n"
    )
    return EXIT_CLEAN


def reopen_concept(bundle_directory: Path, concept_path: Path) -> int:
    """Put one concept back to draft, so that a change the owner asked for can be made.

    Raises:
        UnreadableBundleError: If the bundle cannot be read.
        UnusableArgumentError: If the path is not a concept of the bundle, or its frontmatter
            cannot be changed safely.
    """
    concept = concept_at(read_bundle(bundle_directory), concept_path)
    if concept.frontmatter_problem is not None:
        message = f"{concept.path} has no frontmatter to reopen: {concept.frontmatter_problem}"
        raise UnusableArgumentError(message)
    try:
        reopen(concept)
    except ApprovalError as error:
        raise UnusableArgumentError(str(error)) from error
    sys.stdout.write(f"okf: reopened {concept.path}; it is a draft until it is approved again\n")
    return EXIT_CLEAN


def attest_claim(
    bundle_directory: Path,
    concept_path: Path,
    receipt_file: Path,
    claimed_text: str,
    given_parameters: list[str],
) -> int:
    """Say whether a claimed value was produced by running a computation the sanctioned way.

    Raises:
        UnreadableBundleError: If the bundle cannot be read.
        UnusableArgumentError: If the path is not an attested computation that breaks no rule, or
            the receipt or the attester cannot be used.
    """
    bundle = read_bundle(bundle_directory)
    concept = concept_at(bundle, concept_path)
    blocking_findings = [
        finding for finding in findings_in(read_trace(bundle, None)) if finding.path == concept.path
    ]
    if blocking_findings:
        sys.stdout.write("".join(f"{finding.render()}\n" for finding in blocking_findings))
        message = (
            f"{concept.path} breaks {len(blocking_findings)} rule(s); it attests nothing until"
            " they are fixed"
        )
        raise UnusableArgumentError(message)
    try:
        verdict = attest_value(
            bundle,
            concept,
            receipt_file,
            claimed_text,
            given_parameters,
            now=datetime.datetime.now(datetime.UTC),
        )
    except CannotAttestError as error:
        raise UnusableArgumentError(str(error)) from error
    detail_lines = "".join(f"  {key}: {value}\n" for key, value in verdict.details.items())
    if verdict.is_ok:
        given = " ".join(given_parameters)
        sys.stdout.write(
            f"attested: {concept.path}  {given}  claimed {claimed_text}\n{detail_lines}"
        )
        return EXIT_CLEAN
    sys.stdout.write(f"refused: {concept.path}: {verdict.reason}\n{detail_lines}")
    return EXIT_FINDINGS


def argument_parser() -> argparse.ArgumentParser:
    """Return the parser for the command line: a subcommand, the bundle, then what it needs."""
    parser = argparse.ArgumentParser(
        prog="okf_bundle.py", description="Hold a directory to the Open Knowledge Format."
    )
    parser.add_argument("--version", action="version", version=f"okf-bundle, OKF {OKF_VERSION}")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command_name, command_help in COMMAND_HELP.items():
        command_parser = subcommands.add_parser(command_name, help=command_help)
        command_parser.add_argument(
            "bundle", type=Path, help="the bundle's directory, such as docs"
        )
        if command_name in COMMANDS_ON_ONE_CONCEPT:
            command_parser.add_argument(
                "concept", type=Path, help="the concept's file, such as docs/AUDIT.md"
            )
        if command_name in COMMANDS_THAT_READ_THE_EVALS:
            command_parser.add_argument(
                "--evals", type=Path, default=None, help="the eval suite's directory, such as evals"
            )
        if command_name == CHECK_COMMAND:
            command_parser.add_argument(
                "--repository",
                type=Path,
                default=None,
                help="the repository's root, such as . : also hold the bundle to its layout",
            )
        if command_name == FIND_COMMAND:
            command_parser.add_argument("--type", default=None, help="a `type`, in any case")
            command_parser.add_argument("--status", choices=STATUSES, default=None)
            command_parser.add_argument("--tag", default=None, help="one of the concept's `tags`")
            command_parser.add_argument("--tier", choices=TRUST_TIERS, default=None)
            command_parser.add_argument(
                "--json", action="store_true", help="answer with the fields as JSON, for a tool"
            )
        if command_name == APPROVE_COMMAND:
            command_parser.add_argument("--by", required=True, help="the owner, as human:<id>")
            command_parser.add_argument("--at", default=None, help="the time; now when left out")
        if command_name == ATTEST_COMMAND:
            command_parser.add_argument(
                "--receipt", type=Path, required=True, help="what the run handed back, as JSON"
            )
            command_parser.add_argument("--claimed", required=True, help="the value to check")
            command_parser.add_argument(
                "--parameter",
                action="append",
                default=[],
                help="a value for a declared parameter, as name=value; repeat for each",
            )
    return parser


def run_command_on_one_concept(parsed: argparse.Namespace) -> int:
    """Run a subcommand that works on one concept: approve, reopen or attest.

    Raises:
        UnreadableBundleError: If the bundle cannot be read.
        UnusableArgumentError: If the command was given something it cannot work on.
    """
    command_name: str = parsed.command
    bundle_directory: Path = parsed.bundle
    concept_path: Path = parsed.concept
    if command_name == REOPEN_COMMAND:
        return reopen_concept(bundle_directory, concept_path)
    if command_name == ATTEST_COMMAND:
        receipt_file: Path = parsed.receipt
        claimed_text: str = parsed.claimed
        given_parameters: list[str] = parsed.parameter
        return attest_claim(
            bundle_directory, concept_path, receipt_file, claimed_text, given_parameters
        )
    actor: str = parsed.by
    given_time_text: str | None = parsed.at
    return approve_concept(bundle_directory, concept_path, actor, given_time_text)


def run_find(parsed: argparse.Namespace) -> int:
    """Run the find subcommand with the filters the command line gave.

    Raises:
        UnreadableBundleError: If the bundle cannot be read.
    """
    bundle_directory: Path = parsed.bundle
    type_name: str | None = parsed.type
    status: str | None = parsed.status
    tag: str | None = parsed.tag
    tier: str | None = parsed.tier
    as_json: bool = parsed.json
    concept_filter = ConceptFilter(type_name=type_name, status=status, tag=tag, tier=tier)
    return find_concepts(bundle_directory, concept_filter, as_json=as_json)


def run_command(parsed: argparse.Namespace) -> int:
    """Run the subcommand the command line named.

    Raises:
        UnreadableBundleError: If the bundle cannot be read.
        UnusableArgumentError: If the command was given something it cannot work on.
    """
    command_name: str = parsed.command
    bundle_directory: Path = parsed.bundle
    if command_name in COMMANDS_ON_ONE_CONCEPT:
        return run_command_on_one_concept(parsed)
    if command_name == INDEX_COMMAND:
        return write_index_files(bundle_directory)
    if command_name == STATUS_COMMAND:
        return show_standing(bundle_directory)
    if command_name == FIND_COMMAND:
        return run_find(parsed)
    evals_directory: Path | None = parsed.evals
    if command_name == TRACE_COMMAND:
        return show_trace(bundle_directory, evals_directory)
    repository_directory: Path | None = parsed.repository
    return check_bundle(bundle_directory, evals_directory, repository_directory)


def main(arguments: list[str]) -> int:
    """Run the command line, and say why when it cannot be run; argparse exits 2 on a bad one."""
    parsed = argument_parser().parse_args(arguments)
    try:
        return run_command(parsed)
    except (UnreadableBundleError, UnusableArgumentError) as error:
        sys.stderr.write(f"okf: {error}\n")
        return EXIT_COULD_NOT_RUN


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
