"""Moments about friends (phase 11.6): a short notice when a friend's game hands over ammo.

Each moment states facts a friend can check on the scoreboard or in the kill feed, from the game's
API as the engine reads it every answer, so it carries no exhibit letters:

- a friend dies to their lane opponent with no help, for the second time, or the third;
- a friend dies shortly before the enemy takes a dragon, the Elder or Baron;
- a friend gives up first blood;
- a friend is a set creep score behind their lane opponent at 10:00 or 14:00;
- a friend's lane opponent has killed them a set number of times while the friend has no kills.

A lane opponent is the enemy in the same role, used only where both roles are given or likely, never
a guess, so a moment is never wrong about who laned against whom. Gold is left out: the game's API
gives other players' gold only as an estimate. The scoreboard may show an enemy's creep score only
while they are in sight, so it can only lag behind: a friend is "at least" so far behind.

Each moment is made once per game per friend and threshold, and shows beside the callouts as a
callout of kind "moment". It is never spoken. ⌃⌥C copies the newest during a game (11.4).
"""

import tomllib
from importlib import resources
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from leagueasymode.game_state import GameEvent, GameSnapshot, ScoreboardPlayer
from leagueasymode.overlay_state import Callout, PlayerCard
from leagueasymode.roast.rules import MomentRules

SURE_ROLE_CONFIDENCES: Final = frozenset({"given", "likely"})
CHAMPION_KILL_EVENT: Final = "ChampionKill"
# The enemy's monsters a death before them makes a moment, by the feed's event, and their names.
DRAGON_KILL_EVENT: Final = "DragonKill"
BARON_KILL_EVENT: Final = "BaronKill"
ELDER_DRAGON_TYPE: Final = "Elder"
CREEP_CHECK_MINUTES: Final = (10, 14)
SECONDS_PER_MINUTE: Final = 60
# A creep score check is made in the first answer this soon after its minute, or not at all.
CREEP_CHECK_WINDOW_SECONDS: Final = 30.0
# A moment noticed later than this after it happened, as when the engine starts mid-game, is kept
# to copy but not shown: a notice about a death minutes ago would only confuse.
FRESH_SECONDS: Final = 30.0
# A clock this far behind the last one is a new game.
NEW_GAME_CLOCK_DROP_SECONDS: Final = 5.0

type MomentKind = Literal[
    "solo_death", "death_before_objective", "first_blood", "creep_behind", "opponent_streak"
]


class MomentLines(BaseModel):
    """One line for each kind of moment, with its slots in braces (`moments.toml`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    solo_death: str
    death_before_objective: str
    first_blood: str
    creep_behind: str
    opponent_streak: str


class Moment(BaseModel):
    """One moment of this game."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Stable for one happening, so that it is made once.
    moment_id: str
    kind: MomentKind
    text: str
    # When it happened, and when the engine noticed it, on the game's clock.
    game_time_seconds: float
    made_at_game_time_seconds: float = 0.0


def load_moment_lines() -> MomentLines:
    """Return the moments' lines.

    Returns:
        The lines in `moments.toml`.
    """
    lines_text = resources.files(__package__).joinpath("moments.toml").read_text("utf-8")
    return MomentLines.model_validate(tomllib.loads(lines_text)["lines"])


class MomentTracker:
    """Reads each answer of the game and makes this game's moments about friends."""

    def __init__(self, rules: MomentRules, lines: MomentLines | None = None) -> None:
        """Start with no game seen.

        Args:
            rules: The thresholds.
            lines: The lines; those of `moments.toml` when None.
        """
        self.rules: Final = rules
        self.lines: Final = lines or load_moment_lines()
        self._moments: list[Moment] = []
        self._last_game_time_seconds: float | None = None

    @property
    def moments(self) -> tuple[Moment, ...]:
        """This game's moments, oldest first."""
        return tuple(self._moments)

    def update(self, snapshot: GameSnapshot | None, cards: list[PlayerCard]) -> list[Moment]:
        """Take the next answer and return the moments it made.

        Args:
            snapshot: The game's answer; None when no game is running.
            cards: The players' cards for it, which say who is a friend and each one's role.

        Returns:
            The new moments, oldest first.
        """
        if snapshot is None:
            self._moments = []
            self._last_game_time_seconds = None
            return []
        game_time_seconds = snapshot.game_data.game_time_seconds
        last_game_time_seconds = self._last_game_time_seconds
        if (
            last_game_time_seconds is not None
            and game_time_seconds < last_game_time_seconds - NEW_GAME_CLOCK_DROP_SECONDS
        ):
            self._moments = []
        self._last_game_time_seconds = game_time_seconds
        made_ids = {moment.moment_id for moment in self._moments}
        new_moments = [
            moment.model_copy(update={"made_at_game_time_seconds": game_time_seconds})
            for moment in self._candidates(snapshot, cards, game_time_seconds)
            if moment.moment_id not in made_ids
        ]
        self._moments.extend(new_moments)
        return new_moments

    def callouts(self, game_time_seconds: float | None) -> list[Callout]:
        """Return the moments still shown, as callouts of kind "moment".

        Args:
            game_time_seconds: The game's clock; None when no game is running.

        Returns:
            The moments made less than `shown_seconds` ago and noticed while fresh, oldest first.
        """
        if game_time_seconds is None:
            return []
        return [
            Callout(
                callout_id=f"moment:{moment.moment_id}",
                kind="moment",
                text=moment.text,
                shown_until_game_time_seconds=moment.made_at_game_time_seconds
                + self.rules.shown_seconds,
            )
            for moment in self._moments
            if moment.made_at_game_time_seconds + self.rules.shown_seconds > game_time_seconds
            and moment.made_at_game_time_seconds - moment.game_time_seconds <= FRESH_SECONDS
        ]

    def _candidates(
        self, snapshot: GameSnapshot, cards: list[PlayerCard], game_time_seconds: float
    ) -> list[Moment]:
        """Return every moment the game so far holds, the ones already made among them.

        Args:
            snapshot: The game's answer.
            cards: The players' cards.
            game_time_seconds: The game's clock.

        Returns:
            The moments, in the order they happened.
        """
        friends = _friends_with_opponents(snapshot, cards)
        kills = [
            event for event in snapshot.event_list.events if event.event_name == CHAMPION_KILL_EVENT
        ]
        candidates: list[Moment] = []
        for friend, friend_card, opponent in friends:
            candidates.extend(self._first_blood(friend, friend_card, kills))
            candidates.extend(self._deaths_before_objectives(snapshot, friend, friend_card, kills))
            if opponent is None:
                continue
            opponent_player, opponent_card = opponent
            candidates.extend(
                self._solo_deaths(friend, friend_card, opponent_player, opponent_card, kills)
            )
            candidates.extend(
                self._opponent_streak(friend, friend_card, opponent_player, opponent_card, kills)
            )
            candidates.extend(
                self._creep_behind(
                    friend, friend_card, opponent_player, opponent_card, game_time_seconds
                )
            )
        return sorted(candidates, key=lambda moment: moment.game_time_seconds)

    def _first_blood(
        self, friend: ScoreboardPlayer, friend_card: PlayerCard, kills: list[GameEvent]
    ) -> list[Moment]:
        """Return first blood, when the friend gave it up."""
        if not kills or not friend.is_named(kills[0].victim_name or ""):
            return []
        first_kill = kills[0]
        return [
            Moment(
                moment_id=f"first_blood:{friend_card.champion_name}",
                kind="first_blood",
                text=self.lines.first_blood.format(
                    friend=friend_card.champion_name,
                    clock=_clock(first_kill.event_time_seconds),
                ),
                game_time_seconds=first_kill.event_time_seconds,
            )
        ]

    def _solo_deaths(
        self,
        friend: ScoreboardPlayer,
        friend_card: PlayerCard,
        opponent: ScoreboardPlayer,
        opponent_card: PlayerCard,
        kills: list[GameEvent],
    ) -> list[Moment]:
        """Return the friend's second and third deaths to their lane opponent with no help."""
        solo_deaths = [
            event
            for event in kills
            if friend.is_named(event.victim_name or "")
            and opponent.is_named(event.killer_name or "")
            and not event.assister_names
        ]
        return [
            Moment(
                moment_id=f"solo_death:{friend_card.champion_name}:{count}",
                kind="solo_death",
                text=self.lines.solo_death.format(
                    friend=friend_card.champion_name,
                    opponent=opponent_card.champion_name,
                    count=count,
                ),
                game_time_seconds=solo_deaths[count - 1].event_time_seconds,
            )
            for count in self.rules.solo_death_counts
            if len(solo_deaths) >= count
        ]

    def _opponent_streak(
        self,
        friend: ScoreboardPlayer,
        friend_card: PlayerCard,
        opponent: ScoreboardPlayer,
        opponent_card: PlayerCard,
        kills: list[GameEvent],
    ) -> list[Moment]:
        """Return the lane opponent reaching the count of kills on the friend, who has none."""
        wanted_kills = self.rules.opponent_kills_without_reply
        opponent_kills = [
            event
            for event in kills
            if friend.is_named(event.victim_name or "")
            and opponent.is_named(event.killer_name or "")
        ]
        friend_has_a_kill = any(friend.is_named(event.killer_name or "") for event in kills)
        if len(opponent_kills) < wanted_kills or friend_has_a_kill:
            return []
        return [
            Moment(
                moment_id=f"opponent_streak:{friend_card.champion_name}:{wanted_kills}",
                kind="opponent_streak",
                text=self.lines.opponent_streak.format(
                    friend=friend_card.champion_name,
                    opponent=opponent_card.champion_name,
                    kills=wanted_kills,
                ),
                game_time_seconds=opponent_kills[wanted_kills - 1].event_time_seconds,
            )
        ]

    def _deaths_before_objectives(
        self,
        snapshot: GameSnapshot,
        friend: ScoreboardPlayer,
        friend_card: PlayerCard,
        kills: list[GameEvent],
    ) -> list[Moment]:
        """Return each enemy dragon, Elder or Baron the friend died shortly before."""
        friend_deaths = [event for event in kills if friend.is_named(event.victim_name or "")]
        moments: list[Moment] = []
        for monster_event in snapshot.event_list.events:
            monster_name = _monster_name(monster_event)
            killer_team = snapshot.team_of(monster_event.killer_name)
            if monster_name is None or killer_team is None or killer_team == friend.team:
                continue
            deaths_before = [
                death
                for death in friend_deaths
                if 0
                < monster_event.event_time_seconds - death.event_time_seconds
                <= self.rules.before_objective_seconds
            ]
            if not deaths_before:
                continue
            last_death = deaths_before[-1]
            seconds_before = round(monster_event.event_time_seconds - last_death.event_time_seconds)
            moments.append(
                Moment(
                    moment_id=(
                        f"death_before_objective:{friend_card.champion_name}:"
                        f"{monster_event.event_id}"
                    ),
                    kind="death_before_objective",
                    text=self.lines.death_before_objective.format(
                        friend=friend_card.champion_name,
                        seconds=seconds_before,
                        monster=monster_name,
                    ),
                    game_time_seconds=monster_event.event_time_seconds,
                )
            )
        return moments

    def _creep_behind(
        self,
        friend: ScoreboardPlayer,
        friend_card: PlayerCard,
        opponent: ScoreboardPlayer,
        opponent_card: PlayerCard,
        game_time_seconds: float,
    ) -> list[Moment]:
        """Return the friend's creep score deficit at 10:00 or 14:00, read at that minute."""
        moments: list[Moment] = []
        for minute in CREEP_CHECK_MINUTES:
            minute_seconds = minute * SECONDS_PER_MINUTE
            threshold = (
                self.rules.creep_behind_at_ten
                if minute == 10
                else self.rules.creep_behind_at_fourteen
            )
            # The scoreboard's creep score now, read only just after the minute.
            if not 0 <= game_time_seconds - minute_seconds <= CREEP_CHECK_WINDOW_SECONDS:
                continue
            behind = opponent.scores.creep_score - friend.scores.creep_score
            if behind < threshold:
                continue
            moments.append(
                Moment(
                    moment_id=f"creep_behind:{friend_card.champion_name}:{minute}",
                    kind="creep_behind",
                    text=self.lines.creep_behind.format(
                        friend=friend_card.champion_name,
                        opponent=opponent_card.champion_name,
                        creep=behind,
                        clock=_clock(minute_seconds),
                    ),
                    game_time_seconds=game_time_seconds,
                )
            )
        return moments


def _friends_with_opponents(
    snapshot: GameSnapshot, cards: list[PlayerCard]
) -> list[tuple[ScoreboardPlayer, PlayerCard, tuple[ScoreboardPlayer, PlayerCard] | None]]:
    """Return each friend in the game, their card, and their lane opponent when sure of it.

    Args:
        snapshot: The game's answer.
        cards: The players' cards.

    Returns:
        The friends, each with their lane opponent's player and card, or None.
    """
    ally_team = snapshot.ally_team()
    card_by_side_and_champion = {(card.side, card.champion_name): card for card in cards}
    players_with_cards = [
        (
            player,
            card_by_side_and_champion.get(
                ("ally" if player.team == ally_team else "enemy", player.champion_name)
            ),
        )
        for player in snapshot.players
    ]
    known = [(player, card) for player, card in players_with_cards if card is not None]
    friends: list[
        tuple[ScoreboardPlayer, PlayerCard, tuple[ScoreboardPlayer, PlayerCard] | None]
    ] = []
    for player, card in known:
        if not card.is_friend:
            continue
        opponents = [
            (other, other_card)
            for other, other_card in known
            if other.team != player.team
            and card.role_confidence in SURE_ROLE_CONFIDENCES
            and other_card.role_confidence in SURE_ROLE_CONFIDENCES
            and other_card.role == card.role
            and card.role != ""
        ]
        friends.append((player, card, opponents[0] if len(opponents) == 1 else None))
    return friends


def _monster_name(event: GameEvent) -> str | None:
    """Return what an event's monster is called in a moment, or None for any other event."""
    if event.event_name == BARON_KILL_EVENT:
        return "Baron"
    if event.event_name == DRAGON_KILL_EVENT:
        return "Elder Dragon" if event.dragon_type == ELDER_DRAGON_TYPE else "dragon"
    return None


def _clock(seconds: float) -> str:
    """Return a game time as minutes and seconds: "2:41"."""
    whole_seconds = round(seconds)
    return f"{whole_seconds // SECONDS_PER_MINUTE}:{whole_seconds % SECONDS_PER_MINUTE:02d}"
