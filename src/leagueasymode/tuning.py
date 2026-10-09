"""The hand-set thresholds, in one file the owner edits: `tuning.json`.

Every threshold the overlay was given by hand, not by a game's rules or a fit, lives in a rules
model beside the code it tunes, its value the model's default: when a callout comes and what it
needs (`inference/callouts.py`), the suggestions' windows (`inference/suggestions.py`), what makes
a main or a one-trick (`inference/intel.py`), whom the lookups read timelines for
(`player_intel.py`), the jungle path's camp timings and weights (`inference/jungle_path.py`), the
positions' (`inference/positions.py`), and the estimators' priors and the season's numbers that
recordings will correct: experience rates, dragon timings, trips to base, gold, the monsters'
health and Smite's damage, the build path's weights, and the You panel's thresholds. This module
gathers them under one name each.

`tuning.json` in the application's directory (`LEAGUEASYMODE_TUNING` moves it) names only what it
changes; anything it leaves out keeps its default. `leagueasymode tuning` prints every value the
engine would use, and `leagueasymode tuning --write` writes them all to the file, to edit, when
there is no file yet. The engine reads the file when it starts, so an edit takes effect the next
time the app opens. A file that cannot be read (a misspelled name, a value of the wrong kind, not
JSON at all) changes nothing, and the status page says where it went wrong.
"""

import os
import tempfile
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from leagueasymode.engine_status import StatusBoard
from leagueasymode.inference.backs import BackRules
from leagueasymode.inference.build_path import BuildRules
from leagueasymode.inference.callouts import CalloutRules
from leagueasymode.inference.contests import ContestRules
from leagueasymode.inference.experience import ExperienceRules
from leagueasymode.inference.gold import GoldRules
from leagueasymode.inference.intel import IntelRules
from leagueasymode.inference.jungle_path import CampRules
from leagueasymode.inference.objectives import DragonRules
from leagueasymode.inference.positions import PositionRules
from leagueasymode.inference.suggestions import SuggestionRules
from leagueasymode.inference.you import YouRules
from leagueasymode.player_intel import LookupRules


class Tuning(BaseModel):
    """Every hand-set threshold, by the part of the overlay it tunes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    callouts: CalloutRules = Field(default_factory=CalloutRules)
    suggestions: SuggestionRules = Field(default_factory=SuggestionRules)
    intel: IntelRules = Field(default_factory=IntelRules)
    lookups: LookupRules = Field(default_factory=LookupRules)
    jungle_path: CampRules = Field(default_factory=CampRules)
    positions: PositionRules = Field(default_factory=PositionRules)
    experience: ExperienceRules = Field(default_factory=ExperienceRules)
    dragon: DragonRules = Field(default_factory=DragonRules)
    backs: BackRules = Field(default_factory=BackRules)
    gold: GoldRules = Field(default_factory=GoldRules)
    contests: ContestRules = Field(default_factory=ContestRules)
    build_path: BuildRules = Field(default_factory=BuildRules)
    you: YouRules = Field(default_factory=YouRules)


DEFAULT_TUNING: Final = Tuning()


def load_tuning(tuning_path: Path) -> tuple[Tuning, str | None]:
    """Return the tuning a file sets, and what is wrong with the file if anything is.

    Args:
        tuning_path: The tuning file.

    Returns:
        The tuning, the defaults when there is no file or it cannot be read; and None, or each
        problem as `place.in.file: problem`, the places of the file where it went wrong.
    """
    try:
        file_text = tuning_path.read_text()
    except FileNotFoundError:
        return Tuning(), None
    except OSError as error:
        return Tuning(), f"the file: {type(error).__name__}"
    try:
        return Tuning.model_validate_json(file_text), None
    except ValidationError as error:
        problems = [
            f"{'.'.join(str(place) for place in problem['loc']) or 'the file'}: {problem['type']}"
            for problem in error.errors(
                include_url=False, include_input=False, include_context=False
            )
        ]
        return Tuning(), "; ".join(problems)


def changed_values(tuning: Tuning) -> list[str]:
    """Return each value a tuning changes from its default, as `part.name`.

    Args:
        tuning: The tuning.

    Returns:
        The values' names, in the order the parts and their values are written.
    """
    defaults = Tuning()
    return [
        f"{part_name}.{value_name}"
        for part_name in Tuning.model_fields
        for value_name in type(getattr(defaults, part_name)).model_fields
        if getattr(getattr(tuning, part_name), value_name)
        != getattr(getattr(defaults, part_name), value_name)
    ]


def write_tuning(tuning_path: Path, tuning: Tuning) -> None:
    """Write every value of a tuning to a file, whole or not at all.

    Args:
        tuning_path: The tuning file.
        tuning: The tuning.
    """
    tuning_path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=tuning_path.parent, prefix=".tuning-", suffix=".json"
    )
    with os.fdopen(file_descriptor, "w") as temporary_file:
        temporary_file.write(tuning.model_dump_json(indent=2) + "\n")
    Path(temporary_name).replace(tuning_path)


def note_tuning(
    status: StatusBoard, tuning_path: Path, tuning: Tuning, problem: str | None
) -> None:
    """Say on the status page what the tuning file changed, or why it could not be read.

    Args:
        status: The status page's board.
        tuning_path: The tuning file.
        tuning: The tuning in use.
        problem: What is wrong with the file; None when nothing is.
    """
    path_text = status.path_text(tuning_path)
    if problem is not None:
        status.set_part(
            "tuning",
            "problem",
            f"{path_text} could not be read ({problem}); the hand-set values stand",
        )
        return
    changed = changed_values(tuning)
    if not changed:
        status.set_part("tuning", "ok", f"Hand-set values; none changed in {path_text}")
        return
    value_word = "value" if len(changed) == 1 else "values"
    status.set_part(
        "tuning",
        "ok",
        f"{len(changed)} {value_word} changed in {path_text}: {', '.join(changed)}",
    )
