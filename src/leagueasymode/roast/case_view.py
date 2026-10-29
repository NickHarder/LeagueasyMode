"""A case as the post-game window shows it (phase 11.3), from `/case`.

The window lets the player pick a target (the whole team, the enemy team, a lane or any one of the
ten players), a spice level, "Prove it" and another take, and asks `/case` again for each pick.
This flattens the case for the page: every exhibit by its letter, every line in parts that cite a
letter, the lane board with each lane's champions, and the closing line with its length.
`overlay/web/roast_case.schema.json` holds its JSON Schema, which a test keeps current.
"""

import json
import sys
from collections.abc import Mapping
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from leagueasymode.roast.case import CaseOptions, build_case
from leagueasymode.roast.exhibits import Exhibit
from leagueasymode.roast.last_game import LastGameRoast
from leagueasymode.roast.rules import RoastRules
from leagueasymode.roast.targets import parse_target

SPICE_NAMES: Final = {1: "Honor-eligible", 2: "Salty", 3: "Tilted", 4: "Chat-Restricted Speedrun"}
RISKY_SPICE: Final = 3
RISK_WARNING: Final = (
    "At this spice, the closing line is yours to risk: Riot's chat filter mutes blocked words, "
    "reports go through the Instant Feedback System, and severe chat has carried gameplay bans "
    "since patch 26.5. The lines never cross the floor (no slurs, nothing about who a person is), "
    "but Riot decides what it penalises."
)
TRUE_TEXTS: Final = frozenset({"1", "true", "on", "yes"})


class CasePlayer(BaseModel):
    """One of the ten players, for the target chips."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    participant_id: int
    champion: str
    position: str
    # From the player on this machine's side.
    side: Literal["ally", "enemy"]
    is_defendant: bool
    # On the owner's friends list (phase 11.5); never their name.
    is_friend: bool


class ViewPart(BaseModel):
    """A piece of a line; one that states an exhibit's value carries its letter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    letter: str | None


class ViewLine(BaseModel):
    """One line of the case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    parts: tuple[ViewPart, ...]


class ViewLane(BaseModel):
    """One lane of the position diff board, at minute 14."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position: str
    ally_champion: str
    enemy_champion: str
    # "won", "even", "lost" or "gap", by our thresholds.
    outcome: str
    gold_difference: str | None
    cs_difference: str | None
    letter: str | None


class ViewExhibit(BaseModel):
    """One exhibit, and where its value came from."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    letter: str
    label: str
    display: str
    unit: str
    # The path in the client's answer, or the formula of a computation of ours.
    source: str
    source_kind: Literal["game", "timeline", "live", "computation"]
    # On file only because a computation was built from it.
    supporting: bool


class CaseView(BaseModel):
    """A case, for the post-game window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: int
    players: tuple[CasePlayer, ...]
    target: str
    spice: int
    spice_name: str
    prove: bool
    take: int
    verdict_title: str
    verdict_summary: str
    # None when there is no verdict to give, such as a remake.
    acquitted: bool | None
    board: tuple[ViewLane, ...]
    lines: tuple[ViewLine, ...]
    closing_line: str
    # Lines to pick from for chat, the closing line first; the window copies the one clicked.
    closing_options: tuple[str, ...]
    closing_line_limit: int
    risk_warning: str | None
    exhibits: tuple[ViewExhibit, ...]
    # Claude's take of the closing line (phase 11.8): the take when it is ready, and whether one
    # is still being written; None and false while the setting is off.
    claude_take: str | None = None
    claude_take_pending: bool = False
    # A quick case from the end-of-game stats (phase 11.7): no lane verdict until the full one.
    is_quick: bool = False


def case_options_of(query: Mapping[str, str]) -> CaseOptions:
    """Read a case's options from `/case`'s query.

    Args:
        query: "target" (team, enemy, lane:<POSITION> or player:<1-10>), "spice" (1 to 4),
            "prove" (1 or 0) and "take" (0 on); each may be left out for its default.

    Returns:
        The options.

    Raises:
        ValueError: If one is not a value it can take.
    """
    target = query.get("target", "team")
    parse_target(target)
    spice_text = query.get("spice", "2")
    take_text = query.get("take", "0")
    if not spice_text.isdigit() or int(spice_text) not in SPICE_NAMES:
        message = f"spice {spice_text!r} is not 1, 2, 3 or 4"
        raise ValueError(message)
    if not take_text.isdigit():
        message = f"take {take_text!r} is not a whole number"
        raise ValueError(message)
    return CaseOptions(
        target=target,
        spice=int(spice_text),
        prove=query.get("prove", "0").lower() in TRUE_TEXTS,
        take=int(take_text),
    )


def case_view(last_game: LastGameRoast, options: CaseOptions, rules: RoastRules) -> CaseView:
    """Build the last game's case for the window.

    Args:
        last_game: The last game, as kept after it.
        options: The target, spice, "Prove it" and take.
        rules: Our thresholds for the verdict and the chat line's length.

    Returns:
        The case, flattened.
    """
    game = last_game.game
    players = list(game.players)
    case = build_case(
        players,
        game.ledger,
        last_game.defendant_participant_id,
        remade=game.remade,
        options=options,
        rules=rules,
    )
    letter_by_key = {lettered.exhibit.key: lettered.letter for lettered in case.exhibits}
    exhibits_by_key = game.ledger.exhibits
    champion_by_id = {player.participant_id: player.champion for player in players}
    return CaseView(
        game_id=case.game_id,
        players=tuple(
            CasePlayer(
                participant_id=player.participant_id,
                champion=player.champion,
                position=player.position,
                side="ally" if player.team_id == case.defendant.team_id else "enemy",
                is_defendant=player.participant_id == case.defendant.participant_id,
                is_friend=player.is_friend,
            )
            for player in players
        ),
        target=options.target,
        spice=options.spice,
        spice_name=SPICE_NAMES[options.spice],
        prove=options.prove,
        take=options.take,
        verdict_title=case.verdict.title,
        verdict_summary=case.verdict.summary,
        acquitted=case.verdict.acquitted,
        board=tuple(
            ViewLane(
                position=lane.position,
                ally_champion=champion_by_id.get(lane.ally_participant_id, ""),
                enemy_champion=champion_by_id.get(lane.enemy_participant_id, ""),
                outcome=lane.outcome,
                gold_difference=_display(exhibits_by_key, lane.gold_difference_key),
                cs_difference=_display(exhibits_by_key, lane.cs_difference_key),
                letter=letter_by_key.get(lane.gold_difference_key),
            )
            for lane in case.verdict.lanes
        ),
        lines=tuple(
            ViewLine(
                parts=tuple(
                    ViewPart(
                        text=part.text,
                        letter=letter_by_key.get(part.exhibit_key) if part.exhibit_key else None,
                    )
                    for part in line.parts
                )
            )
            for line in case.lines
        ),
        closing_line=case.closing_line.text,
        closing_options=tuple(option.text for option in case.closing_options),
        closing_line_limit=rules.chat_line_max_characters,
        is_quick=last_game.is_quick,
        risk_warning=RISK_WARNING if options.spice >= RISKY_SPICE else None,
        exhibits=tuple(
            ViewExhibit(
                letter=lettered.letter,
                label=lettered.exhibit.label,
                display=lettered.exhibit.display,
                unit=lettered.exhibit.unit,
                source=lettered.exhibit.source.path or lettered.exhibit.source.formula or "",
                source_kind=lettered.exhibit.source.kind,
                supporting=lettered.supporting,
            )
            for lettered in case.exhibits
        ),
    )


def _display(exhibits_by_key: Mapping[str, Exhibit], key: str | None) -> str | None:
    """Return an exhibit's value as written, when it is on file.

    Args:
        exhibits_by_key: The ledger's exhibits.
        key: The exhibit, or None.

    Returns:
        Its display text, or None.
    """
    exhibit = exhibits_by_key.get(key) if key else None
    return exhibit.display if exhibit is not None else None


if __name__ == "__main__":
    # The contract with overlay/web/src/case_state.ts: overlay/web/roast_case.schema.json.
    sys.stdout.write(json.dumps(CaseView.model_json_schema(), indent=2) + "\n")
