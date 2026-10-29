from leagueasymode.roast.lines import CitedLine, LinePart
from leagueasymode.roast.validate import line_problems
from roast_support import built_ledger, built_players


def make_line(*parts: LinePart, champion_ids: tuple[int, ...] = (2,)) -> CitedLine:
    return CitedLine(template_id="test", parts=parts, champion_participant_ids=champion_ids)


def test_a_line_whose_number_equals_its_exhibit_passes() -> None:
    line = make_line(
        LinePart(text="Our "),
        LinePart(text="Lee Sin"),
        LinePart(text=" died "),
        LinePart(text="9", exhibit_key="deaths/p2"),
        LinePart(text=" times."),
    )
    assert line_problems(line, built_ledger(), built_players()) == []


def test_a_number_that_no_cited_exhibit_holds_is_refused() -> None:
    line = make_line(
        LinePart(text="Our Lee Sin died "),
        LinePart(text="9", exhibit_key="deaths/p2"),
        LinePart(text=" times in 12 minutes."),
    )
    problems = line_problems(line, built_ledger(), built_players())
    assert any("12" in problem for problem in problems)


def test_a_line_with_no_citation_is_refused() -> None:
    line = make_line(LinePart(text="Our Lee Sin had a bad game."))
    assert line_problems(line, built_ledger(), built_players())


def test_a_citation_of_an_exhibit_that_does_not_exist_is_refused() -> None:
    line = make_line(LinePart(text="Lee Sin died "), LinePart(text="9", exhibit_key="deaths/p99"))
    assert line_problems(line, built_ledger(), built_players())


def test_a_slot_whose_text_differs_from_its_exhibit_is_refused() -> None:
    line = make_line(LinePart(text="Lee Sin died "), LinePart(text="10", exhibit_key="deaths/p2"))
    assert line_problems(line, built_ledger(), built_players())


def test_a_champion_who_is_not_in_the_game_is_refused() -> None:
    line = make_line(
        LinePart(text="Our champion died "),
        LinePart(text="9", exhibit_key="deaths/p2"),
        champion_ids=(11,),
    )
    assert line_problems(line, built_ledger(), built_players())


def test_a_champion_named_by_the_line_must_appear_in_its_text() -> None:
    line = make_line(LinePart(text="Somebody died "), LinePart(text="9", exhibit_key="deaths/p2"))
    assert line_problems(line, built_ledger(), built_players())
