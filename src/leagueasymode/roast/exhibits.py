"""An exhibit: one value a case may state, with its unit and exactly where it came from."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

ExhibitValue = int | float | bool | str


class ExhibitSource(BaseModel):
    """Where an exhibit's value came from.

    `game` exhibits carry the JSON path of the value in the client's game details
    (`/lol-match-history/v1/games/<id>`), `timeline` ones a path in the client's timeline of the
    game, and `live` ones a path in the game's API answer at a moment of the game. A
    `computation` is ours: it carries its formula and the keys of the exhibits it was computed
    from, so whoever reads it sees both and knows the number is ours.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["game", "timeline", "live", "computation"]
    path: str | None = None
    formula: str | None = None
    input_keys: tuple[str, ...] = ()


class Exhibit(BaseModel):
    """One value, named, formatted and sourced."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    label: str
    value: ExhibitValue
    display: str
    unit: str
    source: ExhibitSource
    participant_id: int | None = None


class ExhibitLedger(BaseModel):
    """Every exhibit of one game, by key, such as "deaths/p2"."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    game_id: int
    exhibits: dict[str, Exhibit]
