"""Check Python files against the rules that ruff and mypy cannot check.

    python scripts/check_python_rules.py src tests

The gate's lint group runs it (scripts/gate.sh). The rules are stated in
docs/rules/python-conventions.md:

    assign-once   a parameter or a name is bound a second time on one path through its scope
    final         a module-level constant is not annotated `Final`
    short-name    a name has fewer than three characters
    suppression   an escape hatch gives no reason, names no rule, or silences nothing

Assign-once follows each scope statement by statement. A name may be bound once in each branch that
excludes the others (if and else, try and except, the arms of a match). A branch that ends in raise,
return, continue or break does not flow on. A name bound before a loop may be updated inside it, and
a loop variable belongs to its loop. ruff already reports an overwritten loop variable (PLW2901) and
a parameter rebound by a loop (PLR1704), so this check leaves those two to ruff.

A constant is a name in capitals bound by a top-level statement of a module. A short name is
allowed for a one-letter variable of a loop or a comprehension of at most two lines, and for a type
variable. Names that an import brings in are not checked, nor names that Python dictates (`__eq__`).

The escape hatch is a comment on the finding's line that names the rule and gives the reason:

    amount = amount + fee  # ai-kit: ignore-assign  <why>
    RETRY_LIMIT = 3  # ai-kit: ignore-final  <why>
    x = 0.5  # ai-kit: ignore-name  <why>

Exit 0: no findings. Exit 1: findings, one a line, as path:line:column: rule message.
Exit 2: no path was given, or a path could not be read as Python.
"""

import ast
import io
import re
import sys
import tokenize
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

EXIT_CLEAN: Final = 0
EXIT_FINDINGS: Final = 1
EXIT_COULD_NOT_RUN: Final = 2

ASSIGN_ONCE: Final = "assign-once"
FINAL: Final = "final"
SHORT_NAME: Final = "short-name"
SUPPRESSION: Final = "suppression"
RULE_BY_HATCH_NAME: Final = {"assign": ASSIGN_ONCE, "final": FINAL, "name": SHORT_NAME}
HATCH_PATTERN: Final = re.compile(r"#\s*ai-kit:\s*ignore-(?P<hatch_name>[a-z-]+)(?P<reason>.*)")

THROWAWAY_NAME: Final = "_"
SKIPPED_DIRECTORY_NAMES: Final = frozenset({".venv", "node_modules", "__pycache__", ".git"})
NESTED_SCOPE_NODES: Final = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
FLOW_ENDING_STATEMENTS: Final = (ast.Return, ast.Raise, ast.Continue, ast.Break)

CONSTANT_NAME_PATTERN: Final = re.compile(r"_*[A-Z][A-Z0-9_]*")
FINAL_QUALIFIER: Final = "Final"
TYPE_VARIABLE_FACTORIES: Final = frozenset({"TypeVar", "ParamSpec", "TypeVarTuple"})

MINIMUM_NAME_LENGTH: Final = 3
SHORT_LOOP_LINE_COUNT: Final = 2
NAME_INTRODUCING_NODES: Final = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.arg,
    ast.Name,
    ast.ExceptHandler,
    ast.MatchAs,
    ast.MatchStar,
    ast.MatchMapping,
)
LOOPING_NODES: Final = (
    ast.For,
    ast.AsyncFor,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


@dataclass(frozen=True)
class Finding:
    """One broken rule at one place in one file.

    A hatch silences the finding from any line between `line_number` and `last_line_number`, so that
    it can follow a statement that spans several lines.
    """

    path: Path
    line_number: int
    last_line_number: int
    column_number: int
    rule: str
    message: str

    def render(self) -> str:
        """Return the finding as one line a person or an editor can jump to."""
        return f"{self.path}:{self.line_number}:{self.column_number}: {self.rule} {self.message}"


@dataclass(frozen=True)
class Hatch:
    """One escape-hatch comment: the rule it names and the reason it gives."""

    line_number: int
    column_number: int
    hatch_name: str
    reason: str


@dataclass(frozen=True)
class Flow:
    """The names that hold a value after some statements, on the paths that reach their end."""

    bound_names: frozenset[str] = frozenset()
    loop_variable_names: frozenset[str] = frozenset()
    terminates: bool = False


@dataclass(frozen=True)
class LoopContext:
    """What the enclosing loops change: the names they may update, and their own variables."""

    names_bound_before: frozenset[str] = frozenset()
    variable_names: frozenset[str] = frozenset()


class UnreadablePathError(Exception):
    """A path given on the command line does not exist or does not hold valid Python."""


def joined(branch_flows: Sequence[Flow]) -> Flow:
    """Return what holds after branches that exclude each other.

    A branch that ended in raise, return, continue or break contributes nothing. When every branch
    ended that way, so does the whole statement.
    """
    continuing_flows = [flow for flow in branch_flows if not flow.terminates]
    considered_flows = continuing_flows or list(branch_flows)
    return Flow(
        bound_names=frozenset().union(*(flow.bound_names for flow in considered_flows)),
        loop_variable_names=frozenset().union(
            *(flow.loop_variable_names for flow in considered_flows)
        ),
        terminates=not continuing_flows,
    )


def plain_names(target: ast.expr) -> list[ast.Name]:
    """Return the names a target binds; an attribute or an item changes an object, not a name."""
    if isinstance(target, ast.Name):
        return [target]
    if isinstance(target, ast.Tuple | ast.List):
        return [name for element in target.elts for name in plain_names(element)]
    if isinstance(target, ast.Starred):
        return plain_names(target.value)
    return []


def assigned_names(statement: ast.stmt) -> list[ast.Name]:
    """Return the names an assignment statement binds, in source order."""
    if isinstance(statement, ast.Assign):
        return [name for target in statement.targets for name in plain_names(target)]
    if isinstance(statement, ast.AnnAssign) and statement.value is not None:
        return plain_names(statement.target)
    if isinstance(statement, ast.AugAssign):
        return plain_names(statement.target)
    return []


def named_expressions(roots: Sequence[ast.AST]) -> list[ast.NamedExpr]:
    """Return the walrus expressions under the nodes that bind in this scope, in source order."""
    pending_nodes = list(roots)
    found_expressions: list[ast.NamedExpr] = []
    while pending_nodes:
        node = pending_nodes.pop()
        if isinstance(node, NESTED_SCOPE_NODES):
            continue
        if isinstance(node, ast.NamedExpr):
            found_expressions.append(node)
        pending_nodes.extend(ast.iter_child_nodes(node))
    return sorted(found_expressions, key=lambda walrus: (walrus.lineno, walrus.col_offset))


def captured_names(pattern: ast.pattern) -> list[tuple[str, ast.pattern]]:
    """Return each name a match pattern binds, with the part of the pattern that binds it."""
    captures: list[tuple[str, ast.pattern]] = []
    for node in ast.walk(pattern):
        if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name is not None:
            captures.append((node.name, node))
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            captures.append((node.rest, node))
    return captures


def is_catch_all(case: ast.match_case) -> bool:
    """Say whether a match arm takes every subject the arms above it did not."""
    pattern = case.pattern
    return isinstance(pattern, ast.MatchAs) and pattern.pattern is None and case.guard is None


def parameter_names(scope_node: ast.AST) -> frozenset[str]:
    """Return the name of every parameter a function declares; a module or a class has none."""
    if not isinstance(scope_node, ast.FunctionDef | ast.AsyncFunctionDef):
        return frozenset()
    arguments = scope_node.args
    positional_and_keyword = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    variadic = [extra for extra in (arguments.vararg, arguments.kwarg) if extra is not None]
    return frozenset(argument.arg for argument in [*positional_and_keyword, *variadic])


def names_declared_elsewhere(scope_node: ast.AST) -> frozenset[str]:
    """Return the names a scope marks `global` or `nonlocal`: they belong to another scope."""
    declarations = [
        node for node in ast.walk(scope_node) if isinstance(node, ast.Global | ast.Nonlocal)
    ]
    return frozenset(name for declaration in declarations for name in declaration.names)


class AssignOnceScope:
    """Follows one scope (a module, a class body or a function body) and reports second bindings."""

    def __init__(
        self, path: Path, parameters: frozenset[str], names_from_other_scopes: frozenset[str]
    ) -> None:
        """Start a scope with its parameters and the names it borrows from other scopes."""
        self._path = path
        self._parameters = parameters
        self._names_from_other_scopes = names_from_other_scopes
        self.findings: list[Finding] = []

    def block(self, statements: Sequence[ast.stmt], flow: Flow, loop: LoopContext) -> Flow:
        """Follow statements that run one after another and return what holds after the last."""
        flow_so_far = flow
        for statement in statements:
            flow_so_far = self._statement(statement, flow_so_far, loop)
        return flow_so_far

    def _statement(self, statement: ast.stmt, flow: Flow, loop: LoopContext) -> Flow:
        """Follow one statement, whatever its kind."""
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            flow_after = flow
        elif isinstance(statement, ast.For | ast.AsyncFor):
            flow_after = self._for_loop(statement, flow, loop)
        elif isinstance(statement, ast.While):
            flow_after = self._while_loop(statement, flow, loop)
        elif isinstance(statement, ast.If):
            flow_after = self._if_statement(statement, flow, loop)
        elif isinstance(statement, ast.Try | ast.TryStar):
            flow_after = self._try_statement(statement, flow, loop)
        elif isinstance(statement, ast.With | ast.AsyncWith):
            flow_after = self._with_statement(statement, flow, loop)
        elif isinstance(statement, ast.Match):
            flow_after = self._match_statement(statement, flow, loop)
        else:
            flow_after = self._simple_statement(statement, flow, loop)
        return flow_after

    def _simple_statement(self, statement: ast.stmt, flow: Flow, loop: LoopContext) -> Flow:
        """Follow a statement with no block of its own: bind what it assigns."""
        last_line_number = statement.end_lineno or statement.lineno
        flow_after_targets = self._bind_walruses([statement], flow, loop)
        for name in assigned_names(statement):
            flow_after_targets = self._bind(
                name.id, name, last_line_number, flow_after_targets, loop
            )
        ends_the_flow = isinstance(statement, FLOW_ENDING_STATEMENTS)
        return replace(flow_after_targets, terminates=flow.terminates or ends_the_flow)

    def _if_statement(self, statement: ast.If, flow: Flow, loop: LoopContext) -> Flow:
        """Follow both branches from the same start: each may bind a name once."""
        flow_after_test = self._bind_walruses([statement.test], flow, loop)
        return joined(
            [
                self.block(statement.body, flow_after_test, loop),
                self.block(statement.orelse, flow_after_test, loop),
            ]
        )

    def _try_statement(
        self, statement: ast.Try | ast.TryStar, flow: Flow, loop: LoopContext
    ) -> Flow:
        """Follow the body and each handler from the same start, then the finally block."""
        flow_after_body = self.block(statement.body, flow, loop)
        flow_after_else = self.block(statement.orelse, flow_after_body, loop)
        handler_flows = [self.block(handler.body, flow, loop) for handler in statement.handlers]
        return self.block(statement.finalbody, joined([flow_after_else, *handler_flows]), loop)

    def _match_statement(self, statement: ast.Match, flow: Flow, loop: LoopContext) -> Flow:
        """Follow every arm from the same start; without a catch-all, no arm may run at all."""
        flow_after_subject = self._bind_walruses([statement.subject], flow, loop)
        arm_flows = [self._match_arm(case, flow_after_subject, loop) for case in statement.cases]
        takes_every_subject = any(is_catch_all(case) for case in statement.cases)
        return joined(arm_flows if takes_every_subject else [*arm_flows, flow_after_subject])

    def _match_arm(self, case: ast.match_case, flow: Flow, loop: LoopContext) -> Flow:
        """Bind what the arm's pattern captures, then follow its guard and its body."""
        flow_after_captures = flow
        for captured_name, capturing_pattern in captured_names(case.pattern):
            flow_after_captures = self._bind(
                captured_name,
                capturing_pattern,
                capturing_pattern.lineno,
                flow_after_captures,
                loop,
            )
        guards = [case.guard] if case.guard is not None else []
        return self.block(case.body, self._bind_walruses(guards, flow_after_captures, loop), loop)

    def _with_statement(
        self, statement: ast.With | ast.AsyncWith, flow: Flow, loop: LoopContext
    ) -> Flow:
        """Bind the names after `as`, then follow the body."""
        context_expressions = [item.context_expr for item in statement.items]
        targets = [item.optional_vars for item in statement.items if item.optional_vars is not None]
        # ruff reports a parameter rebound by a with target (PLR1704); one finding is enough.
        new_names = [
            name
            for target in targets
            for name in plain_names(target)
            if name.id not in self._parameters
        ]
        flow_after_targets = self._bind_walruses(context_expressions, flow, loop)
        for name in new_names:
            flow_after_targets = self._bind(name.id, name, name.lineno, flow_after_targets, loop)
        return self.block(statement.body, flow_after_targets, loop)

    def _for_loop(self, statement: ast.For | ast.AsyncFor, flow: Flow, loop: LoopContext) -> Flow:
        """Follow a for loop: its variables are its own, and it may update names bound before it."""
        flow_before_loop = self._bind_walruses([statement.iter], flow, loop)
        loop_variables = plain_names(statement.target)
        flow_inside = flow_before_loop
        for loop_variable in loop_variables:
            flow_inside = self._bind_loop_variable(loop_variable, flow_inside)
        body_context = LoopContext(
            names_bound_before=flow_before_loop.bound_names,
            variable_names=loop.variable_names | {name.id for name in loop_variables},
        )
        flow_after_body = self.block(statement.body, flow_inside, body_context)
        return self._after_loop(flow_inside, flow_after_body, statement.orelse, loop)

    def _while_loop(self, statement: ast.While, flow: Flow, loop: LoopContext) -> Flow:
        """Follow a while loop: it may update names bound before it."""
        flow_after_test = self._bind_walruses([statement.test], flow, loop)
        body_context = LoopContext(
            names_bound_before=flow.bound_names, variable_names=loop.variable_names
        )
        flow_after_body = self.block(statement.body, flow_after_test, body_context)
        return self._after_loop(flow_after_test, flow_after_body, statement.orelse, loop)

    def _after_loop(
        self,
        flow_before_body: Flow,
        flow_after_body: Flow,
        else_statements: Sequence[ast.stmt],
        loop: LoopContext,
    ) -> Flow:
        """Join a loop that ran with one that did not, then follow the loop's else block.

        A loop never ends the flow here: a break inside it leads to the statement after it.
        """
        flow_after_iterations = Flow(
            bound_names=flow_before_body.bound_names | flow_after_body.bound_names,
            loop_variable_names=(
                flow_before_body.loop_variable_names | flow_after_body.loop_variable_names
            ),
            terminates=flow_before_body.terminates,
        )
        flow_after_else = self.block(else_statements, flow_after_iterations, loop)
        return replace(flow_after_else, terminates=flow_before_body.terminates)

    def _bind_walruses(self, roots: Sequence[ast.AST], flow: Flow, loop: LoopContext) -> Flow:
        """Bind the names that walrus expressions under the nodes assign."""
        flow_after_walruses = flow
        for walrus in named_expressions(roots):
            flow_after_walruses = self._bind(
                walrus.target.id,
                walrus.target,
                walrus.end_lineno or walrus.lineno,
                flow_after_walruses,
                loop,
            )
        return flow_after_walruses

    def _bind_loop_variable(self, name: ast.Name, flow: Flow) -> Flow:
        """Record a loop variable; a later loop may use the name again, an assignment may not."""
        identifier = name.id
        # ruff reports a parameter rebound by a loop (PLR1704); one finding is enough.
        if (
            identifier == THROWAWAY_NAME
            or identifier in self._names_from_other_scopes | self._parameters
        ):
            return flow
        if identifier in flow.bound_names:
            self._report(
                name,
                name.lineno,
                f"`{identifier}` already holds a value; give the loop variable its own name",
            )
        return replace(flow, loop_variable_names=flow.loop_variable_names | {identifier})

    def _bind(
        self,
        identifier: str,
        node: ast.expr | ast.pattern,
        last_line_number: int,
        flow: Flow,
        loop: LoopContext,
    ) -> Flow:
        """Record a binding, and report it when the name already holds a value on this path."""
        # ruff reports a loop variable overwritten inside its loop (PLW2901); one finding is enough.
        is_left_alone = (
            identifier == THROWAWAY_NAME
            or identifier in self._names_from_other_scopes
            or identifier in loop.variable_names
        )
        if is_left_alone:
            return flow
        if identifier in self._parameters:
            self._report(
                node,
                last_line_number,
                f"`{identifier}` is a parameter; bind the new value to a new name",
            )
            return flow
        holds_a_value = identifier in flow.bound_names | flow.loop_variable_names
        if holds_a_value and identifier not in loop.names_bound_before:
            self._report(
                node,
                last_line_number,
                f"`{identifier}` already holds a value; bind the new one to a new name",
            )
        return replace(flow, bound_names=flow.bound_names | {identifier})

    def _report(self, node: ast.expr | ast.pattern, last_line_number: int, message: str) -> None:
        """Add an assign-once finding at the node's place."""
        self.findings.append(
            Finding(
                path=self._path,
                line_number=node.lineno,
                last_line_number=max(last_line_number, node.lineno),
                column_number=node.col_offset + 1,
                rule=ASSIGN_ONCE,
                message=message,
            )
        )


def assign_once_findings(path: Path, tree: ast.Module) -> list[Finding]:
    """Return every second binding in the module, in its classes and in its functions."""
    scope_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    findings: list[Finding] = []
    for scope_node in scope_nodes:
        scope = AssignOnceScope(
            path, parameter_names(scope_node), names_declared_elsewhere(scope_node)
        )
        scope.block(scope_node.body, Flow(), LoopContext())
        findings.extend(scope.findings)
    return findings


def is_type_variable(value: ast.expr) -> bool:
    """Say whether an expression creates a type variable, which keeps its short name."""
    if not isinstance(value, ast.Call):
        return False
    factory = value.func
    if isinstance(factory, ast.Name):
        return factory.id in TYPE_VARIABLE_FACTORIES
    return isinstance(factory, ast.Attribute) and factory.attr in TYPE_VARIABLE_FACTORIES


def is_final_annotation(annotation: ast.expr) -> bool:
    """Say whether an annotation is `Final`, bare or with a type, however it was imported."""
    qualifier = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    if isinstance(qualifier, ast.Name):
        return qualifier.id == FINAL_QUALIFIER
    return isinstance(qualifier, ast.Attribute) and qualifier.attr == FINAL_QUALIFIER


def names_needing_final(statement: ast.stmt) -> list[ast.Name]:
    """Return the names a top-level statement binds without saying they are final."""
    if isinstance(statement, ast.Assign) and not is_type_variable(statement.value):
        bound_names = [name for target in statement.targets for name in plain_names(target)]
    elif (
        isinstance(statement, ast.AnnAssign)
        and statement.value is not None
        and not is_final_annotation(statement.annotation)
    ):
        bound_names = plain_names(statement.target)
    else:
        bound_names = []
    return [name for name in bound_names if CONSTANT_NAME_PATTERN.fullmatch(name.id)]


def final_findings(path: Path, tree: ast.Module) -> list[Finding]:
    """Return a finding for every module-level constant that is not annotated `Final`."""
    return [
        Finding(
            path=path,
            line_number=name.lineno,
            last_line_number=statement.end_lineno or name.lineno,
            column_number=name.col_offset + 1,
            rule=FINAL,
            message=(
                f"`{name.id}` is a module-level constant; annotate it `Final`, "
                f"or write a type alias as `type {name.id} = ...`"
            ),
        )
        for statement in tree.body
        for name in names_needing_final(statement)
    ]


def name_introduced_by(node: ast.AST) -> str | None:
    """Return the name a node brings into being, or None when it brings none."""
    introduced_name: str | None
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        introduced_name = node.name
    elif isinstance(node, ast.arg):
        introduced_name = node.arg
    elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        introduced_name = node.id
    elif isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar):
        introduced_name = node.name
    elif isinstance(node, ast.MatchMapping):
        introduced_name = node.rest
    else:
        introduced_name = None
    return introduced_name


def loop_targets(looping_node: ast.AST) -> list[ast.expr]:
    """Return the targets of a for statement or of a comprehension's clauses."""
    if isinstance(looping_node, ast.For | ast.AsyncFor):
        return [looping_node.target]
    if isinstance(looping_node, ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp):
        return [clause.target for clause in looping_node.generators]
    return []


def positions_allowed_a_short_name(tree: ast.Module) -> frozenset[tuple[int, int]]:
    """Return where a short name is allowed: a short loop's one-letter variable, a type variable.

    The target of an augmented assignment is here too: it updates a name and introduces none.
    """
    short_loops = [
        node
        for node in ast.walk(tree)
        if isinstance(node, LOOPING_NODES)
        and (node.end_lineno or node.lineno) - node.lineno < SHORT_LOOP_LINE_COUNT
    ]
    loop_variables = [
        name
        for short_loop in short_loops
        for target in loop_targets(short_loop)
        for name in plain_names(target)
        if len(name.id) == 1
    ]
    type_variables = [
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and is_type_variable(node.value)
        for target in node.targets
        for name in plain_names(target)
    ]
    updated_names = [
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.AugAssign)
        for name in plain_names(node.target)
    ]
    return frozenset(
        (name.lineno, name.col_offset)
        for name in [*loop_variables, *type_variables, *updated_names]
    )


def last_lines_of_assignments(tree: ast.Module) -> dict[tuple[int, int], int]:
    """Return, for each name an assignment binds, the last line of that assignment."""
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign | ast.AnnAssign)]
    return {
        (name.lineno, name.col_offset): assignment.end_lineno or name.lineno
        for assignment in assignments
        for target in (
            assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
        )
        for name in plain_names(target)
    }


def short_name_findings(path: Path, tree: ast.Module) -> list[Finding]:
    """Return a finding for every name introduced with fewer than three characters."""
    allowed_positions = positions_allowed_a_short_name(tree)
    last_line_numbers = last_lines_of_assignments(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, NAME_INTRODUCING_NODES):
            continue
        introduced_name = name_introduced_by(node)
        position = (node.lineno, node.col_offset)
        is_dictated_by_python = introduced_name is not None and (
            introduced_name.startswith("__") and introduced_name.endswith("__")
        )
        if introduced_name is None or position in allowed_positions or is_dictated_by_python:
            continue
        if 0 < len(introduced_name.strip("_")) < MINIMUM_NAME_LENGTH:
            findings.append(
                Finding(
                    path=path,
                    line_number=node.lineno,
                    last_line_number=last_line_numbers.get(position, node.lineno),
                    column_number=node.col_offset + 1,
                    rule=SHORT_NAME,
                    message=(
                        f"`{introduced_name}` has fewer than {MINIMUM_NAME_LENGTH} characters; "
                        "name it for what it is"
                    ),
                )
            )
    return findings


def hatches_in(source_text: str) -> list[Hatch]:
    """Return every escape-hatch comment in the source."""
    comment_tokens = [
        token
        for token in tokenize.generate_tokens(io.StringIO(source_text).readline)
        if token.type == tokenize.COMMENT
    ]
    hatches: list[Hatch] = []
    for token in comment_tokens:
        matched = HATCH_PATTERN.search(token.string)
        if matched is not None:
            hatches.append(
                Hatch(
                    line_number=token.start[0],
                    column_number=token.start[1] + matched.start() + 1,
                    hatch_name=matched.group("hatch_name"),
                    reason=matched.group("reason").strip(),
                )
            )
    return hatches


def silenced_by(hatch: Hatch, findings: Sequence[Finding]) -> list[Finding]:
    """Return the findings a hatch covers: those of its rule on the line it sits on."""
    rule = RULE_BY_HATCH_NAME.get(hatch.hatch_name)
    return [
        finding
        for finding in findings
        if finding.rule == rule
        and finding.line_number <= hatch.line_number <= finding.last_line_number
    ]


def hatch_problem(hatch: Hatch, silenced_findings: Sequence[Finding]) -> str | None:
    """Return what is wrong with a hatch, or None when it is used as it should be."""
    if hatch.hatch_name not in RULE_BY_HATCH_NAME:
        known_hatches = ", ".join(f"ignore-{name}" for name in sorted(RULE_BY_HATCH_NAME))
        return f"`ignore-{hatch.hatch_name}` names no rule; the hatches are: {known_hatches}"
    if not silenced_findings:
        return f"`ignore-{hatch.hatch_name}` silences nothing on this line; remove it"
    if not hatch.reason:
        return f"`ignore-{hatch.hatch_name}` gives no reason; say why after it"
    return None


def after_hatches(
    path: Path, findings: Sequence[Finding], hatches: Sequence[Hatch]
) -> list[Finding]:
    """Return the findings that no hatch silences, plus one for every hatch that is misused."""
    silenced_findings_by_hatch = [(hatch, silenced_by(hatch, findings)) for hatch in hatches]
    silenced_findings = [
        finding for _, hatch_findings in silenced_findings_by_hatch for finding in hatch_findings
    ]
    hatch_findings = [
        Finding(
            path=path,
            line_number=hatch.line_number,
            last_line_number=hatch.line_number,
            column_number=hatch.column_number,
            rule=SUPPRESSION,
            message=problem,
        )
        for hatch, covered_findings in silenced_findings_by_hatch
        for problem in [hatch_problem(hatch, covered_findings)]
        if problem is not None
    ]
    remaining_findings = [finding for finding in findings if finding not in silenced_findings]
    return [*remaining_findings, *hatch_findings]


def python_files(given_path: Path) -> list[Path]:
    """Return the Python files a command-line path names: itself, or every one below it.

    Raises:
        UnreadablePathError: If the path does not exist.
    """
    if given_path.is_file():
        return [given_path]
    if not given_path.is_dir():
        message = f"{given_path} does not exist"
        raise UnreadablePathError(message)
    return sorted(
        candidate
        for candidate in given_path.rglob("*.py")
        if not SKIPPED_DIRECTORY_NAMES.intersection(candidate.parts)
    )


def findings_in_file(path: Path) -> list[Finding]:
    """Return every finding in one file, in the order of its lines.

    Raises:
        UnreadablePathError: If the file is not valid Python.
    """
    try:
        with tokenize.open(path) as source_file:
            source_text = source_file.read()
        tree = ast.parse(source_text, filename=str(path))
        hatches = hatches_in(source_text)
    except (OSError, SyntaxError, UnicodeDecodeError, tokenize.TokenError) as error:
        message = f"{path} could not be read as Python: {error}"
        raise UnreadablePathError(message) from error
    rule_findings = [
        *assign_once_findings(path, tree),
        *final_findings(path, tree),
        *short_name_findings(path, tree),
    ]
    return sorted(
        after_hatches(path, rule_findings, hatches),
        key=lambda finding: (finding.line_number, finding.column_number),
    )


def main(arguments: list[str]) -> int:
    """Check the paths named on the command line and report what breaks the rules."""
    if not arguments:
        sys.stderr.write("python rules: name at least one file or directory to check\n")
        return EXIT_COULD_NOT_RUN
    try:
        files = [file for argument in arguments for file in python_files(Path(argument))]
        findings = [finding for file in files for finding in findings_in_file(file)]
    except UnreadablePathError as error:
        sys.stderr.write(f"python rules: {error}\n")
        return EXIT_COULD_NOT_RUN
    if findings:
        sys.stdout.write("".join(f"{finding.render()}\n" for finding in findings))
        sys.stdout.write(f"python rules: {len(findings)} finding(s) in {len(files)} file(s)\n")
        return EXIT_FINDINGS
    sys.stdout.write(f"python rules: {len(files)} file(s), no findings\n")
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
