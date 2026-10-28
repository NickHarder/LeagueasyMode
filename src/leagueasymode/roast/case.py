"""A case: the verdict, the lines that survive the validator, the closing line and the exhibits.

This is the whole roast for one player of one game, from the game's players and exhibits, which the
families build from the client's answers. It reads nothing itself.
"""

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from leagueasymode.roast.closing import ClosingLine, write_closing_line
from leagueasymode.roast.compose import CaseContext, compose_lines
from leagueasymode.roast.exhibits import Exhibit, ExhibitLedger
from leagueasymode.roast.lanes import lane_opponents
from leagueasymode.roast.lines import CitedLine
from leagueasymode.roast.players import RoastPlayer
from leagueasymode.roast.rules import RoastRules
from leagueasymode.roast.targets import parse_target, subjects_for_target
from leagueasymode.roast.templates import load_templates
from leagueasymode.roast.validate import line_problems
from leagueasymode.roast.verdict import Verdict, judge_case

FALLBACK_CLOSING_TEXT: Final = "gg. Nothing's my fault."
ALPHABET_SIZE: Final = 26


class CaseOptions(BaseModel):
    """What the owner chose: whom to roast, how hard, which take, and how the chat line reads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: str = "team"
    # Keep only head-to-head lines: each target against their lane opponent.
    prove: bool = False
    spice: int = Field(default=2, ge=1, le=4)
    take: int = Field(default=0, ge=0)
    # The Mutual Defense Pact: friends on the defendant's team left out of a team roast.
    spare_friends: bool = False
    cite_letters: bool = False
    signature: bool = False


class LetteredExhibit(BaseModel):
    """An exhibit with the letter the case cites it by."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    letter: str
    exhibit: Exhibit
    # True for an exhibit on file only because a cited computation was built from it.
    supporting: bool = False


class Case(BaseModel):
    """Everything the post-game window shows of a roast, and the line the shortcut copies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: int
    defendant: RoastPlayer
    verdict: Verdict
    lines: tuple[CitedLine, ...]
    closing_line: ClosingLine
    exhibits: tuple[LetteredExhibit, ...]


def build_case(
    players: list[RoastPlayer],
    ledger: ExhibitLedger,
    defendant_participant_id: int,
    *,
    remade: bool,
    options: CaseOptions,
    rules: RoastRules,
) -> Case:
    """Build the case for one player of one game.

    Args:
        players: The game's players.
        ledger: The game's exhibits.
        defendant_participant_id: The player whose case it is.
        remade: Whether the game ended in a remake.
        options: The owner's choices.
        rules: The hand-set thresholds.

    Returns:
        The case.

    Raises:
        LookupError: If the player is not in the game.
        ValueError: If the options name a target that is not one.
    """
    defendants = [player for player in players if player.participant_id == defendant_participant_id]
    if not defendants:
        message = f"participant {defendant_participant_id} is not in game {ledger.game_id}"
        raise LookupError(message)
    defendant = defendants[0]
    target = parse_target(options.target)
    verdict = judge_case(players, ledger, defendant, remade=remade, rules=rules.verdict)
    context = CaseContext(
        ledger=ledger,
        players_by_id={player.participant_id: player for player in players},
        opponent_by_id=lane_opponents(players),
        defendant=defendant,
        verdict_code=verdict.code,
    )
    composed_lines = (
        []
        if verdict.code == "remake"
        else compose_lines(
            load_templates().templates,
            context,
            subjects_for_target(players, defendant, target, spare_friends=options.spare_friends),
            options.spice,
            target_is_narrow=target.is_narrow,
            prove=options.prove,
        )
    )
    checked_lines = [line for line in composed_lines if not line_problems(line, ledger, players)]
    lettered_exhibits = letter_exhibits(verdict, checked_lines, ledger.exhibits)
    letter_by_key = {lettered.exhibit.key: lettered.letter for lettered in lettered_exhibits}
    closing_line = write_closing_line(
        checked_lines,
        letter_by_key,
        limit_characters=rules.chat_line_max_characters,
        take=options.take,
        verdict_title=verdict.title,
        cite_letters=options.cite_letters,
        signature=options.signature,
    ) or fallback_closing_line(verdict, rules.chat_line_max_characters)
    return Case(
        game_id=ledger.game_id,
        defendant=defendant,
        verdict=verdict,
        lines=tuple(checked_lines),
        closing_line=closing_line,
        exhibits=lettered_exhibits,
    )


def letter_exhibits(
    verdict: Verdict, lines: list[CitedLine], exhibits: dict[str, Exhibit]
) -> tuple[LetteredExhibit, ...]:
    """Letter every cited exhibit, A first: the verdict's, then the board's, then the lines'.

    Every input of a cited computation is lettered too, so the chain from a claim down to what the
    client sent is on file.

    Args:
        verdict: The verdict, whose board and reasons are cited first.
        lines: The case's lines.
        exhibits: The ledger's exhibits, by key.

    Returns:
        The lettered exhibits.
    """
    line_keys = [key for line in lines for key in line.exhibit_keys]
    directly_cited = [
        key
        for key in dict.fromkeys([*verdict.exhibit_keys, *verdict.board_exhibit_keys(), *line_keys])
        if key in exhibits
    ]
    cited_keys = with_inputs(directly_cited, exhibits)
    directly_cited_keys = set(directly_cited)
    return tuple(
        LetteredExhibit(
            letter=exhibit_letter(index),
            exhibit=exhibits[key],
            supporting=key not in directly_cited_keys,
        )
        for index, key in enumerate(cited_keys)
    )


def with_inputs(cited_keys: list[str], exhibits: dict[str, Exhibit]) -> list[str]:
    """Return the cited keys followed by every input they were computed from, each once.

    Args:
        cited_keys: The exhibits cited directly, in order.
        exhibits: The ledger's exhibits, by key.

    Returns:
        The keys, the cited ones first, then the inputs in the order they are reached.
    """
    ordered_keys = dict.fromkeys(cited_keys)
    pending_keys = list(cited_keys)
    while pending_keys:
        exhibit = exhibits[pending_keys.pop(0)]
        new_inputs = [
            key for key in exhibit.source.input_keys if key in exhibits and key not in ordered_keys
        ]
        ordered_keys.update(dict.fromkeys(new_inputs))
        pending_keys.extend(new_inputs)
    return list(ordered_keys)


def exhibit_letter(index: int) -> str:
    """Return the letter for the n-th exhibit: A to Z, then AA, AB and so on.

    Args:
        index: The exhibit's position, from 0.

    Returns:
        Its letter.
    """
    if index < ALPHABET_SIZE:
        return chr(ord("A") + index)
    return exhibit_letter(index // ALPHABET_SIZE - 1) + exhibit_letter(index % ALPHABET_SIZE)


def fallback_closing_line(verdict: Verdict, limit_characters: int) -> ClosingLine:
    """Return the closing line for a case with no line that fits: the verdict, if it fits.

    Args:
        verdict: The verdict.
        limit_characters: The longest line chat takes.

    Returns:
        "gg." with the verdict's stamp and summary, which state no number, or a shorter line.
    """
    verdict_text = f"gg. {verdict.title}. {verdict.summary}"
    fitting_text = verdict_text if len(verdict_text) <= limit_characters else FALLBACK_CLOSING_TEXT
    return ClosingLine(text=fitting_text, exhibit_keys=())
