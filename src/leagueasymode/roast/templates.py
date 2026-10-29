"""Load the roast's lines from templates.toml, and split their text into parts and slots."""

import re
import tomllib
from functools import cache
from importlib import resources
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

SLOT_PATTERN: Final = re.compile(r"\{(?P<slot>[a-z0-9_.]+)\}")


class TemplateCondition(BaseModel):
    """A bound a subject's exhibit must meet for the template to apply."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slot: str
    at_least: float | None = None
    at_most: float | None = None


class RoastTemplate(BaseModel):
    """One line the roast can say, with the slots it fills."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str = Field(alias="id")
    family: str
    subject: Literal["ally", "enemy", "defendant"]
    spice: tuple[int, int]
    rank_by: str
    when: tuple[TemplateCondition, ...] = ()
    # The verdicts the line is offered under; empty means any.
    verdicts: tuple[str, ...] = ()
    # How many qualifying subjects get the line, best first.
    max_subjects: int = 1
    # Offered only when the target is one lane or one player.
    narrow_only: bool = False
    text: str

    def offered_at(self, spice_level: int) -> bool:
        """Say whether the template is offered at a spice level.

        Args:
            spice_level: From 1 to 4.

        Returns:
            True when the level is within the template's range.
        """
        lowest_level, highest_level = self.spice
        return lowest_level <= spice_level <= highest_level

    def slots(self) -> list[str]:
        """Return the slots the text fills, in order.

        Returns:
            The slot names.
        """
        return [found.group("slot") for found in SLOT_PATTERN.finditer(self.text)]


class TemplateLibrary(BaseModel):
    """Every template, in the order they are tried."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    templates: tuple[RoastTemplate, ...]


@cache
def load_templates() -> TemplateLibrary:
    """Read templates.toml, once.

    Returns:
        The template library.
    """
    templates_text = resources.files(__package__).joinpath("templates.toml").read_text("utf-8")
    return TemplateLibrary.model_validate(tomllib.loads(templates_text))


def split_template_text(text: str) -> list[tuple[str, str | None]]:
    """Split a template's text into literal pieces and slot names.

    Args:
        text: The template's text.

    Returns:
        Pairs of (literal text, None) and ("", slot name), in order.
    """
    pieces: list[tuple[str, str | None]] = []
    position = 0
    for found in SLOT_PATTERN.finditer(text):
        if found.start() > position:
            pieces.append((text[position : found.start()], None))
        pieces.append(("", found.group("slot")))
        position = found.end()
    if position < len(text):
        pieces.append((text[position:], None))
    return pieces
