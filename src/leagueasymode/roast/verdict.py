"""The verdict: whose fault the game was, judged lane by lane from the defendant's side.

Each lane is judged on the gold difference at minute 14 against its opponent, by our thresholds
(roast/lanes.py, and `tuning.json`). The rules run in order; the first that fits decides:

1. A remake has no case to answer.
2. A win gets a carry receipt.
3. Without a full board (no timeline, a game shorter than 14 minutes, or a lane the game did not
   pair) there is no lane verdict: a verdict on four lanes would guess at the fifth.
4. Every lane lost, the defendant's included: mutual assured destruction.
5. The defendant's lane lost to an opponent who killed enough different players, with enough
   kills: enemy smurf.
6. The defendant's lane lost while enough other lanes held: guilty.
7. The defendant's lane held, one other lane was a gap and the rest held: that lane's diff.
8. The defendant's lane held and enough other lanes were lost: team diff.

"Enough" is each count of `VerdictRules` (roast/rules.py).
9. Anything else: a hung jury.

The verdict cites the exhibits it rests on, and its summary states no number of its own.
"""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from leagueasymode.roast.exhibits import ExhibitLedger
from leagueasymode.roast.lanes import lane_opponents
from leagueasymode.roast.players import RoastPlayer
from leagueasymode.roast.rules import VerdictRules

LaneOutcome = Literal["won", "even", "lost", "gap"]
VerdictCode = Literal[
    "remake",
    "carry_receipt",
    "no_lane_verdict",
    "mutual_destruction",
    "enemy_smurf",
    "guilty",
    "lane_diff",
    "team_diff",
    "hung_jury",
]
POSITION_ORDER: Final = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
ROLE_NAME_BY_POSITION: Final = {
    "TOP": "TOP",
    "JUNGLE": "JUNGLE",
    "MIDDLE": "MID",
    "BOTTOM": "BOT",
    "UTILITY": "SUPPORT",
}
# How each verdict reads in chat, as a player would type it (the owner, 2026-10-29: "what a league
# player might actually type not nerd stuff"); none for a verdict that is no ruling.
CHAT_WORDS_BY_CODE: Final[dict[str, str]] = {
    "carry_receipt": "wp",
    "mutual_destruction": "every lane lost",
    "enemy_smurf": "smurf diff",
    "guilty": "my bad",
    "team_diff": "team diff",
}
CHAT_ROLE_BY_ROLE_NAME: Final = {
    "TOP": "top",
    "JUNGLE": "jg",
    "MID": "mid",
    "BOT": "bot",
    "SUPPORT": "sup",
}
HELD_OUTCOMES: Final = frozenset({"won", "even"})
LOST_OUTCOMES: Final = frozenset({"lost", "gap"})


class LaneJudgement(BaseModel):
    """One lane of the board: the defendant's teammate, their opponent, and how it went."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position: str
    ally_participant_id: int
    enemy_participant_id: int
    outcome: LaneOutcome
    gold_difference_key: str
    outcome_key: str
    # The creep score difference the board shows beside the gold; not part of the ruling.
    cs_difference_key: str | None = None


class Verdict(BaseModel):
    """The ruling on a case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: VerdictCode
    title: str
    summary: str
    acquitted: bool | None
    exhibit_keys: tuple[str, ...]
    lanes: tuple[LaneJudgement, ...]

    def board_exhibit_keys(self) -> tuple[str, ...]:
        """Return the exhibits the board shows that the ruling does not rest on.

        Returns:
            Each lane's creep score difference, top to support, where there is one.
        """
        return tuple(lane.cs_difference_key for lane in self.lanes if lane.cs_difference_key)


def judge_lanes(
    players: list[RoastPlayer], ledger: ExhibitLedger, defendant: RoastPlayer
) -> tuple[LaneJudgement, ...]:
    """Judge each lane from the defendant's team's side, top to support.

    Args:
        players: The game's players.
        ledger: Its exhibits.
        defendant: The player whose case it is.

    Returns:
        One judgement per lane with an outcome exhibit; none without lane data.
    """
    opponents = lane_opponents(players)
    allies = sorted(
        (player for player in players if player.team_id == defendant.team_id),
        key=lambda player: (
            POSITION_ORDER.index(player.position)
            if player.position in POSITION_ORDER
            else len(POSITION_ORDER)
        ),
    )
    judgements: list[LaneJudgement] = []
    for ally in allies:
        outcome_exhibit = ledger.exhibits.get(f"lane_outcome_14/p{ally.participant_id}")
        if outcome_exhibit is None or ally.participant_id not in opponents:
            continue
        cs_difference_key = f"cs_diff_14/p{ally.participant_id}"
        judgements.append(
            LaneJudgement(
                position=ally.position,
                ally_participant_id=ally.participant_id,
                enemy_participant_id=opponents[ally.participant_id],
                outcome=_as_outcome(str(outcome_exhibit.value)),
                gold_difference_key=f"gold_diff_14/p{ally.participant_id}",
                outcome_key=outcome_exhibit.key,
                cs_difference_key=cs_difference_key
                if cs_difference_key in ledger.exhibits
                else None,
            )
        )
    return tuple(judgements)


def _as_outcome(outcome_text: str) -> LaneOutcome:
    """Narrow an outcome exhibit's text to a lane outcome.

    Args:
        outcome_text: "won", "even", "lost" or "gap".

    Returns:
        The same text, typed.

    Raises:
        ValueError: If it is none of the four.
    """
    if outcome_text == "won":
        return "won"
    if outcome_text == "even":
        return "even"
    if outcome_text == "lost":
        return "lost"
    if outcome_text == "gap":
        return "gap"
    message = f"{outcome_text!r} is not a lane outcome"
    raise ValueError(message)


def judge_case(
    players: list[RoastPlayer],
    ledger: ExhibitLedger,
    defendant: RoastPlayer,
    *,
    remade: bool,
    rules: VerdictRules,
) -> Verdict:
    """Rule on a case.

    Args:
        players: The game's players.
        ledger: Its exhibits.
        defendant: The player whose case it is.
        remade: Whether the game ended in a remake.
        rules: The counts the rules turn on.

    Returns:
        The verdict.
    """
    if remade:
        return _verdict(
            "remake",
            title="REMAKE",
            summary="A remake. There is no case to answer.",
            acquitted=None,
            exhibit_keys=(),
            lanes=(),
        )
    lanes = judge_lanes(players, ledger, defendant)
    lane_keys = tuple(key for lane in lanes for key in (lane.gold_difference_key, lane.outcome_key))
    if defendant.won:
        return _verdict(
            "carry_receipt",
            title="CARRY RECEIPT",
            summary="A win. Nothing to defend; the receipt shows who carried.",
            acquitted=None,
            exhibit_keys=lane_keys,
            lanes=lanes,
        )
    if len(lanes) < len(POSITION_ORDER):
        return _verdict(
            "no_lane_verdict",
            title="NO LANE VERDICT",
            summary=(
                "Riot's data gives no full lane board for this game, so the court rules on the "
                "scoreboard alone."
            ),
            acquitted=None,
            exhibit_keys=(),
            lanes=(),
        )
    return _judge_loss(ledger, defendant, lanes, lane_keys, rules)


def _judge_loss(
    ledger: ExhibitLedger,
    defendant: RoastPlayer,
    lanes: tuple[LaneJudgement, ...],
    lane_keys: tuple[str, ...],
    rules: VerdictRules,
) -> Verdict:
    """Rule on a lost game with a full board, by rules 4 to 9 of the module's docstring.

    Args:
        ledger: The match's exhibits.
        defendant: The player whose case it is.
        lanes: The board.
        lane_keys: The exhibits the board rests on.
        rules: The counts the rules turn on.

    Returns:
        The verdict.
    """
    own_lanes = [lane for lane in lanes if lane.ally_participant_id == defendant.participant_id]
    other_lanes = [lane for lane in lanes if lane.ally_participant_id != defendant.participant_id]
    own_lost = bool(own_lanes) and own_lanes[0].outcome in LOST_OUTCOMES
    held_others = [lane for lane in other_lanes if lane.outcome in HELD_OUTCOMES]
    lost_others = [lane for lane in other_lanes if lane.outcome in LOST_OUTCOMES]
    gapped_others = [lane for lane in other_lanes if lane.outcome == "gap"]
    if own_lost and not held_others:
        return _verdict(
            "mutual_destruction",
            title="MUTUAL ASSURED DESTRUCTION",
            summary=(
                "Every lane was lost, the defendant's included. "
                "Nobody leaves this courtroom innocent."
            ),
            acquitted=False,
            exhibit_keys=lane_keys,
            lanes=lanes,
        )
    if own_lost and _opponent_is_a_smurf(ledger, own_lanes[0].enemy_participant_id, rules):
        smurf_keys = (
            f"kills/p{own_lanes[0].enemy_participant_id}",
            f"distinct_victims/p{own_lanes[0].enemy_participant_id}",
        )
        return _verdict(
            "enemy_smurf",
            title="ENEMY SMURF",
            summary="The defendant's lane was lost to an opponent who killed nearly everyone. "
            "Opponent diff, not position diff.",
            acquitted=True,
            exhibit_keys=(*lane_keys, *smurf_keys),
            lanes=lanes,
        )
    if own_lost and len(held_others) >= rules.guilty_held_lanes:
        return _verdict(
            "guilty",
            title="GUILTY",
            summary=(
                "The other lanes held and the defendant's lane did not. The defense rests, poorly."
            ),
            acquitted=False,
            exhibit_keys=lane_keys,
            lanes=lanes,
        )
    if not own_lost and len(gapped_others) == 1 and len(lost_others) == 1:
        role = ROLE_NAME_BY_POSITION.get(gapped_others[0].position, gapped_others[0].position)
        return _verdict(
            "lane_diff",
            title=f"{role} DIFF",
            summary=f"Every lane held except the {role.lower()}, which was a gap. Acquitted.",
            acquitted=True,
            exhibit_keys=lane_keys,
            lanes=lanes,
        )
    if not own_lost and len(lost_others) >= rules.team_diff_lost_lanes:
        return _verdict(
            "team_diff",
            title="TEAM DIFF",
            summary="The defendant's lane held while the team lost theirs. Acquitted: team diff.",
            acquitted=True,
            exhibit_keys=lane_keys,
            lanes=lanes,
        )
    return _verdict(
        "hung_jury",
        title="HUNG JURY",
        summary="The lanes do not settle it either way.",
        acquitted=None,
        exhibit_keys=lane_keys,
        lanes=lanes,
    )


def _opponent_is_a_smurf(
    ledger: ExhibitLedger, opponent_participant_id: int, rules: VerdictRules
) -> bool:
    """Say whether a lane opponent killed most of the team, by kills and different victims.

    Args:
        ledger: The match's exhibits.
        opponent_participant_id: The defendant's lane opponent.
        rules: The counts the rules turn on.

    Returns:
        True when both counts reach the rules' thresholds.
    """
    kills = ledger.exhibits.get(f"kills/p{opponent_participant_id}")
    victims = ledger.exhibits.get(f"distinct_victims/p{opponent_participant_id}")
    if kills is None or victims is None:
        return False
    return (
        isinstance(kills.value, int)
        and isinstance(victims.value, int)
        and kills.value >= rules.smurf_kills
        and victims.value >= rules.smurf_distinct_victims
    )


def _verdict(
    code: VerdictCode,
    *,
    title: str,
    summary: str,
    acquitted: bool | None,
    exhibit_keys: tuple[str, ...],
    lanes: tuple[LaneJudgement, ...],
) -> Verdict:
    """Build a verdict.

    Args:
        code: The verdict's code.
        title: The stamp.
        summary: The ruling in a sentence, with no number of its own.
        acquitted: True, False, or None when there is nothing to acquit or convict.
        exhibit_keys: The exhibits it rests on.
        lanes: The board.

    Returns:
        The verdict.
    """
    return Verdict(
        code=code,
        title=title,
        summary=summary,
        acquitted=acquitted,
        exhibit_keys=exhibit_keys,
        lanes=lanes,
    )


def chat_words_of(verdict: Verdict) -> str:
    """Return how a verdict reads in chat, such as "jg diff"; empty for one that is no ruling.

    Args:
        verdict: The verdict.

    Returns:
        The words, in lower case.
    """
    if verdict.code == "lane_diff":
        role_name = verdict.title.split()[0]
        return f"{CHAT_ROLE_BY_ROLE_NAME.get(role_name, role_name.lower())} diff"
    return CHAT_WORDS_BY_CODE.get(verdict.code, "")
