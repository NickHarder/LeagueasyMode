"""A game's players, as a roast needs them: where they played and on what, never their names."""

from pydantic import BaseModel, ConfigDict


class RoastPlayer(BaseModel):
    """One of a game's players."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    participant_id: int
    team_id: int
    # "TOP", "JUNGLE", "MIDDLE", "BOTTOM" or "UTILITY"; empty when the game gave no position.
    position: str
    # The champion's name as people write it ("Lee Sin"), which is all a line ever calls a player.
    champion: str
    won: bool
    # On the owner's friends list (phase 11.5).
    is_friend: bool = False
