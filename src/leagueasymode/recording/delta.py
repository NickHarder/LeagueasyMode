"""The changes between two JSON documents, as a subset of JSON Patch (RFC 6902).

The game's API answers with the whole game state, about the same each time, several times a second.
A recording stores the first answer whole and each later one as the operations that turn the
previous answer into it, which is a few hundred bytes instead of tens of kilobytes.

Only `add`, `remove` and `replace` are used, with paths written as JSON Pointers (RFC 6901), so any
JSON Patch library can read what this module writes.
"""

import copy
from collections.abc import Sequence
from typing import Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    SerializerFunctionWrapHandler,
    model_serializer,
)

ROOT_HOLDER_INDEX: Final = "0"


class PatchOperation(BaseModel):
    """One step of a patch: add, remove or replace the value at a path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    op: Literal["add", "remove", "replace"]  # ai-kit: ignore-name  JSON Patch names this field "op"
    path: str
    value: JsonValue = None

    @model_serializer(mode="wrap")
    def _leave_out_the_value_of_a_remove(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        """Serialize as JSON Patch does: a `remove` has no `value` member.

        Args:
            handler: Pydantic's own serializer for this model.

        Returns:
            The operation's members.

        Raises:
            TypeError: Pydantic handed back something other than the members of the model.
        """
        serialized_members: object = handler(self)
        if not isinstance(serialized_members, dict):
            raise TypeError("a patch operation serializes to an object")
        return {
            str(member_name): member_value
            for member_name, member_value in serialized_members.items()
            if not (self.op == "remove" and member_name == "value")
        }


def compute_patch(previous: JsonValue, current: JsonValue) -> list[PatchOperation]:
    """Return the operations that turn `previous` into `current`.

    Args:
        previous: The document as it was.
        current: The document as it is now.

    Returns:
        The operations, in the order they must be applied. Empty when the two are the same.
    """
    operations: list[PatchOperation] = []
    _collect_operations(previous, current, "", operations)
    return operations


def apply_patch(document: JsonValue, operations: Sequence[PatchOperation]) -> JsonValue:
    """Return a copy of `document` with the operations applied in order; the original is unchanged.

    Args:
        document: The document to start from.
        operations: The operations, as `compute_patch` returns them.

    Returns:
        The patched copy.

    Raises:
        ValueError: An operation names a path that does not exist, or one it cannot apply to.
    """
    # The root is held as the only item of a list, so that replacing it is the same as replacing any
    # other value: its path is the holder's first item.
    root_holder: list[JsonValue] = [copy.deepcopy(document)]
    for operation in operations:
        _apply_operation(root_holder, operation)
    return root_holder[0]


def _collect_operations(
    previous: JsonValue, current: JsonValue, path: str, operations: list[PatchOperation]
) -> None:
    """Append to `operations` what turns `previous` into `current`, both found at `path`.

    Args:
        previous: The old value at the path.
        current: The new value at the path.
        path: The JSON Pointer of both values.
        operations: The list the operations are appended to.
    """
    if isinstance(previous, dict) and isinstance(current, dict):
        for removed_key in [key for key in previous if key not in current]:
            operations.append(PatchOperation(op="remove", path=_child_path(path, removed_key)))
        for key, current_value in current.items():
            if key in previous:
                _collect_operations(
                    previous[key], current_value, _child_path(path, key), operations
                )
            else:
                operations.append(
                    PatchOperation(op="add", path=_child_path(path, key), value=current_value)
                )
        return
    if isinstance(previous, list) and isinstance(current, list):
        shared_length = min(len(previous), len(current))
        for index in range(shared_length):
            _collect_operations(
                previous[index], current[index], _child_path(path, str(index)), operations
            )
        for index in range(shared_length, len(current)):
            operations.append(
                PatchOperation(op="add", path=_child_path(path, str(index)), value=current[index])
            )
        # From the end, so that each index still names the item it was computed for.
        for index in range(len(previous) - 1, shared_length - 1, -1):
            operations.append(PatchOperation(op="remove", path=_child_path(path, str(index))))
        return
    if not _is_same_json(previous, current):
        operations.append(PatchOperation(op="replace", path=path, value=current))


def _is_same_json(first: JsonValue, second: JsonValue) -> bool:
    """Return whether two scalar or mixed values would be written as the same JSON.

    Python's `==` holds `True == 1` and `1 == 1.0`, which JSON writes differently, so the types are
    compared as well.

    Args:
        first: One value.
        second: The other.

    Returns:
        Whether they are the same JSON.
    """
    return type(first) is type(second) and first == second


def _child_path(path: str, key: str) -> str:
    """Return the JSON Pointer of `key` under `path`, escaping `~` and `/` as RFC 6901 says.

    Args:
        path: The parent's pointer.
        key: The child's key, or a list index written as text.

    Returns:
        The child's pointer.
    """
    escaped_key = key.replace("~", "~0").replace("/", "~1")
    return f"{path}/{escaped_key}"


def _pointer_tokens(path: str) -> list[str]:
    """Return the reference tokens of a JSON Pointer, unescaped.

    Args:
        path: The pointer: empty for the root, otherwise starting with `/`.

    Returns:
        The tokens, outermost first.

    Raises:
        ValueError: The pointer neither is empty nor starts with `/`.
    """
    if path == "":
        return []
    if not path.startswith("/"):
        raise ValueError(f"a JSON Pointer starts with '/': {path!r}")
    return [token.replace("~1", "/").replace("~0", "~") for token in path[1:].split("/")]


def _apply_operation(root_holder: list[JsonValue], operation: PatchOperation) -> None:
    """Apply one operation in place, below the list that holds the root.

    Args:
        root_holder: A one-item list whose item is the document.
        operation: The operation to apply.

    Raises:
        ValueError: The path does not exist, or the operation cannot apply to what is there.
    """
    tokens = [ROOT_HOLDER_INDEX, *_pointer_tokens(operation.path)]
    parent: JsonValue = root_holder
    for token in tokens[:-1]:
        parent = _child_value(parent, token, operation.path)
    last_token = tokens[-1]
    new_value = copy.deepcopy(operation.value)
    if isinstance(parent, dict):
        if operation.op != "add" and last_token not in parent:
            raise ValueError(f"no value at {operation.path!r} to {operation.op}")
        if operation.op == "remove":
            del parent[last_token]
        else:
            parent[last_token] = new_value
        return
    if isinstance(parent, list):
        index = _list_index(last_token, operation.path)
        upper_bound = len(parent) if operation.op == "add" else len(parent) - 1
        if index > upper_bound:
            raise ValueError(f"index out of range at {operation.path!r}")
        if operation.op == "add":
            parent.insert(index, new_value)
        elif operation.op == "remove":
            del parent[index]
        else:
            parent[index] = new_value
        return
    raise ValueError(f"no object or array to hold {operation.path!r}")


def _child_value(container: JsonValue, token: str, path: str) -> JsonValue:
    """Return the value under `token` in `container`, for walking a pointer down.

    Args:
        container: An object or an array.
        token: A key, or an index written as text.
        path: The whole pointer, for the error message.

    Returns:
        The value under the token.

    Raises:
        ValueError: The container has nothing under that token.
    """
    if isinstance(container, dict) and token in container:
        return container[token]
    if isinstance(container, list):
        index = _list_index(token, path)
        if index < len(container):
            return container[index]
    raise ValueError(f"no value at {token!r} on the way to {path!r}")


def _list_index(token: str, path: str) -> int:
    """Return a pointer token as an array index.

    Args:
        token: The token: digits with no leading zero.
        path: The whole pointer, for the error message.

    Returns:
        The index.

    Raises:
        ValueError: The token is not an index.
    """
    if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
        raise ValueError(f"{token!r} is not an array index in {path!r}")
    return int(token)
