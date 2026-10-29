"""A few lines for chat after the game, for the overlay's roast card.

The owner, 2026-10-29: the post-game window's options were "overwhelming", so the overlay offers
three, each about a different target: the team, the lane lost by the most gold, and the enemy team.
No two come from the same template; when those would, or a quick case has no lanes, the team's
next lines fill in. When the defendant lost their own lane, the card leads with owning it; and no
line flames a teammate for what the defendant did too (`compose.py`).
"""

from typing import Final

from pydantic import BaseModel, ConfigDict

from leagueasymode.roast.case import Case, CaseOptions, build_case
from leagueasymode.roast.closing import ClosingLine
from leagueasymode.roast.last_game import LastGameRoast
from leagueasymode.roast.rules import RoastRules

SUGGESTION_COUNT: Final = 3
# The defendant's own lane lost: the card leads with owning it (the owner, 2026-10-29: "make
# roasts self aware").
OWNING_IT_TEMPLATE_ID: Final = "defendant-behind"
# The lines where the defendant owns what they did too, which the card leads with likewise.
SELF_AWARE_PREFIX: Final = "self-"
LOST_OUTCOMES: Final = ("lost", "gap")


class RoastSuggestions(BaseModel):
    """The lines the roast card offers, at one spice level."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spice: int
    is_quick: bool
    lines: tuple[str, ...]


def roast_suggestions(last_game: LastGameRoast, spice: int, rules: RoastRules) -> RoastSuggestions:
    """Return up to three lines for chat, each about a different target where it can.

    Args:
        last_game: The last game, as kept after it.
        spice: The spice level, 1 to 4.
        rules: Our thresholds for the verdict and the chat line's length.

    Returns:
        The lines, distinct, the team's closing line first.
    """
    team_case = _case_of(last_game, "team", spice, rules)
    worst_lane = _worst_lost_lane(team_case, last_game)
    cases = [
        team_case,
        *(
            _case_of(last_game, target, spice, rules)
            for target in ([f"lane:{worst_lane}"] if worst_lane else []) + ["enemy"]
        ),
    ]
    owning_it = [
        option
        for option in team_case.closing_options
        if option.template_id == OWNING_IT_TEMPLATE_ID
        or option.template_id.startswith(SELF_AWARE_PREFIX)
    ]
    chosen: list[ClosingLine] = owning_it[:1]
    # Each target's first line not like one chosen, then the team's others.
    for options in [case.closing_options for case in cases] + [team_case.closing_options] * 2:
        fresh = next((option for option in options if _is_new(option, chosen)), None)
        if fresh is not None and len(chosen) < SUGGESTION_COUNT:
            chosen.append(fresh)
    lines = [option.text for option in chosen] or [team_case.closing_line.text]
    return RoastSuggestions(spice=spice, is_quick=last_game.is_quick, lines=tuple(lines))


def _is_new(option: ClosingLine, chosen: list[ClosingLine]) -> bool:
    """Return whether a line is a roast that says something new.

    From a template, and not the same words or template as one chosen: the fallback line, the
    verdict alone, is offered only when there is no other.
    """
    return bool(option.template_id) and all(
        option.text != other.text and option.template_id != other.template_id for other in chosen
    )


def _case_of(last_game: LastGameRoast, target: str, spice: int, rules: RoastRules) -> Case:
    game = last_game.game
    return build_case(
        list(game.players),
        game.ledger,
        last_game.defendant_participant_id,
        remade=game.remade,
        options=CaseOptions(target=target, spice=spice),
        rules=rules,
    )


def _worst_lost_lane(team_case: Case, last_game: LastGameRoast) -> str | None:
    """Return the position of the lane our side lost by the most gold; None when none was lost."""
    exhibits = last_game.game.ledger.exhibits
    lost = [
        (exhibit.value, lane.position)
        for lane in team_case.verdict.lanes
        if lane.outcome in LOST_OUTCOMES
        and (exhibit := exhibits.get(lane.gold_difference_key)) is not None
    ]
    return min(lost)[1] if lost else None
