"""Attested computations (OKF 0.2, section 10): a number, and proof of how it was got.

A concept of `type: Attested Computation` holds the sanctioned way to compute a value, so that a
reader can confirm a number was produced by running it and not by improvising something else. Its
frontmatter is a contract:

    runtime      how the computation is run, which also says what a parameter means
    parameters   the named, typed holes a caller may fill, and nothing else
    computation  a file that holds the computation; or it is the one block of code in the body,
                 under a `# Computation` heading
    executor     `resource`: how to run it. `receipt`: the fields a run must hand back
    attester     `resource`: code that reads a receipt and returns a verdict

    computation   a contract with a part missing or malformed; a file it names that is not there;
                  an attester that is not Python, or that imports outside the standard library

An attester is deterministic: no model, and nothing a reader cannot run. Holding it to the standard
library is how the check keeps that true. The format leaves the shapes of a receipt and a verdict
to a later version, so the ones here are this project's own:

    attest(*, computation, parameters, receipt, claimed_value) -> {"ok", "reason", "details"}

`attest_value` is the consumer's side. Before the attester is asked, it refuses: a deprecated or
stale computation; a parameter that is not written `name=value`, is given twice, is not declared,
or is not of its declared type; a required parameter left out; and a receipt without a declared
field. An attester that fails, or ends the program, has given no verdict, and that is an error.
"""

import ast
import datetime
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from okf.documents import Bundle, Document
from okf.findings import COMPUTATION, Finding
from okf.markdown import PROSE, code_blocks, heading_of, markdown_lines
from okf.policy import linked_path
from okf.trust import STATUS_KEY, stale_since

ATTESTED_COMPUTATION_TYPE: Final = "Attested Computation"
TYPE_KEY: Final = "type"
RUNTIME_KEY: Final = "runtime"
PARAMETERS_KEY: Final = "parameters"
COMPUTATION_KEY: Final = "computation"
EXECUTOR_KEY: Final = "executor"
ATTESTER_KEY: Final = "attester"
RESOURCE_KEY: Final = "resource"
RECEIPT_KEY: Final = "receipt"
NAME_KEY: Final = "name"
PARAMETER_TYPE_KEY: Final = "type"
REQUIRED_KEY: Final = "required"
DEPRECATED: Final = "deprecated"

COMPUTATION_HEADING_TEXT: Final = "Computation"
PYTHON_SUFFIX: Final = ".py"
ATTEST_FUNCTION_NAME: Final = "attest"
VERDICT_OK_KEY: Final = "ok"
VERDICT_REASON_KEY: Final = "reason"
VERDICT_DETAILS_KEY: Final = "details"
PARAMETER_SEPARATOR: Final = "="
ATTESTER_MODULE_NAME: Final = "okf_attester"

INTEGER_TYPE: Final = "integer"
NUMBER_TYPE: Final = "number"
BOOLEAN_TYPE: Final = "boolean"
BOOLEAN_WORDS: Final = {"true": True, "false": False}


class CannotAttestError(Exception):
    """An attestation could not be run at all; the message says why. Not a verdict."""


class RefusalError(Exception):
    """An attestation is refused before the attester is asked; the message is the reason."""


@dataclass(frozen=True)
class ComputationSection:
    """The `# Computation` part of a concept's body: where its heading is, and its code blocks."""

    heading_line_number: int
    code_blocks: list[str]


@dataclass(frozen=True)
class Parameter:
    """One named hole of a computation: what a caller may supply, its type, whether it must."""

    name: str
    type_name: str
    is_required: bool


@dataclass(frozen=True)
class Verdict:
    """What an attestation concluded: whether the value stands, the reason when not, and facts."""

    is_ok: bool
    reason: str
    details: dict[str, object]


def is_attested_computation(document: Document) -> bool:
    """Return whether a concept is an attested computation."""
    return document.text_field(TYPE_KEY) == ATTESTED_COMPUTATION_TYPE


def computation_section(document: Document) -> ComputationSection | None:
    """Return the `# Computation` part of a concept's body, or None when it has no such heading.

    The part runs from the heading to the next heading. A heading shown in a code block is neither.
    """
    lines = markdown_lines(document.body, document.body_line_number)
    heading_indexes = [
        line_index
        for line_index, line in enumerate(lines)
        if line.kind == PROSE and heading_of(line.text) is not None
    ]
    computation_heading_indexes = [
        line_index
        for line_index in heading_indexes
        for heading in [heading_of(lines[line_index].text)]
        if heading is not None and heading.text == COMPUTATION_HEADING_TEXT
    ]
    if not computation_heading_indexes:
        return None
    heading_index = computation_heading_indexes[0]
    later_heading_indexes = [
        line_index for line_index in heading_indexes if line_index > heading_index
    ]
    section_end_index = later_heading_indexes[0] if later_heading_indexes else len(lines)
    return ComputationSection(
        heading_line_number=lines[heading_index].line_number,
        code_blocks=code_blocks(lines[heading_index + 1 : section_end_index]),
    )


def named_file(bundle: Bundle, document: Document, value: object) -> Path | None:
    """Return the file a path-valued field names, or None when it names none that is on disk.

    A path that starts with `/` is read from the bundle's own directory; any other, from the
    directory of the concept.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    target_path = linked_path(bundle.directory, document, value.strip())
    return target_path if target_path is not None and target_path.is_file() else None


def read_parameters(document: Document) -> list[Parameter]:
    """Return the well-formed parameters a contract declares."""
    entries = document.fields.get(PARAMETERS_KEY)
    return [
        Parameter(
            name=str(entry[NAME_KEY]),
            type_name=str(entry[PARAMETER_TYPE_KEY]),
            is_required=entry[REQUIRED_KEY] is True,
        )
        for entry in (entries if isinstance(entries, list) else [])
        if is_a_parameter(entry)
    ]


def is_a_parameter(entry: object) -> bool:
    """Return whether an entry of `parameters` has a name, a type, and says if it is required."""
    return (
        isinstance(entry, dict)
        and isinstance(entry.get(NAME_KEY), str)
        and isinstance(entry.get(PARAMETER_TYPE_KEY), str)
        and isinstance(entry.get(REQUIRED_KEY), bool)
    )


def contract_problems(document: Document) -> list[tuple[str, str]]:
    """Return what is wrong with a contract's `runtime` and `parameters`, each with its key."""
    runtime_problems = (
        [
            (
                RUNTIME_KEY,
                "an attested computation says how it is run: `runtime: shell`, `python`, ...",
            )
        ]
        if not document.text_field(RUNTIME_KEY)
        else []
    )
    entries = document.fields.get(PARAMETERS_KEY)
    if PARAMETERS_KEY not in document.fields:
        return runtime_problems
    if not isinstance(entries, list):
        return [*runtime_problems, (PARAMETERS_KEY, "`parameters` must be a list")]
    parameter_problems = [
        (
            PARAMETERS_KEY,
            f"parameter {entry_index + 1} must be `{{ name: <name>, type: <type>,"
            " required: <true or false> }`",
        )
        for entry_index, entry in enumerate(entries)
        if not is_a_parameter(entry)
    ]
    return [*runtime_problems, *parameter_problems]


def source_findings(bundle: Bundle, document: Document) -> list[Finding]:
    """Return what is wrong with where a contract holds its computation: no place, two, or a gap."""
    section = computation_section(document)
    block_count = len(section.code_blocks) if section is not None else 0
    if COMPUTATION_KEY in document.fields:
        line_number = document.line_number_of(COMPUTATION_KEY)
        if block_count:
            message = (
                "the computation is given twice, in `computation` and under `# Computation`; keep"
                " one"
            )
            return [Finding(document.path, line_number, COMPUTATION, message)]
        if named_file(bundle, document, document.fields[COMPUTATION_KEY]) is None:
            message = "`computation` names a file that is not there"
            return [Finding(document.path, line_number, COMPUTATION, message)]
        return []
    if section is not None and block_count > 1:
        message = (
            f"there are {block_count} blocks of code under `# Computation`; a computation is one"
        )
        return [Finding(document.path, section.heading_line_number, COMPUTATION, message)]
    if block_count == 0:
        message = (
            "an attested computation holds its computation: one block of code under a"
            " `# Computation` heading, or a `computation` field that names a file"
        )
        return [Finding(document.path, 1, COMPUTATION, message)]
    return []


def imported_module_names(python_source: str) -> list[str]:
    """Return the top-level name of every module a Python source imports; `.` for a relative one.

    Raises:
        SyntaxError: If the source is not valid Python.
    """
    tree = ast.parse(python_source)
    plain_imports = [
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    from_imports = [
        "." if node.level else (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    ]
    return [*plain_imports, *from_imports]


def attester_problem(bundle: Bundle, document: Document) -> str:
    """Return what is wrong with a contract's attester, or an empty string."""
    attester = document.fields.get(ATTESTER_KEY)
    attester_file = (
        named_file(bundle, document, attester.get(RESOURCE_KEY))
        if isinstance(attester, dict)
        else None
    )
    if attester_file is None:
        return "`attester.resource` must name the code that checks a receipt, and it is not there"
    if attester_file.suffix != PYTHON_SUFFIX:
        return f"its attester, {attester_file.name}, is not Python; an attester is a `.py` file"
    try:
        module_names = imported_module_names(attester_file.read_text(encoding="utf-8"))
    # Before Python 3.11.4 a null character in the source is a ValueError and not a SyntaxError.
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as error:
        return f"its attester, {attester_file.name}, cannot be read as Python: {error}"
    outside_names = sorted(
        {module_name for module_name in module_names if module_name not in sys.stdlib_module_names}
    )
    if outside_names:
        listed = ", ".join(f"`{module_name}`" for module_name in outside_names)
        return (
            f"its attester imports {listed}, from outside the standard library; an attester is"
            " code that any reader can run, with no model and no service behind it"
        )
    return ""


def executor_problem(bundle: Bundle, document: Document) -> str:
    """Return what is wrong with a contract's executor, or an empty string."""
    executor = document.fields.get(EXECUTOR_KEY)
    if not isinstance(executor, dict):
        return "`executor` must be `resource`, how to run the computation, and `receipt`"
    if named_file(bundle, document, executor.get(RESOURCE_KEY)) is None:
        return "`executor.resource` must name how the computation is run, and it is not there"
    receipt_fields = executor.get(RECEIPT_KEY)
    if not isinstance(receipt_fields, list) or not receipt_fields:
        return (
            "`executor.receipt` must list the fields a run hands back, such as `[job_id, result]`"
        )
    return ""


def computation_findings(bundle: Bundle, document: Document) -> list[Finding]:
    """Return what keeps an attested computation's contract from being one a reader can use."""
    if document.frontmatter_problem is not None or not is_attested_computation(document):
        return []
    missing_part = "an attested computation has an `{key}`: {what}"
    part_problems = [
        (key, missing_part.format(key=key, what=what) if key not in document.fields else problem)
        for key, what, problem in (
            (
                EXECUTOR_KEY,
                "how it is run, and what a run hands back",
                executor_problem(bundle, document),
            ),
            (ATTESTER_KEY, "the code that checks a receipt", attester_problem(bundle, document)),
        )
    ]
    return [
        *(
            Finding(document.path, document.line_number_of(key), COMPUTATION, problem)
            for key, problem in (*contract_problems(document), *part_problems)
            if problem
        ),
        *source_findings(bundle, document),
    ]


def computation_text(bundle: Bundle, document: Document) -> str:
    """Return the computation a contract holds: the file it names, or the block of code in its body.

    Raises:
        CannotAttestError: If the contract holds no computation that can be read.
    """
    computation_file = named_file(bundle, document, document.fields.get(COMPUTATION_KEY))
    if computation_file is not None:
        try:
            return computation_file.read_text(encoding="utf-8").strip("\n")
        except (OSError, UnicodeDecodeError) as error:
            message = f"the computation {computation_file} could not be read: {error}"
            raise CannotAttestError(message) from error
    section = computation_section(document)
    if section is None or len(section.code_blocks) != 1:
        message = f"{document.path} does not hold one computation"
        raise CannotAttestError(message)
    return section.code_blocks[0].strip("\n")


def typed_value(parameter: Parameter, written_value: str) -> object:
    """Return a parameter's value as the type the contract gives it.

    Raises:
        RefusalError: If the value is not of that type.
    """
    try:
        if parameter.type_name == INTEGER_TYPE:
            return int(written_value)
        if parameter.type_name == NUMBER_TYPE:
            return float(written_value)
    except ValueError as error:
        article = "an" if parameter.type_name == INTEGER_TYPE else "a"
        message = (
            f"`{parameter.name}` must be {article} {parameter.type_name}, not `{written_value}`"
        )
        raise RefusalError(message) from error
    if parameter.type_name == BOOLEAN_TYPE:
        if written_value not in BOOLEAN_WORDS:
            message = f"`{parameter.name}` must be true or false, not `{written_value}`"
            raise RefusalError(message)
        return BOOLEAN_WORDS[written_value]
    return written_value


def written_parameters(given_parameters: list[str]) -> dict[str, str]:
    """Return what a caller wrote for each parameter, by name.

    Raises:
        RefusalError: If one is not written `name=value`, or a name is given twice. Guessing which
            value was meant would attest a number for a run the caller did not describe.
    """
    names_and_values = [given.partition(PARAMETER_SEPARATOR) for given in given_parameters]
    not_name_and_value = [
        given
        for given, (name, separator, _value) in zip(given_parameters, names_and_values, strict=True)
        if not name or not separator
    ]
    if not_name_and_value:
        message = f"a parameter is written `name=value`, and `{not_name_and_value[0]}` is not"
        raise RefusalError(message)
    names = [name for name, _separator, _value in names_and_values]
    repeated_names = [name for name in names if names.count(name) > 1]
    if repeated_names:
        message = f"`{repeated_names[0]}` is given twice; a parameter has one value"
        raise RefusalError(message)
    return {name: value for name, _separator, value in names_and_values}


def bound_parameters(document: Document, given_parameters: list[str]) -> dict[str, object]:
    """Return the values a caller supplied, by name, each as the type the contract declares.

    A caller may fill the holes the contract declares, and no others.

    Raises:
        RefusalError: If a value is not written `name=value`, is given twice, is for no declared
            parameter or is not of its parameter's type, or a required one is left out.
    """
    declared = {parameter.name: parameter for parameter in read_parameters(document)}
    written_by_name = written_parameters(given_parameters)
    undeclared_names = [name for name in written_by_name if name not in declared]
    if undeclared_names:
        message = f"`{undeclared_names[0]}` is not a parameter of this computation"
        raise RefusalError(message)
    missing_names = [
        parameter.name
        for parameter in declared.values()
        if parameter.is_required and parameter.name not in written_by_name
    ]
    if missing_names:
        message = f"`{missing_names[0]}` is required, and no value was given for it"
        raise RefusalError(message)
    return {
        name: typed_value(declared[name], written_value)
        for name, written_value in written_by_name.items()
    }


def read_receipt(receipt_file: Path) -> dict[str, object]:
    """Return a receipt: the object a run handed back, as JSON.

    Raises:
        CannotAttestError: If the file is not there, or does not hold a JSON object.
    """
    try:
        receipt: object = json.loads(receipt_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        message = f"the receipt {receipt_file} could not be read: {error}"
        raise CannotAttestError(message) from error
    if not isinstance(receipt, dict):
        message = f"the receipt {receipt_file} must be a JSON object, with a field for each fact"
        raise CannotAttestError(message)
    return {str(key): value for key, value in receipt.items()}


def claimed_value_of(claimed_text: str) -> object:
    """Return a claimed value as what it reads as: a number, true or false, or else text."""
    try:
        claimed_value: object = json.loads(claimed_text)
    except json.JSONDecodeError:
        return claimed_text
    return claimed_value


def asked_of_the_attester(
    attester_file: Path,
    computation: str,
    parameters: dict[str, object],
    receipt: dict[str, object],
    claimed_value: object,
) -> Verdict:
    """Return the verdict of a contract's attester on one receipt and one claimed value.

    Raises:
        CannotAttestError: If the attester cannot be loaded, fails, ends the program, or returns
            no verdict.
    """
    # The attester sits in the bundle; running it must leave nothing behind there.
    sys.dont_write_bytecode = True
    module_spec = importlib.util.spec_from_file_location(ATTESTER_MODULE_NAME, attester_file)
    if module_spec is None or module_spec.loader is None:
        message = f"the attester {attester_file} could not be loaded"
        raise CannotAttestError(message)
    attester_module = importlib.util.module_from_spec(module_spec)
    # A dataclass looks its own module up by name, so the module is registered while it runs.
    sys.modules[ATTESTER_MODULE_NAME] = attester_module
    try:
        module_spec.loader.exec_module(attester_module)
        attest_function = getattr(attester_module, ATTEST_FUNCTION_NAME)
        raw_verdict: object = attest_function(
            computation=computation,
            parameters=parameters,
            receipt=receipt,
            claimed_value=claimed_value,
        )
    except KeyboardInterrupt:
        raise
    # An attester is the project's own code. It may fail in any way, or end the program, which
    # would leave the exit code of a value that was attested. Every way is the same answer.
    except BaseException as error:
        message = f"the attester {attester_file} failed: {error!r}"
        raise CannotAttestError(message) from error
    finally:
        sys.modules.pop(ATTESTER_MODULE_NAME, None)
    if not isinstance(raw_verdict, dict) or not isinstance(raw_verdict.get(VERDICT_OK_KEY), bool):
        message = (
            f"the attester {attester_file} returned no verdict: it must return `ok`, true or false"
        )
        raise CannotAttestError(message)
    details = raw_verdict.get(VERDICT_DETAILS_KEY)
    return Verdict(
        is_ok=raw_verdict[VERDICT_OK_KEY] is True,
        reason=str(raw_verdict.get(VERDICT_REASON_KEY) or ""),
        details=dict(details) if isinstance(details, dict) else {},
    )


def attest_value(
    bundle: Bundle,
    document: Document,
    receipt_file: Path,
    claimed_text: str,
    given_parameters: list[str],
    *,
    now: datetime.datetime,
) -> Verdict:
    """Return whether a claimed value was produced by running a computation the sanctioned way.

    Raises:
        CannotAttestError: If the concept is not an attested computation, the receipt cannot be
            read, or the attester cannot be asked.
    """
    if not is_attested_computation(document):
        message = f"{document.path} is not a concept of `type: {ATTESTED_COMPUTATION_TYPE}`"
        raise CannotAttestError(message)
    receipt = read_receipt(receipt_file)
    executor = document.fields.get(EXECUTOR_KEY)
    attester = document.fields.get(ATTESTER_KEY)
    attester_file = named_file(
        bundle, document, attester.get(RESOURCE_KEY) if isinstance(attester, dict) else None
    )
    if attester_file is None or not isinstance(executor, dict):
        message = f"{document.path} names no attester and executor that can be used"
        raise CannotAttestError(message)
    try:
        if document.fields.get(STATUS_KEY) == DEPRECATED:
            message = "the computation is deprecated; it is kept for history and no longer the way"
            raise RefusalError(message)
        passed_time = stale_since(document, now)
        if passed_time:
            message = f"the computation is stale since {passed_time}; check it still holds, first"
            raise RefusalError(message)
        parameters = bound_parameters(document, given_parameters)
        receipt_fields = executor.get(RECEIPT_KEY)
        missing_fields = [
            str(field)
            for field in (receipt_fields if isinstance(receipt_fields, list) else [])
            if str(field) not in receipt
        ]
        if missing_fields:
            message = (
                f"the receipt has no `{missing_fields[0]}`, which the contract says a run hands"
                " back"
            )
            raise RefusalError(message)
    except RefusalError as refusal:
        return Verdict(is_ok=False, reason=str(refusal), details={})
    return asked_of_the_attester(
        attester_file,
        computation_text(bundle, document),
        parameters,
        receipt,
        claimed_value_of(claimed_text),
    )
