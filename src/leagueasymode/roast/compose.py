"""Fill the templates for one case: pick each template's subjects, then write its parts.

A subject is chosen from the case's target among the players who meet the template's conditions,
the highest `rank_by` value first. Every slot becomes a part holding its exhibit's display text and
key, so a line can only state what an exhibit holds. The slots:

    {champion}              the subject's champion
    {opponent_champion}     the subject's lane opponent's champion
    {defendant_champion}    the defendant's champion
    {name}                  the subject's exhibit "name/p<id>"
    {opponent.name}         the lane opponent's exhibit "name/p<id>"
    {team.name}             the subject's team's exhibit "name/t<team id>"
    {enemy_team.name}       the other team's exhibit "name/t<team id>"
    {game.name}             the match's exhibit "name"

A template's conditions name slots the same way.
"""

from dataclasses import dataclass
from typing import Final

from leagueasymode.roast.exhibits import ExhibitLedger
from leagueasymode.roast.lines import CitedLine, LinePart
from leagueasymode.roast.players import RoastPlayer
from leagueasymode.roast.templates import RoastTemplate, TemplateCondition, split_template_text

# The families "Prove it" keeps: lines that set a player against their lane opponent, and the kills
# that make an opponent a smurf.
HEAD_TO_HEAD_FAMILIES: Final = frozenset({"lanes", "kills"})
# When a case roasts a whole team, no teammate or opponent is the subject of more lines than this,
# so the case spreads its blame. The defendant's own lines are their excuses, and are not capped;
# nor is a single lane or player the reader chose, who gets every receipt there is.
MAXIMUM_LINES_PER_SUBJECT: Final = 3
# Lines about a teammate that clear them rather than flame them: the defendant meeting their
# conditions too is no fault.
NOT_FLAMES: Final = frozenset({"carry-receipt-ally", "lane-held-ahead", "lane-held-behind"})


@dataclass(frozen=True)
class CaseContext:
    """What a template needs to know about the case besides its subject."""

    ledger: ExhibitLedger
    players_by_id: dict[int, RoastPlayer]
    opponent_by_id: dict[int, int]
    defendant: RoastPlayer
    verdict_code: str


def exhibit_number(ledger: ExhibitLedger, exhibit_key: str) -> float | None:
    """Return an exhibit's value as a number, or None when there is none or it is not a number.

    Args:
        ledger: The match's exhibits.
        exhibit_key: The exhibit's key.

    Returns:
        The value, or None.
    """
    exhibit = ledger.exhibits.get(exhibit_key)
    if exhibit is None or isinstance(exhibit.value, (bool, str)):
        return None
    return float(exhibit.value)


def exhibit_key_for(slot_name: str, subject: RoastPlayer, context: CaseContext) -> str | None:
    """Return the key of the exhibit a slot names, for one subject.

    Args:
        slot_name: The slot, such as "deaths", "opponent.vision_score" or "enemy_team.dragons".
        subject: The player the line is about.
        context: The case.

    Returns:
        The exhibit key, or None when the slot names nobody (no lane opponent, an unknown scope).
    """
    scope, _, exhibit_name = slot_name.rpartition(".")
    opponent_id = context.opponent_by_id.get(subject.participant_id)
    other_team_ids = [
        participant.team_id
        for participant in context.players_by_id.values()
        if participant.team_id != subject.team_id
    ]
    keys_by_scope = {
        "": f"{exhibit_name}/p{subject.participant_id}",
        "opponent": f"{exhibit_name}/p{opponent_id}" if opponent_id is not None else None,
        "team": f"{exhibit_name}/t{subject.team_id}",
        "enemy_team": f"{exhibit_name}/t{other_team_ids[0]}" if other_team_ids else None,
        "game": exhibit_name,
    }
    return keys_by_scope.get(scope)


def meets_condition(
    context: CaseContext, subject: RoastPlayer, condition: TemplateCondition
) -> bool:
    """Say whether a subject meets one of a template's conditions.

    Args:
        context: The case.
        subject: The player the line would be about.
        condition: The condition, whose slot is named as in a template's text.

    Returns:
        True when the exhibit exists and is within the bounds.
    """
    exhibit_key = exhibit_key_for(condition.slot, subject, context)
    value = exhibit_number(context.ledger, exhibit_key) if exhibit_key is not None else None
    if value is None:
        return False
    above_floor = condition.at_least is None or value >= condition.at_least
    below_ceiling = condition.at_most is None or value <= condition.at_most
    return above_floor and below_ceiling


def resolve_slot(
    slot_name: str, subject: RoastPlayer, context: CaseContext
) -> tuple[LinePart, int | None] | None:
    """Turn one slot into a part, and say which player it names.

    Args:
        slot_name: The slot, such as "champion", "gold_behind_14" or "game.clock_14".
        subject: The player the line is about.
        context: The case.

    Returns:
        The part and the participant id it names (or None), or None when the slot has no value.
    """
    opponent_id = context.opponent_by_id.get(subject.participant_id)
    if slot_name == "champion":
        name_part = LinePart(text=subject.champion)
        return name_part, subject.participant_id
    if slot_name == "defendant_champion":
        defendant_part = LinePart(text=context.defendant.champion)
        return defendant_part, context.defendant.participant_id
    if slot_name == "opponent_champion":
        if opponent_id is None:
            return None
        opponent = context.players_by_id[opponent_id]
        return LinePart(text=opponent.champion), opponent_id
    exhibit_key = exhibit_key_for(slot_name, subject, context)
    exhibit = context.ledger.exhibits.get(exhibit_key) if exhibit_key is not None else None
    if exhibit is None:
        return None
    return LinePart(text=exhibit.display, exhibit_key=exhibit.key), None


def fill_template(
    template: RoastTemplate, subject: RoastPlayer, context: CaseContext
) -> CitedLine | None:
    """Write one template about one player.

    Args:
        template: The template.
        subject: The player the line is about.
        context: The case.

    Returns:
        The line, or None when one of its slots has no value.
    """
    parts: list[LinePart] = []
    named_ids: list[int] = []
    for literal_text, slot_name in split_template_text(template.text):
        if slot_name is None:
            parts.append(LinePart(text=literal_text))
            continue
        resolved = resolve_slot(slot_name, subject, context)
        if resolved is None:
            return None
        part, named_id = resolved
        parts.append(part)
        if named_id is not None:
            named_ids.append(named_id)
    return CitedLine(
        template_id=template.template_id,
        parts=tuple(parts),
        champion_participant_ids=tuple(dict.fromkeys(named_ids)),
        subject_participant_id=subject.participant_id,
    )


def _is_a_glass_house(template: RoastTemplate, context: CaseContext) -> bool:
    """Return whether a line would flame a teammate for what the defendant did too.

    The owner, 2026-10-29: "you need to make roasts self aware ... cant do a roast if i am also
    bad". A line about a teammate is not offered when the defendant meets its conditions as well:
    six deaths, a lane lost by 1,500 gold, a low kill participation. A line clearing a teammate
    is no flame, and stays.

    Args:
        template: The template.
        context: The case, with its defendant.

    Returns:
        True when the line is not to be offered.
    """
    return (
        template.subject == "ally"
        and template.template_id not in NOT_FLAMES
        and bool(template.when)
        and all(
            meets_condition(context, context.defendant, condition) for condition in template.when
        )
    )


def compose_lines(
    templates: tuple[RoastTemplate, ...],
    context: CaseContext,
    subjects_by_role: dict[str, list[RoastPlayer]],
    spice_level: int,
    *,
    target_is_narrow: bool = False,
    prove: bool = False,
) -> list[CitedLine]:
    """Write every template that applies, each about its best-qualified subjects.

    Args:
        templates: The templates, in the order they are tried.
        context: The case.
        subjects_by_role: The players each template subject may be: "ally", "enemy" and
            "defendant", already narrowed to the case's target.
        spice_level: The spice level, from 1 to 4.
        target_is_narrow: Whether the target is one lane or one player, which offers the
            templates marked `narrow_only`.
        prove: Whether to keep only head-to-head templates.

    Returns:
        The lines, in template order, with no subject in more than
        `MAXIMUM_LINES_PER_SUBJECT` of them.
    """
    lines: list[CitedLine] = []
    lines_per_subject: dict[int, int] = {}
    for template in templates:
        if not template.offered_at(spice_level):
            continue
        if template.verdicts and context.verdict_code not in template.verdicts:
            continue
        if template.narrow_only and not target_is_narrow:
            continue
        if prove and template.family not in HEAD_TO_HEAD_FAMILIES:
            continue
        if _is_a_glass_house(template, context):
            continue
        qualified_subjects = [
            subject
            for subject in subjects_by_role.get(template.subject, [])
            if all(meets_condition(context, subject, condition) for condition in template.when)
        ]
        ranked_subjects = sorted(
            qualified_subjects,
            key=lambda subject: (
                -(
                    exhibit_number(context.ledger, f"{template.rank_by}/p{subject.participant_id}")
                    or 0
                ),
                subject.participant_id,
            ),
        )
        open_subjects = [
            subject
            for subject in ranked_subjects
            if target_is_narrow
            or subject.participant_id == context.defendant.participant_id
            or lines_per_subject.get(subject.participant_id, 0) < MAXIMUM_LINES_PER_SUBJECT
        ]
        for subject in open_subjects[: template.max_subjects]:
            line = fill_template(template, subject, context)
            if line is not None:
                lines.append(line)
                lines_per_subject[subject.participant_id] = (
                    lines_per_subject.get(subject.participant_id, 0) + 1
                )
    return lines
