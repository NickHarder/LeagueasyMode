"""The check every line passes before it is shown.

A line must cite at least one exhibit; each slot's text must be its exhibit's display; every
number in the line must be a number of an exhibit it cites; every champion it names must be in
the game and in the text; and it must pass the safety floor (roast/safety.py). A line that fails
is dropped, never shown.
"""

from leagueasymode.roast.exhibits import ExhibitLedger
from leagueasymode.roast.lines import CitedLine
from leagueasymode.roast.numbers import number_tokens
from leagueasymode.roast.players import RoastPlayer
from leagueasymode.roast.safety import floor_problems


def line_problems(line: CitedLine, ledger: ExhibitLedger, players: list[RoastPlayer]) -> list[str]:
    """Return every way a line breaks the rules; an empty list means it may be shown.

    Args:
        line: The line.
        ledger: The game's exhibits.
        players: The game's players.

    Returns:
        A description of each problem.
    """
    unknown_keys = [key for key in line.exhibit_keys if key not in ledger.exhibits]
    cited_exhibits = [ledger.exhibits[key] for key in line.exhibit_keys if key in ledger.exhibits]
    cited_numbers = {
        token for exhibit in cited_exhibits for token in number_tokens(exhibit.display)
    }
    slot_mismatches = [
        f"slot {part.text!r} is not exhibit {part.exhibit_key}'s value"
        for part in line.parts
        if part.exhibit_key in ledger.exhibits
        and part.text != ledger.exhibits[part.exhibit_key].display
    ]
    uncited_numbers = [
        f"the number {token} is in no exhibit the line cites"
        for token in number_tokens(line.text)
        if token not in cited_numbers
    ]
    players_by_id = {player.participant_id: player for player in players}
    absent_champions = [
        f"participant {participant_id} is not in the game"
        for participant_id in line.champion_participant_ids
        if participant_id not in players_by_id
    ]
    unnamed_champions = [
        f"{players_by_id[participant_id].champion} is not named"
        for participant_id in line.champion_participant_ids
        if participant_id in players_by_id
        and players_by_id[participant_id].champion not in line.text
    ]
    no_citation = ["the line cites no exhibit"] if not line.exhibit_keys else []
    return [
        *no_citation,
        *(f"exhibit {key} does not exist" for key in unknown_keys),
        *slot_mismatches,
        *uncited_numbers,
        *absent_champions,
        *unnamed_champions,
        *floor_problems(line.text),
    ]
