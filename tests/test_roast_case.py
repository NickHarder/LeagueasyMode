import re
from typing import Final

import pytest

from leagueasymode.roast.case import (
    CLOSING_OPTION_COUNT,
    Case,
    CaseOptions,
    build_case,
    exhibit_letter,
)
from leagueasymode.roast.rules import RoastRules
from leagueasymode.roast.safety import floor_problems
from leagueasymode.roast.targets import Target, parse_target
from roast_support import DEFENDANT_ID, built_ledger, built_players

# Written here rather than imported, so the check does not share the validator's mistakes.
NUMBER_IN_TEXT: Final = re.compile(r"[-+]?\d[\d,]*(?:[.:]\d+)?%?")


def case_of(
    options: CaseOptions | None = None,
    *,
    rules: RoastRules | None = None,
    friends: frozenset[int] = frozenset(),
    remade: bool = False,
) -> Case:
    return build_case(
        built_players(friends=friends),
        built_ledger(),
        DEFENDANT_ID,
        remade=remade,
        options=options or CaseOptions(),
        rules=rules or RoastRules(),
    )


def named_ids(case: Case) -> set[int]:
    return {
        participant_id for line in case.lines for participant_id in line.champion_participant_ids
    }


@pytest.mark.parametrize("spice_level", [1, 2, 3, 4])
def test_every_number_in_every_line_is_in_an_exhibit_the_line_cites(spice_level: int) -> None:
    case = case_of(CaseOptions(spice=spice_level))
    exhibits = {lettered.exhibit.key: lettered.exhibit for lettered in case.exhibits}
    assert case.lines
    for line in case.lines:
        cited_numbers = {
            number
            for key in line.exhibit_keys
            for number in NUMBER_IN_TEXT.findall(exhibits[key].display)
        }
        assert set(NUMBER_IN_TEXT.findall(line.text)) <= cited_numbers, line.text
        assert floor_problems(line.text) == [], line.text


def test_the_approved_lines_come_out_word_for_word() -> None:
    texts = [line.text for line in case_of(CaseOptions(spice=2)).lines]
    assert "Lee Sin 1,661 gold down at 14:00. Vi gap" in texts


def test_the_chat_line_states_its_numbers_without_letters_or_a_signature() -> None:
    closing = case_of().closing_line
    assert closing.text.startswith("gg team diff. ")
    assert "(A)" not in closing.text
    assert "nothingsmyfault.lol" not in closing.text
    assert len(closing.text) <= RoastRules().chat_line_max_characters


def test_the_letters_and_the_signature_can_be_asked_for() -> None:
    closing = case_of(CaseOptions(cite_letters=True, signature=True)).closing_line
    assert re.search(r"\([A-Z]+\)", closing.text)
    assert closing.text.endswith("nothingsmyfault.lol")


def test_another_take_gives_another_line_and_wraps() -> None:
    first = case_of(CaseOptions(take=0)).closing_line.text
    second = case_of(CaseOptions(take=1)).closing_line.text
    assert first != second
    assert case_of(CaseOptions(take=500)).closing_line.text


def test_the_window_offers_lines_to_pick_from_the_closing_line_first() -> None:
    # The owner, 2026-10-29: at the post-game screen, "a way to see roast options and pick".
    case = case_of(CaseOptions(take=0))
    texts = [option.text for option in case.closing_options]
    assert 1 < len(texts) <= CLOSING_OPTION_COUNT
    assert texts[0] == case.closing_line.text
    assert len(set(texts)) == len(texts)
    assert all(len(text) <= RoastRules().chat_line_max_characters for text in texts)
    # Another take starts the options at the next line.
    next_take = case_of(CaseOptions(take=1))
    assert next_take.closing_options[0].text == texts[1]


def test_the_chat_limit_comes_from_the_tuning() -> None:
    short = RoastRules(chat_line_max_characters=40)
    assert len(case_of(rules=short).closing_line.text) <= 40


def test_a_remake_has_no_lines() -> None:
    case = case_of(remade=True)
    assert case.verdict.title == "REMAKE"
    assert case.lines == ()


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("team", Target(kind="team")),
        ("enemy", Target(kind="enemy")),
        ("lane:JUNGLE", Target(kind="lane", position="JUNGLE")),
        ("player:7", Target(kind="player", participant_id=7)),
    ],
)
def test_a_target_is_read_from_its_text(typed: str, expected: Target) -> None:
    assert parse_target(typed) == expected


@pytest.mark.parametrize("typed", ["", "lane:MOON", "player:11", "player:x", "everyone"])
def test_a_target_that_is_not_one_is_refused(typed: str) -> None:
    with pytest.raises(ValueError, match="target"):
        parse_target(typed)


def test_any_of_the_ten_players_can_be_the_target() -> None:
    for participant_id in range(1, 11):
        case = case_of(CaseOptions(target=f"player:{participant_id}", spice=2))
        assert named_ids(case) <= {participant_id, (participant_id + 4) % 10 + 1}


def test_a_lane_target_names_only_that_lane() -> None:
    ids = named_ids(case_of(CaseOptions(target="lane:JUNGLE")))
    assert ids
    assert ids <= {2, 7}


def test_friends_are_roasted_unless_the_pact_spares_them() -> None:
    assert 2 in named_ids(case_of(friends=frozenset({2})))
    assert 2 not in named_ids(case_of(CaseOptions(spare_friends=True), friends=frozenset({2})))


def test_exhibits_are_lettered_in_order_from_the_verdict() -> None:
    case = case_of()
    assert [lettered.letter for lettered in case.exhibits] == [
        exhibit_letter(index) for index in range(len(case.exhibits))
    ]
    assert case.exhibits[0].exhibit.key == case.verdict.exhibit_keys[0]
    assert exhibit_letter(26) == "AA"
