"""The trace: from the north star down to the eval cases, by ids a check can follow.

    NS-01 north star  <-  DR-nn drivers, GR-nn guardrails   `supports: NS-01`
    a key metric      ->  the use cases it proves           `proves: [UC-02]`
    an eval case      ->  what it guards, what it feeds     `guards: [UC-02]`, `metrics: [DR-01]`

An id is a few capitals, a hyphen and two or more digits. It is defined by a concept whose file
name is the id (`docs/metrics/NS-01.md`), by an eval case's `id`, or by a heading that starts with
it (`### UC-01: ...`, `### [SEC-01] ...`). The first cell of a table row defines an id only when
no heading, file name or case defines an id with the same capitals. So a register that exists only
as a table (`| DV-01 | ... |`) defines its ids, and a table that lists `UC-07` beside use cases
that have headings only names it.

    trace   an id that is defined nowhere; an id two headings define; a second north star; a driver
            or a guardrail that does not support the north star; a gap whose floor is on

A word such as SHA-256 is taken for an id only when its capitals start an id that is defined, so a
project is never asked to explain a hash. A gap is something the trace does not yet reach: a use
case with no eval case, a metric with no measurement. Each kind of gap has a floor in
`evals/thresholds.yaml`. With the floor off the gap is a note; with it on, a finding. A project
turns a floor on in the change that earns it; the thresholds file says when one may be turned off,
and the owner reviews that file. A floor is `true` or `false` and
nothing else: the eval runner reads the same file, and the two must never disagree on a floor.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from okf.computation import is_attested_computation
from okf.documents import (
    Bundle,
    Document,
    NotAMappingError,
    UnreadableBundleError,
    key_line_numbers,
    read_text_file,
    yaml_mapping,
)
from okf.findings import TRACE, Finding, Note
from okf.markdown import heading_of, links_in, prose_lines, without_addresses
from okf.policy import linked_path, resolved_path
from okf.trust import STATUS_KEY, trust_tier

# An id is not followed by a dash and digits: `CVE-2024-3094` is one number, not the id `CVE-2024`.
ID_SHAPE: Final = r"[A-Z]{1,5}-\d{2,}(?!-\d)"
ID_PATTERN: Final = re.compile(rf"(?<![A-Za-z0-9-])(?P<identifier>{ID_SHAPE})(?![A-Za-z0-9])")
WHOLE_ID_PATTERN: Final = re.compile(ID_SHAPE)
# What a heading's text starts with when the heading defines an id: `UC-01: ...` or `[SEC-01] ...`.
HEADING_DEFINITION_PATTERN: Final = re.compile(rf"\[?(?P<identifier>{ID_SHAPE})\]?(?![A-Za-z0-9])")
TABLE_ROW_DEFINITION_PATTERN: Final = re.compile(
    rf"\s{{0,3}}\|\s*\[?(?P<identifier>{ID_SHAPE})\]?\s*\|"
)

ROLE_KEY: Final = "role"
SUPPORTS_KEY: Final = "supports"
PROVES_KEY: Final = "proves"
TITLE_KEY: Final = "title"
NORTH_STAR: Final = "north-star"
DRIVER: Final = "driver"
GUARDRAIL: Final = "guardrail"
ROLES: Final = (NORTH_STAR, DRIVER, GUARDRAIL)
USE_CASE_PREFIX: Final = "UC"

CASE_ID_KEY: Final = "id"
GUARDS_KEY: Final = "guards"
METRICS_KEY: Final = "metrics"
TIER_KEY: Final = "tier"
CASE_TYPE_KEY: Final = "type"
DEFAULT_TIER: Final = "scenario"
CORE_TIER: Final = "core"
CASE_TYPES_THAT_TEST_A_GUARDRAIL: Final = ("boundary", "regression")
CASES_DIRECTORY_NAME: Final = "cases"
CASE_FILE_PATTERNS: Final = ("*.yaml", "*.yml")
THRESHOLDS_FILE_NAME: Final = "thresholds.yaml"
RESULTS_FILE: Final = Path("out") / "results.json"
FLOORS_KEY: Final = "trace"
NOT_RUN: Final = "not run"

EVERY_CASE_NAMES_A_USE_CASE_OR_FINDING: Final = "every_case_names_a_use_case_or_finding"
EVERY_CASE_NAMES_A_METRIC: Final = "every_case_names_a_metric"
EVERY_USE_CASE_HAS_A_CASE: Final = "every_use_case_has_a_case"
EVERY_METRIC_HAS_A_CASE_OR_A_COMPUTATION: Final = "every_metric_has_a_case_or_a_computation"
NORTH_STAR_HAS_A_CORE_CASE: Final = "north_star_has_a_core_case"
EVERY_GUARDRAIL_HAS_A_BOUNDARY_OR_REGRESSION_CASE: Final = (
    "every_guardrail_has_a_boundary_or_regression_case"
)
FLOORS: Final = (
    EVERY_CASE_NAMES_A_USE_CASE_OR_FINDING,
    EVERY_CASE_NAMES_A_METRIC,
    EVERY_USE_CASE_HAS_A_CASE,
    EVERY_METRIC_HAS_A_CASE_OR_A_COMPUTATION,
    NORTH_STAR_HAS_A_CORE_CASE,
    EVERY_GUARDRAIL_HAS_A_BOUNDARY_OR_REGRESSION_CASE,
)


@dataclass(frozen=True)
class EvalCase:
    """One eval case, as far as the trace reads it: what it guards and what it feeds."""

    path: Path
    case_id: str
    guards: list[str]
    metrics: list[str]
    tier: str
    case_type: str
    line_number_by_key: dict[str, int]

    def line_number_of(self, key: str) -> int:
        """Return the line a top-level key of the case is on, or 1 when the key is not there."""
        return self.line_number_by_key.get(key, 1)

    def described(self, verdict_by_case_id: dict[str, str]) -> str:
        """Return the case as one phrase: its id, its tier and type, and its last verdict."""
        verdict = verdict_by_case_id.get(self.case_id, NOT_RUN)
        return f"{self.case_id} ({self.tier}, {self.case_type}): {verdict}"


@dataclass(frozen=True)
class EvalSuite:
    """The eval suite beside a bundle: its cases, its floors, and its last verdicts.

    `floor_findings` is what is wrong with how the thresholds file writes the floors.
    """

    cases: list[EvalCase]
    floors_on: frozenset[str]
    floor_findings: list[Finding]
    verdict_by_case_id: dict[str, str]


@dataclass(frozen=True)
class KeyMetric:
    """A concept with a `role`: the north star, a driver or a guardrail."""

    document: Document
    identifier: str
    role: str
    supports: str
    proves: list[str]


@dataclass(frozen=True)
class Definition:
    """One place an id is defined: strongly by a heading, a file name or a case; weakly by a row."""

    identifier: str
    path: Path
    line_number: int
    is_strong: bool


@dataclass(frozen=True)
class Reference:
    """One place an id is named. A field of frontmatter or of a case is structured; prose is not."""

    identifier: str
    path: Path
    line_number: int
    is_structured: bool


@dataclass(frozen=True)
class Gap:
    """Something the trace does not yet reach, and the floor that would make it a finding."""

    floor: str
    path: Path
    line_number: int
    message: str


@dataclass(frozen=True)
class Trace:
    """Everything the trace is worked out from, read once."""

    bundle: Bundle
    suite: EvalSuite | None
    key_metrics: list[KeyMetric]
    definitions: list[Definition]

    @property
    def cases(self) -> list[EvalCase]:
        """Return the eval cases, or none when the project has no suite."""
        return self.suite.cases if self.suite is not None else []

    @property
    def defined_ids(self) -> frozenset[str]:
        """Return every id that is defined somewhere."""
        return frozenset(definition.identifier for definition in self.definitions)

    @property
    def north_stars(self) -> list[KeyMetric]:
        """Return the key metrics whose role is the north star; there should be one."""
        return [metric for metric in self.key_metrics if metric.role == NORTH_STAR]


def prefix_of(identifier: str) -> str:
    """Return the capitals an id starts with: `UC` for `UC-02`."""
    return identifier.split("-", 1)[0]


def text_items(value: object) -> list[str]:
    """Return a list field as its text items; a value that is not a list has none."""
    return [str(item) for item in value] if isinstance(value, list) else []


def yaml_file_mapping(yaml_file: Path, yaml_text: str) -> dict[str, object]:
    """Return the top-level keys and values of a YAML file, from its text.

    Raises:
        UnreadableBundleError: If the text cannot be read as a mapping.
    """
    try:
        return yaml_mapping(yaml_text)
    except NotAMappingError as error:
        message = f"{yaml_file} {error}"
        raise UnreadableBundleError(message) from error


def read_eval_case(case_file: Path) -> EvalCase:
    """Return one eval case, as far as the trace reads it.

    Raises:
        UnreadableBundleError: If the file cannot be read as a mapping.
    """
    case_text = read_text_file(case_file)
    fields = yaml_file_mapping(case_file, case_text)
    return EvalCase(
        path=case_file,
        case_id=str(fields.get(CASE_ID_KEY, case_file.stem)),
        guards=text_items(fields.get(GUARDS_KEY)),
        metrics=text_items(fields.get(METRICS_KEY)),
        tier=str(fields.get(TIER_KEY, DEFAULT_TIER)),
        case_type=str(fields.get(CASE_TYPE_KEY, "")),
        line_number_by_key=key_line_numbers(case_text),
    )


def floor_problem(floor: str, value: object) -> str:
    """Return what is wrong with how one floor is written, or an empty string."""
    if floor not in FLOORS:
        known_floors = ", ".join(f"`{known_floor}`" for known_floor in FLOORS)
        return f"`{floor}` is not a floor of the trace; the floors are {known_floors}"
    if not isinstance(value, bool):
        written_value = json.dumps(value, default=str)
        return f"the floor `{floor}` must be `true` or `false`, not `{written_value}`"
    return ""


def read_floors(thresholds_file: Path) -> tuple[frozenset[str], list[Finding]]:
    """Return the floors a thresholds file switches on, and what is wrong with how it writes them.

    Without the file, or without `trace` in it, every floor is off and nothing is wrong. A floor
    is on when it is written `true`. Anything that is neither `true` nor `false` is a finding, and
    so is a name that is not a floor: either would leave a floor off that someone meant to be on.

    Raises:
        UnreadableBundleError: If the file is there and cannot be read as a mapping.
    """
    if not thresholds_file.is_file():
        return frozenset(), []
    thresholds_text = read_text_file(thresholds_file)
    fields = yaml_file_mapping(thresholds_file, thresholds_text)
    if FLOORS_KEY not in fields:
        return frozenset(), []
    floors = fields[FLOORS_KEY]
    if not isinstance(floors, dict):
        line_number = key_line_numbers(thresholds_text).get(FLOORS_KEY, 1)
        message = (
            f"`{FLOORS_KEY}` holds the floors of the trace, each written `<floor>: true` or"
            " `<floor>: false`"
        )
        return frozenset(), [Finding(thresholds_file, line_number, TRACE, message)]
    line_number_by_floor = key_line_numbers(thresholds_text, FLOORS_KEY)
    problems = [(str(floor), floor_problem(str(floor), value)) for floor, value in floors.items()]
    floor_findings = [
        Finding(thresholds_file, line_number_by_floor.get(floor, 1), TRACE, problem)
        for floor, problem in problems
        if problem
    ]
    floors_on = frozenset(
        str(floor) for floor, value in floors.items() if value is True and str(floor) in FLOORS
    )
    return floors_on, floor_findings


def last_verdicts(results_file: Path) -> dict[str, str]:
    """Return each case's verdict in the last run that wrote a report; none without the file."""
    if not results_file.is_file():
        return {}
    try:
        results: object = json.loads(read_text_file(results_file))
    except json.JSONDecodeError:
        return {}
    case_results = results.get("cases") if isinstance(results, dict) else None
    return {
        str(case_result.get("case_id")): str(case_result.get("status"))
        for case_result in (case_results if isinstance(case_results, list) else [])
        if isinstance(case_result, dict)
    }


def read_eval_suite(evals_directory: Path | None) -> EvalSuite | None:
    """Return the eval suite in a directory, or None when the project has none.

    Raises:
        UnreadableBundleError: If the directory is not there, or a case cannot be read.
    """
    if evals_directory is None:
        return None
    if not evals_directory.is_dir():
        message = f"{evals_directory} does not exist, or is not a directory"
        raise UnreadableBundleError(message)
    case_files = sorted(
        (
            case_file
            for pattern in CASE_FILE_PATTERNS
            for case_file in (evals_directory / CASES_DIRECTORY_NAME).rglob(pattern)
        ),
        key=lambda case_file: case_file.as_posix(),
    )
    floors_on, floor_findings = read_floors(evals_directory / THRESHOLDS_FILE_NAME)
    return EvalSuite(
        cases=[read_eval_case(case_file) for case_file in case_files],
        floors_on=floors_on,
        floor_findings=floor_findings,
        verdict_by_case_id=last_verdicts(evals_directory / RESULTS_FILE),
    )


def read_key_metrics(bundle: Bundle) -> list[KeyMetric]:
    """Return every concept that gives itself a role in the trace, in the order of their paths."""
    return [
        KeyMetric(
            document=concept,
            identifier=concept.path.stem,
            role=str(concept.fields[ROLE_KEY]),
            supports=concept.text_field(SUPPORTS_KEY),
            proves=text_items(concept.fields.get(PROVES_KEY)),
        )
        for concept in bundle.concepts
        if concept.frontmatter_problem is None and ROLE_KEY in concept.fields
    ]


def body_definitions(concept: Document) -> list[Definition]:
    """Return the ids a concept's body defines: by a heading, or by a table row's first cell."""
    lines = prose_lines(concept.body, concept.body_line_number)
    headings = [(line.line_number, heading_of(line.text)) for line in lines]
    matches = [
        *(
            (line_number, HEADING_DEFINITION_PATTERN.match(heading.text), True)
            for line_number, heading in headings
            if heading is not None
        ),
        *(
            (line.line_number, TABLE_ROW_DEFINITION_PATTERN.match(line.text), False)
            for line in lines
        ),
    ]
    return sorted(
        (
            Definition(matched.group("identifier"), concept.path, line_number, is_strong)
            for line_number, matched, is_strong in matches
            if matched is not None
        ),
        key=lambda definition: definition.line_number,
    )


def read_definitions(bundle: Bundle, suite: EvalSuite | None) -> list[Definition]:
    """Return every definition of an id, in the order of the files and their lines.

    A heading that repeats the id its own file is named after is that file's definition again, and
    not a second one. A table row defines an id only when no heading, file name or case defines an
    id with the same capitals; otherwise the row names the id, as prose does.
    """
    readable_concepts = [
        concept for concept in bundle.concepts if concept.frontmatter_problem is None
    ]
    by_file_name = [
        Definition(concept.path.stem, concept.path, 1, is_strong=True)
        for concept in readable_concepts
        if WHOLE_ID_PATTERN.fullmatch(concept.path.stem)
    ]
    by_case = [
        Definition(case.case_id, case.path, case.line_number_of(CASE_ID_KEY), is_strong=True)
        for case in (suite.cases if suite is not None else [])
        if WHOLE_ID_PATTERN.fullmatch(case.case_id)
    ]
    in_bodies = [
        definition
        for concept in readable_concepts
        for definition in body_definitions(concept)
        if not (definition.is_strong and definition.identifier == concept.path.stem)
    ]
    strongly_defined_prefixes = {
        prefix_of(definition.identifier)
        for definition in (*by_file_name, *by_case, *in_bodies)
        if definition.is_strong
    }
    return sorted(
        (
            definition
            for definition in (*by_file_name, *by_case, *in_bodies)
            if definition.is_strong
            or prefix_of(definition.identifier) not in strongly_defined_prefixes
        ),
        key=lambda definition: (definition.path.as_posix(), definition.line_number),
    )


def read_trace(bundle: Bundle, evals_directory: Path | None) -> Trace:
    """Return everything the trace is worked out from.

    Raises:
        UnreadableBundleError: If the eval suite cannot be read.
    """
    suite = read_eval_suite(evals_directory)
    return Trace(
        bundle=bundle,
        suite=suite,
        key_metrics=read_key_metrics(bundle),
        definitions=read_definitions(bundle, suite),
    )


def references_in(trace: Trace) -> list[Reference]:
    """Return every place an id is named: in prose, in a key metric's fields, in a case's fields.

    The address a link leads to is not prose: an id-shaped word in it belongs to wherever it leads.
    """
    in_prose = [
        Reference(matched.group("identifier"), concept.path, line.line_number, is_structured=False)
        for concept in trace.bundle.concepts
        if concept.frontmatter_problem is None
        for line in prose_lines(concept.body, concept.body_line_number)
        for matched in ID_PATTERN.finditer(without_addresses(line.text))
    ]
    in_metric_fields = [
        Reference(identifier, metric.document.path, metric.document.line_number_of(key), True)
        for metric in trace.key_metrics
        for key, identifiers in (
            (SUPPORTS_KEY, [metric.supports] if metric.supports else []),
            (PROVES_KEY, metric.proves),
        )
        for identifier in identifiers
    ]
    in_case_fields = [
        Reference(identifier, case.path, case.line_number_of(key), is_structured=True)
        for case in trace.cases
        for key, identifiers in ((GUARDS_KEY, case.guards), (METRICS_KEY, case.metrics))
        for identifier in identifiers
    ]
    return [*in_prose, *in_metric_fields, *in_case_fields]


def dangling_findings(trace: Trace) -> list[Finding]:
    """Return a finding for each id that is named and defined nowhere.

    In prose, only a word whose capitals start some defined id is taken for an id. In a field
    that holds ids, every entry is one.
    """
    defined_ids = trace.defined_ids
    known_prefixes = {prefix_of(identifier) for identifier in defined_ids}
    dangling_places = sorted(
        {
            (reference.path, reference.line_number, reference.identifier)
            for reference in references_in(trace)
            if reference.identifier not in defined_ids
            and (reference.is_structured or prefix_of(reference.identifier) in known_prefixes)
        },
        key=lambda place: (place[0].as_posix(), place[1], place[2]),
    )
    return [
        Finding(
            path,
            line_number,
            TRACE,
            f"`{identifier}` is defined nowhere: no heading, no eval case and no file of that"
            " name carries the id",
        )
        for path, line_number, identifier in dangling_places
    ]


def duplicate_findings(trace: Trace) -> list[Finding]:
    """Return a finding for each id that a second heading, file name or case defines."""
    strong_definitions = [definition for definition in trace.definitions if definition.is_strong]
    first_by_identifier = {
        definition.identifier: definition for definition in reversed(strong_definitions)
    }
    return [
        Finding(
            definition.path,
            definition.line_number,
            TRACE,
            f"`{definition.identifier}` is already defined at"
            f" {first_by_identifier[definition.identifier].path}:"
            f"{first_by_identifier[definition.identifier].line_number}; an id names one thing",
        )
        for definition in strong_definitions
        if first_by_identifier[definition.identifier] is not definition
    ]


def metric_shape_findings(metric: KeyMetric) -> list[Finding]:
    """Return what is wrong with how one key metric states its role, its id and what it proves."""
    document = metric.document
    allowed_roles = ", ".join(f"`{role}`" for role in ROLES)
    bad_role = (
        [
            Finding(
                document.path,
                document.line_number_of(ROLE_KEY),
                TRACE,
                f"`role` must be one of {allowed_roles}",
            )
        ]
        if metric.role not in ROLES
        else []
    )
    bad_name = (
        [
            Finding(
                document.path,
                1,
                TRACE,
                f"a key metric's file name is its id, such as `NS-01.md`; this one is"
                f" `{document.path.name}`",
            )
        ]
        if not WHOLE_ID_PATTERN.fullmatch(metric.identifier)
        else []
    )
    bad_proves = (
        [
            Finding(
                document.path,
                document.line_number_of(PROVES_KEY),
                TRACE,
                "`proves` must be a list of use case ids, such as `[UC-01, UC-02]`",
            )
        ]
        if PROVES_KEY in document.fields and not isinstance(document.fields[PROVES_KEY], list)
        else []
    )
    return [*bad_role, *bad_name, *bad_proves]


def north_star_findings(trace: Trace) -> list[Finding]:
    """Return a finding for each north star after the first, and each metric that supports none."""
    north_stars = trace.north_stars
    north_star_id = north_stars[0].identifier if north_stars else ""
    second_north_stars = [
        Finding(
            metric.document.path,
            metric.document.line_number_of(ROLE_KEY),
            TRACE,
            f"`{north_star_id}` is the north star already, and a project has one",
        )
        for metric in north_stars[1:]
    ]
    supporters = [metric for metric in trace.key_metrics if metric.role in (DRIVER, GUARDRAIL)]
    unsupported = [
        Finding(
            metric.document.path,
            metric.document.line_number_of(ROLE_KEY),
            TRACE,
            f"a {metric.role} supports the north star: add `supports: <the north star's id>`",
        )
        for metric in supporters
        if not metric.supports
    ]
    # A `supports` that names an id defined nowhere is reported as that, and not twice.
    misdirected = [
        Finding(
            metric.document.path,
            metric.document.line_number_of(SUPPORTS_KEY),
            TRACE,
            f"a {metric.role} supports the north star, and `{metric.supports}` is not it",
        )
        for metric in supporters
        if metric.supports
        and metric.supports in trace.defined_ids
        and metric.supports != north_star_id
    ]
    return [*second_north_stars, *unsupported, *misdirected]


def is_measured_by_a_computation(trace: Trace, metric: KeyMetric) -> bool:
    """Return whether a key metric's body links to a concept that is an attested computation."""
    document = metric.document
    linked_files = {
        resolved_path(target_path)
        for link in links_in(prose_lines(document.body, document.body_line_number))
        for target_path in [linked_path(trace.bundle.directory, document, link.target)]
        if target_path is not None
    }
    return any(
        concept.path.resolve() in linked_files and is_attested_computation(concept)
        for concept in trace.bundle.concepts
    )


def case_gaps(trace: Trace) -> list[Gap]:
    """Return the gaps in the cases themselves: one that guards nothing, one that feeds nothing."""
    guarding_nothing = [
        Gap(
            EVERY_CASE_NAMES_A_USE_CASE_OR_FINDING,
            case.path,
            case.line_number_of(GUARDS_KEY),
            f"{case.case_id} guards no use case and no finding",
        )
        for case in trace.cases
        if not case.guards
    ]
    feeding_nothing = [
        Gap(
            EVERY_CASE_NAMES_A_METRIC,
            case.path,
            case.line_number_of(METRICS_KEY),
            f"{case.case_id} feeds no metric",
        )
        for case in trace.cases
        if not case.metrics
    ]
    return [*guarding_nothing, *feeding_nothing]


def use_case_gaps(trace: Trace) -> list[Gap]:
    """Return a gap for each use case that no eval case guards."""
    guarded_ids = {identifier for case in trace.cases for identifier in case.guards}
    first_definition_by_id = {
        definition.identifier: definition for definition in reversed(trace.definitions)
    }
    return [
        Gap(
            EVERY_USE_CASE_HAS_A_CASE,
            definition.path,
            definition.line_number,
            f"{identifier} has no eval case",
        )
        for identifier, definition in sorted(first_definition_by_id.items())
        if prefix_of(identifier) == USE_CASE_PREFIX and identifier not in guarded_ids
    ]


def metric_gaps(trace: Trace) -> list[Gap]:
    """Return the gaps under the key metrics: unmeasured, or without the case its role needs."""
    placed_metrics = [metric for metric in trace.key_metrics if metric.role in ROLES]
    cases_by_metric_id = {
        metric.identifier: [case for case in trace.cases if metric.identifier in case.metrics]
        for metric in placed_metrics
    }
    unmeasured = [
        Gap(
            EVERY_METRIC_HAS_A_CASE_OR_A_COMPUTATION,
            metric.document.path,
            1,
            f"{metric.identifier} has neither an eval case nor a computation",
        )
        for metric in placed_metrics
        if not cases_by_metric_id[metric.identifier]
        and not is_measured_by_a_computation(trace, metric)
    ]
    north_star_without_core = [
        Gap(
            NORTH_STAR_HAS_A_CORE_CASE,
            metric.document.path,
            1,
            f"the north star {metric.identifier} has no case in the core tier",
        )
        for metric in placed_metrics
        if metric.role == NORTH_STAR
        and not any(case.tier == CORE_TIER for case in cases_by_metric_id[metric.identifier])
    ]
    guardrail_untested = [
        Gap(
            EVERY_GUARDRAIL_HAS_A_BOUNDARY_OR_REGRESSION_CASE,
            metric.document.path,
            1,
            f"the guardrail {metric.identifier} has no boundary case and no regression case",
        )
        for metric in placed_metrics
        if metric.role == GUARDRAIL
        and not any(
            case.case_type in CASE_TYPES_THAT_TEST_A_GUARDRAIL
            for case in cases_by_metric_id[metric.identifier]
        )
    ]
    return [*unmeasured, *north_star_without_core, *guardrail_untested]


def gaps_in(trace: Trace) -> list[Gap]:
    """Return everything the trace does not yet reach; nothing in a project with no eval suite."""
    if trace.suite is None:
        return []
    return [*case_gaps(trace), *use_case_gaps(trace), *metric_gaps(trace)]


def floor_state(trace: Trace, gap: Gap) -> str:
    """Return the words that say whether a gap's floor is on: for a finding, a note, the report."""
    return f"(the floor `{gap.floor}` is {'on' if is_refused(trace, gap) else 'off'})"


def is_refused(trace: Trace, gap: Gap) -> bool:
    """Return whether a gap's floor is on, which makes the gap a finding."""
    return trace.suite is not None and gap.floor in trace.suite.floors_on


def trace_findings(trace: Trace) -> list[Finding]:
    """Return everything that breaks the trace."""
    return [
        *(trace.suite.floor_findings if trace.suite is not None else []),
        *dangling_findings(trace),
        *duplicate_findings(trace),
        *(finding for metric in trace.key_metrics for finding in metric_shape_findings(metric)),
        *north_star_findings(trace),
        *(
            Finding(gap.path, gap.line_number, TRACE, f"{gap.message}  {floor_state(trace, gap)}")
            for gap in gaps_in(trace)
            if is_refused(trace, gap)
        ),
    ]


def trace_notes(trace: Trace) -> list[Note]:
    """Return a note for each gap whose floor is still off."""
    return [
        Note(gap.path, gap.line_number, f"{gap.message}  {floor_state(trace, gap)}")
        for gap in gaps_in(trace)
        if not is_refused(trace, gap)
    ]


def metric_lines(trace: Trace, metric: KeyMetric, indent: str) -> list[str]:
    """Return the lines of the report for one key metric: itself, what it proves, and its cases."""
    document = metric.document
    title = document.text_field(TITLE_KEY) or document.path.stem
    status = document.text_field(STATUS_KEY) or "-"
    role_words = metric.role.replace("-", " ")
    verdicts = trace.suite.verdict_by_case_id if trace.suite is not None else {}
    described_cases = [
        case.described(verdicts) for case in trace.cases if metric.identifier in case.metrics
    ]
    return [
        f"{indent}{metric.identifier}  {title}  ({role_words}, {status}, {trust_tier(document)})",
        *([f"{indent}  proves  {', '.join(metric.proves)}"] if metric.proves else []),
        *(
            f"{indent}  {'cases ' if case_index == 0 else '      '}  {described_case}"
            for case_index, described_case in enumerate(described_cases)
        ),
    ]


def use_case_lines(trace: Trace) -> list[str]:
    """Return the lines of the report that say which cases guard each use case."""
    use_case_ids = sorted(
        identifier for identifier in trace.defined_ids if prefix_of(identifier) == USE_CASE_PREFIX
    )
    guarding_case_ids = {
        identifier: [case.case_id for case in trace.cases if identifier in case.guards]
        for identifier in use_case_ids
    }
    return [
        *(["use cases"] if use_case_ids else []),
        *(
            f"  {identifier}  {', '.join(guarding_case_ids[identifier]) or '-'}"
            for identifier in use_case_ids
        ),
    ]


def trace_report(trace: Trace) -> list[str]:
    """Return the trace as lines to print: the north star, what supports it, the cases, the gaps."""
    north_stars = trace.north_stars
    supporters = [
        metric
        for role in (DRIVER, GUARDRAIL)
        for metric in trace.key_metrics
        if metric.role == role
    ]
    top_lines = (
        metric_lines(trace, north_stars[0], "")
        if north_stars
        else ["no north star yet: no concept of the bundle has `role: north-star`"]
    )
    supporter_indent = "  " if north_stars else ""
    gaps = gaps_in(trace)
    gap_lines = (
        ["no eval suite: the documents alone are traced"]
        if trace.suite is None
        else ["gaps", *(f"  {gap.message}  {floor_state(trace, gap)}" for gap in gaps)]
        if gaps
        else ["no gaps"]
    )
    return [
        *top_lines,
        *(line for metric in supporters for line in metric_lines(trace, metric, supporter_indent)),
        *use_case_lines(trace),
        *gap_lines,
    ]
