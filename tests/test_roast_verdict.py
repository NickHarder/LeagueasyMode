import pytest

from leagueasymode.roast.rules import VerdictRules
from leagueasymode.roast.verdict import Verdict, judge_case
from roast_support import DEFENDANT_ID, built_ledger, built_players


def verdict_of(
    gold_differences: tuple[int | None, ...],
    *,
    won: bool = False,
    remade: bool = False,
    rules: VerdictRules | None = None,
    distinct_victims: dict[int, int] | None = None,
    scores: tuple[tuple[int, int, int], ...] | None = None,
) -> Verdict:
    players = built_players(our_team_won=won)
    ledger = (
        built_ledger(gold_differences, distinct_victims=distinct_victims)
        if scores is None
        else built_ledger(gold_differences, scores, distinct_victims=distinct_victims)
    )
    defendant = next(player for player in players if player.participant_id == DEFENDANT_ID)
    return judge_case(players, ledger, defendant, remade=remade, rules=rules or VerdictRules())


@pytest.mark.parametrize(
    ("gold_differences", "title"),
    [
        ((-792, -1661, 1013, -810, -131), "TEAM DIFF"),
        ((200, -1700, 900, -300, 0), "JUNGLE DIFF"),
        ((100, 100, -900, 0, 300), "GUILTY"),
        ((-900, -900, -900, -900, -900), "MUTUAL ASSURED DESTRUCTION"),
        ((100, -100, 900, 0, -700), "HUNG JURY"),
        ((-792, None, 1013, -810, -131), "NO LANE VERDICT"),
    ],
)
def test_each_board_gets_its_verdict(gold_differences: tuple[int | None, ...], title: str) -> None:
    assert verdict_of(gold_differences).title == title


def test_a_win_is_a_carry_receipt_and_a_remake_no_case() -> None:
    assert verdict_of((0, 0, 900, 0, 0), won=True).title == "CARRY RECEIPT"
    assert verdict_of((0, 0, 900, 0, 0), remade=True).title == "REMAKE"


def test_a_lane_lost_to_an_opponent_who_killed_everyone_is_an_enemy_smurf() -> None:
    scores = tuple((12, 0, 0) if index == 7 else (1, 1, 1) for index in range(10))
    verdict = verdict_of((100, 100, -900, 0, 300), distinct_victims={8: 5}, scores=scores)
    assert verdict.title == "ENEMY SMURF"
    assert "kills/p8" in verdict.exhibit_keys


def test_the_counts_come_from_the_tuning() -> None:
    strict = VerdictRules(team_diff_lost_lanes=4)
    assert verdict_of((-792, -1661, 1013, -810, -131), rules=strict).title == "HUNG JURY"


def test_the_verdict_cites_the_board_it_rests_on() -> None:
    verdict = verdict_of((-792, -1661, 1013, -810, -131))
    assert "gold_diff_14/p2" in verdict.exhibit_keys
    assert [lane.position for lane in verdict.lanes] == [
        "TOP",
        "JUNGLE",
        "MIDDLE",
        "BOTTOM",
        "UTILITY",
    ]
