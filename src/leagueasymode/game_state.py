"""The game's answer, `/liveclientdata/allgamedata`, as typed models: what the estimators read.

Riot adds fields to this answer between patches (the Riot ID fields arrived that way), so these
models ignore a field they do not know instead of refusing it, unlike the project's own contracts:
refusing one would stop the overlay in the middle of a game on the day a patch lands. Nothing is
lost by it, since the recorder keeps every answer whole.
"""

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

RIOT_ID_SEPARATOR: Final = "#"


class RiotPayloadModel(BaseModel):
    """A model of something Riot sends: unknown fields are ignored, and the model is frozen."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class GameEvent(RiotPayloadModel):
    """One entry of the kill and objective feed."""

    event_id: int = Field(alias="EventID")
    event_name: str = Field(alias="EventName")
    event_time_seconds: float = Field(alias="EventTime")
    killer_name: str | None = Field(default=None, alias="KillerName")
    victim_name: str | None = Field(default=None, alias="VictimName")
    assister_names: list[str] = Field(default_factory=list, alias="Assisters")
    dragon_type: str | None = Field(default=None, alias="DragonType")
    is_stolen: bool = Field(default=False, alias="Stolen")
    turret_killed_name: str | None = Field(default=None, alias="TurretKilled")
    inhibitor_killed_name: str | None = Field(default=None, alias="InhibKilled")
    inhibitor_respawned_name: str | None = Field(default=None, alias="InhibRespawned")


class EventList(RiotPayloadModel):
    """The whole feed so far, oldest first."""

    events: list[GameEvent] = Field(alias="Events")


class ScoreboardItem(RiotPayloadModel):
    """One item in a player's inventory."""

    item_id: int = Field(alias="itemID")
    display_name: str = Field(default="", alias="displayName")
    count: int = 1
    # What the scoreboard says the item is worth; the patch's catalog is preferred when known.
    price: int = 0


class SummonerSpell(RiotPayloadModel):
    """One summoner spell, by the name the game shows (its cooldown is never sent)."""

    display_name: str = Field(default="", alias="displayName")


class SummonerSpells(RiotPayloadModel):
    """A player's two summoner spells."""

    first: SummonerSpell = Field(default_factory=SummonerSpell, alias="summonerSpellOne")
    second: SummonerSpell = Field(default_factory=SummonerSpell, alias="summonerSpellTwo")

    def names(self) -> list[str]:
        """Return both spells' names.

        Returns:
            The names, empty ones left out.
        """
        return [spell.display_name for spell in (self.first, self.second) if spell.display_name]


class Scores(RiotPayloadModel):
    """A player's line on the scoreboard."""

    kills: int = 0
    deaths: int = 0
    assists: int = 0
    creep_score: int = Field(default=0, alias="creepScore")
    ward_score: float = Field(default=0.0, alias="wardScore")


class ScoreboardPlayer(RiotPayloadModel):
    """One of the ten players, as the scoreboard shows them."""

    champion_name: str = Field(alias="championName")
    team: str
    position: str = ""
    level: int = 1
    is_dead: bool = Field(default=False, alias="isDead")
    respawn_timer_seconds: float = Field(default=0.0, alias="respawnTimer")
    summoner_name: str = Field(default="", alias="summonerName")
    riot_id: str = Field(default="", alias="riotId")
    riot_id_game_name: str = Field(default="", alias="riotIdGameName")
    items: list[ScoreboardItem] = Field(default_factory=list)
    summoner_spells: SummonerSpells = Field(default_factory=SummonerSpells, alias="summonerSpells")
    scores: Scores = Field(default_factory=Scores)

    def is_named(self, name: str) -> bool:
        """Return whether the feed's name for someone is this player.

        The feed has named players by summoner name, by Riot ID and by the game name alone,
        depending on the patch, so every form is accepted.

        Args:
            name: A name from the feed, such as `KillerName`.

        Returns:
            Whether it names this player.
        """
        own_names = {self.summoner_name, self.riot_id, self.riot_id_game_name}
        own_game_names = {
            own_name.partition(RIOT_ID_SEPARATOR)[0] for own_name in own_names if own_name
        }
        return bool(name) and (name in own_names or name in own_game_names)


class ActivePlayer(RiotPayloadModel):
    """The player on this machine. Absent when spectating."""

    summoner_name: str = Field(default="", alias="summonerName")
    riot_id: str = Field(default="", alias="riotId")
    riot_id_game_name: str = Field(default="", alias="riotIdGameName")
    level: int = 1
    current_gold: float = Field(default=0.0, alias="currentGold")


class GameData(RiotPayloadModel):
    """The game itself: its mode, its clock and the map's state."""

    game_mode: str = Field(default="", alias="gameMode")
    game_time_seconds: float = Field(alias="gameTime")
    map_number: int = Field(default=0, alias="mapNumber")
    # "Default" until the second dragon; then the soul's element ("Infernal", "Ocean", ...).
    map_terrain: str = Field(default="Default", alias="mapTerrain")


class GameSnapshot(RiotPayloadModel):
    """One whole answer of the game's API."""

    active_player: ActivePlayer | None = Field(default=None, alias="activePlayer")
    players: list[ScoreboardPlayer] = Field(alias="allPlayers")
    event_list: EventList = Field(alias="events")
    game_data: GameData = Field(alias="gameData")

    def team_of(self, name: str | None) -> str | None:
        """Return the team of the player the feed names, or None for a monster, a turret or nobody.

        Args:
            name: A name from the feed.

        Returns:
            `ORDER`, `CHAOS`, or None.
        """
        if not name:
            return None
        return next((player.team for player in self.players if player.is_named(name)), None)

    def ally_team(self) -> str:
        """Return the team of the player on this machine; `ORDER` when spectating.

        Returns:
            `ORDER` or `CHAOS`.
        """
        active_player = self.active_player
        if active_player is not None:
            for active_name in (active_player.riot_id, active_player.summoner_name):
                active_team = self.team_of(active_name)
                if active_team is not None:
                    return active_team
        return "ORDER"
