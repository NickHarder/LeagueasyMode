import hashlib
import json
import re
from typing import Final

import pytest

from leagueasymode.roast.safety import floor_problems
from leagueasymode.roast.templates import load_templates, split_template_text

NUMBER_WORDS: Final = re.compile(
    r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|twenty|thirty|forty|fifty|hundred|thousand|million|once|twice)\b",
    re.IGNORECASE,
)
# The lines the owner approved word for word: first on 2026-10-08 in nothingsmyfault, then the
# rewrite with more flair on 2026-10-29 ("approved"). A change to any line changes this; the new
# line goes to the owner before the fingerprint does.
APPROVED_LINES_SHA256: Final = "3e3bd1eb07dc301ab562cbd3df482523e5d219e16719991bc570acff7316392b"


def test_the_lines_are_the_ones_the_owner_approved() -> None:
    canonical = json.dumps(
        [
            template.model_dump(by_alias=True, mode="json")
            for template in load_templates().templates
        ],
        sort_keys=True,
        ensure_ascii=False,
    )
    assert hashlib.sha256(canonical.encode()).hexdigest() == APPROVED_LINES_SHA256


def test_every_template_has_its_own_id_and_a_spice_range_within_the_four_levels() -> None:
    templates = load_templates().templates
    assert len({template.template_id for template in templates}) == len(templates)
    for template in templates:
        lowest_level, highest_level = template.spice
        assert 1 <= lowest_level <= highest_level <= 4, template.template_id


def test_no_template_writes_a_number_of_its_own() -> None:
    for template in load_templates().templates:
        literal_text = "".join(
            text for text, slot in split_template_text(template.text) if slot is None
        )
        assert not re.search(r"\d", literal_text), template.template_id
        assert not NUMBER_WORDS.search(literal_text), template.template_id


def test_every_template_passes_the_floor() -> None:
    for template in load_templates().templates:
        assert floor_problems(template.text) == [], template.template_id


@pytest.mark.parametrize(
    "line",
    ["kys", "Just KYS already", "k y s", "go kill yourself", "your mom plays better", "UR M0M"],
)
def test_the_floor_refuses_attacks_on_who_a_person_is(line: str) -> None:
    assert floor_problems(line)


@pytest.mark.parametrize(
    "line",
    [
        "Our Lee Sin was 1,661 gold behind Vi at 14:00.",
        "That is not a lane, that is a hostage situation.",
        "Skyscraper of a gold lead.",
    ],
)
def test_the_floor_lets_gameplay_flame_through(line: str) -> None:
    assert floor_problems(line) == []
