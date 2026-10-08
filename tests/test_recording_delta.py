import copy
import json
import random

import pytest
from pydantic import JsonValue

from leagueasymode.recording.delta import PatchOperation, apply_patch, compute_patch


def canonical(value: JsonValue) -> str:
    # json.dumps tells true from 1 and 1.0 from 1, which == does not.
    return json.dumps(value, sort_keys=True)


def random_json(generator: random.Random, depth: int) -> JsonValue:
    kind = generator.choice(
        ["dict", "list", "str", "int", "float", "bool", "null"]
        if depth
        else ["str", "int", "float", "bool", "null"]
    )
    if kind == "dict":
        keys = [
            generator.choice(["a", "b", "c/d", "e~f", "gameTime", "", "0"])
            for _ in range(generator.randint(0, 4))
        ]
        return {key: random_json(generator, depth - 1) for key in keys}
    if kind == "list":
        return [random_json(generator, depth - 1) for _ in range(generator.randint(0, 4))]
    if kind == "str":
        return generator.choice(["Ahri", "Turret_T1_L_03_A", "", "#", "~1"])
    if kind == "int":
        return generator.choice([0, 1, 2, 300])
    if kind == "float":
        return generator.choice([0.0, 1.0, 12.5, 300.25])
    if kind == "bool":
        return generator.choice([True, False])
    return None


def mutate(generator: random.Random, value: JsonValue, depth: int) -> JsonValue:
    if generator.random() < 0.2:
        return random_json(generator, depth)
    if isinstance(value, dict):
        mutated = {key: mutate(generator, item, depth - 1) for key, item in value.items()}
        if generator.random() < 0.3 and mutated:
            mutated.pop(generator.choice(list(mutated)))
        if generator.random() < 0.3:
            mutated[generator.choice(["new", "a", "x/y"])] = random_json(generator, depth - 1)
        return mutated
    if isinstance(value, list):
        mutated_list = [mutate(generator, item, depth - 1) for item in value]
        if generator.random() < 0.3:
            mutated_list.append(random_json(generator, depth - 1))
        if generator.random() < 0.3 and mutated_list:
            mutated_list.pop()
        return mutated_list
    return value


def test_identical_documents_need_no_operations() -> None:
    document: JsonValue = {"gameData": {"gameTime": 12.5}, "allPlayers": [{"level": 3}]}
    assert compute_patch(document, copy.deepcopy(document)) == []


def test_a_changed_number_is_one_replace_at_its_path() -> None:
    previous: JsonValue = {"gameData": {"gameTime": 12.5}}
    current: JsonValue = {"gameData": {"gameTime": 13.0}}
    assert compute_patch(previous, current) == [
        PatchOperation(op="replace", path="/gameData/gameTime", value=13.0)
    ]


def test_an_appended_event_is_one_add_at_the_end_of_the_list() -> None:
    previous: JsonValue = {"Events": [{"EventID": 0}]}
    current: JsonValue = {"Events": [{"EventID": 0}, {"EventID": 1}]}
    assert compute_patch(previous, current) == [
        PatchOperation(op="add", path="/Events/1", value={"EventID": 1})
    ]


def test_a_shorter_list_removes_from_the_end() -> None:
    previous: JsonValue = {"items": [1, 2, 3]}
    current: JsonValue = {"items": [1]}
    operations = compute_patch(previous, current)
    assert operations == [
        PatchOperation(op="remove", path="/items/2"),
        PatchOperation(op="remove", path="/items/1"),
    ]
    assert apply_patch(previous, operations) == current


def test_keys_with_a_slash_or_a_tilde_are_escaped() -> None:
    previous: JsonValue = {"a/b": 1, "m~n": 2}
    current: JsonValue = {"a/b": 3, "m~n": 4}
    operations = compute_patch(previous, current)
    assert [operation.path for operation in operations] == ["/a~1b", "/m~0n"]
    assert apply_patch(previous, operations) == current


def test_a_number_turning_into_a_boolean_is_a_change() -> None:
    previous: JsonValue = {"isDead": 1}
    current: JsonValue = {"isDead": True}
    patched = apply_patch(previous, compute_patch(previous, current))
    assert canonical(patched) == canonical(current)


def test_the_root_can_be_replaced() -> None:
    assert apply_patch([1, 2], compute_patch([1, 2], {"a": 1})) == {"a": 1}


def test_applying_a_patch_leaves_the_original_alone() -> None:
    previous: JsonValue = {"scores": {"kills": 1}}
    snapshot = copy.deepcopy(previous)
    apply_patch(previous, [PatchOperation(op="replace", path="/scores/kills", value=2)])
    assert previous == snapshot


def test_a_path_that_does_not_exist_is_an_error() -> None:
    with pytest.raises(ValueError, match="/missing"):
        apply_patch({"a": 1}, [PatchOperation(op="replace", path="/missing/b", value=2)])


@pytest.mark.parametrize("seed", range(300))
def test_any_change_round_trips(seed: int) -> None:
    generator = random.Random(seed)  # noqa: S311  seeded, so that every case can be reproduced
    previous = random_json(generator, depth=4)
    current = mutate(generator, copy.deepcopy(previous), depth=4)
    patched = apply_patch(previous, compute_patch(previous, current))
    assert canonical(patched) == canonical(current)
