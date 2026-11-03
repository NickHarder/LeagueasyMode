"""Lines for chat after a game, for the overlay's roast card: a player each, the hardest hitting.

The owner, 2026-10-29: the post-game window's options were "overwhelming"; then "make it roast
different players. also make it the hardest hitting and only if its notable ... i want variety on
who i can pick". So the card offers up to three players, each with their lines hardest first: a
player's line is how far their numbers are past its template's thresholds (`compose._notability`),
and a player is offered only for a line that meets them. Copying a player's line brings up their
next one. When the defendant owns what they did too (`self-*`, `defendant-behind`), that comes
first; otherwise no line is about the defendant, and no line flames a teammate for what the
defendant did too (`compose.py`). Lines that clear a teammate are no roast, and are left out.
"""

from collections.abc import Iterable
from typing import Final

from pydantic import BaseModel, ConfigDict

from leagueasymode.roast.case import Case, CaseOptions, build_case
from leagueasymode.roast.closing import ClosingLine, closing_line_candidates
from leagueasymode.roast.compose import NOT_FLAMES
from leagueasymode.roast.last_game import LastGameRoast
from leagueasymode.roast.rules import RoastRules
from leagueasymode.roast.verdict import chat_words_of

SUGGESTION_COUNT: Final = 3
# The lines where the defendant owns what they did too, which the card leads with.
OWNING_IT_TEMPLATE_ID: Final = "defendant-behind"
SELF_AWARE_PREFIX: Final = "self-"
# Each player's lines offered in turn, hardest first.
LINES_PER_PLAYER: Final = 4


class RoastSuggestions(BaseModel):
    """The players the roast card offers, at one spice level, each with their lines."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    spice: int
    is_quick: bool
    # The first line of each player, as the card first shows them.
    lines: tuple[str, ...]
    # Each player's lines, hardest first; copying one brings up the next.
    groups: tuple[tuple[str, ...], ...]


def roast_suggestions(last_game: LastGameRoast, spice: int, rules: RoastRules) -> RoastSuggestions:
    """Return up to three players to roast, each with their lines, hardest first.

    Args:
        last_game: The last game, as kept after it.
        spice: The spice level, 1 to 4.
        rules: Our thresholds for the verdict and the chat line's length.

    Returns:
        The players' lines; the defendant's own line first when they own something.
    """
    defendant_id = last_game.defendant_participant_id
    by_player: dict[int, list[ClosingLine]] = {}
    # The team's case for the defendant's own lines; each other player's own case for theirs, since
    # a case about a team gives each line to its worst player only.
    targets = ["team"] + [
        f"player:{player.participant_id}"
        for player in last_game.game.players
        if player.participant_id != defendant_id
    ]
    for line in _chat_lines(
        (_case_of(last_game, target, spice, rules) for target in targets),
        rules.chat_line_max_characters,
    ):
        subject_id = line.subject_participant_id
        if subject_id is None or not _is_a_roast(line, defendant_id):
            continue
        same_player = by_player.setdefault(subject_id, [])
        if all(line.text != other.text for other in same_player):
            same_player.append(line)
    groups = sorted(
        (sorted(lines, key=lambda line: -line.notability) for lines in by_player.values()),
        key=lambda lines: (lines[0].subject_participant_id != defendant_id, -lines[0].notability),
    )[:SUGGESTION_COUNT]
    if not groups:
        closing = _case_of(last_game, "team", spice, rules).closing_line.text
        return RoastSuggestions(
            spice=spice, is_quick=last_game.is_quick, lines=(closing,), groups=((closing,),)
        )
    texts = tuple(
        tuple(line.text for line in lines[:LINES_PER_PLAYER]) for lines in _varied_leads(groups)
    )
    return RoastSuggestions(
        spice=spice,
        is_quick=last_game.is_quick,
        lines=tuple(lines[0] for lines in texts),
        groups=texts,
    )


def _varied_leads(groups: list[list[ClosingLine]]) -> list[list[ClosingLine]]:
    """Return the groups, each led by its hardest line whose template leads no group before it.

    So the card's first lines are different jokes, not one joke about three players.
    """
    leading_templates: set[str] = set()
    varied: list[list[ClosingLine]] = []
    for lines in groups:
        lead = next((line for line in lines if line.template_id not in leading_templates), lines[0])
        leading_templates.add(lead.template_id)
        varied.append([lead, *(line for line in lines if line is not lead)])
    return varied


def _is_a_roast(line: ClosingLine, defendant_id: int) -> bool:
    """Return whether a line belongs on the card.

    A line about the defendant only when they own something; never one clearing a teammate.
    """
    if line.template_id in NOT_FLAMES or not line.template_id:
        return False
    if line.subject_participant_id == defendant_id:
        return line.template_id == OWNING_IT_TEMPLATE_ID or line.template_id.startswith(
            SELF_AWARE_PREFIX
        )
    return True


def _chat_lines(cases: Iterable[Case], limit_characters: int) -> list[ClosingLine]:
    """Return every line of the cases written for chat, each that fits, in the cases' order."""
    return [
        candidate
        for case in cases
        for candidate in closing_line_candidates(
            list(case.lines),
            {},
            limit_characters=limit_characters,
            verdict_words=chat_words_of(case.verdict),
        )
    ]


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
