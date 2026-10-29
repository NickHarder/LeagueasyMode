"""The exhibits of a game's timeline from the League client: lanes at 10:00 and 14:00, and events.

The timeline (`/lol-match-history/v1/game-timelines/<id>`) holds a frame about once a minute, each
with every participant's gold, creep score and level, and the events since the frame before. A
minute's frame is the one within half a minute of it; a game without one has no lane exhibits, and
so no lane verdict. Each exhibit cites its value's path in the timeline, and the differences and
outcomes are computations of ours that say so.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from pydantic import JsonValue

from leagueasymode.roast.client_json import as_list, as_object, as_whole_number
from leagueasymode.roast.exhibits import Exhibit, ExhibitSource
from leagueasymode.roast.lanes import lane_opponents, lane_outcome, lane_outcome_formula
from leagueasymode.roast.numbers import format_clock, format_count, format_signed
from leagueasymode.roast.players import RoastPlayer
from leagueasymode.roast.rules import LaneRules

MILLISECONDS_PER_MINUTE: Final = 60_000
MILLISECONDS_PER_SECOND: Final = 1000
SECONDS_PER_MINUTE: Final = 60
FRAME_TOLERANCE_MILLISECONDS: Final = 30_000
LANE_MINUTES: Final = (10, 14)
VERDICT_MINUTE: Final = 14
CARRY_INDEX_MINUTE: Final = 20
GOLD_PER_INDEX_POINT: Final = 100
THROW_WINDOW_MILLISECONDS: Final = 60_000
DIED_RICH_GOLD: Final = 1500
CHAMPION_KILL: Final = "CHAMPION_KILL"
ELITE_MONSTER_KILL: Final = "ELITE_MONSTER_KILL"
MONSTER_NAMES: Final = {"BARON_NASHOR": "Baron", "DRAGON": "dragon", "ELDER_DRAGON": "Elder Dragon"}


@dataclass(frozen=True)
class FrameView:
    """One participant's numbers at one frame, and the path to them."""

    path: str
    numbers: dict[str, JsonValue]


@dataclass(frozen=True)
class LocatedEvent:
    """One event of the timeline, with its path."""

    path: str
    event: dict[str, JsonValue]

    def number(self, field_name: str) -> int | None:
        """Return one of the event's whole numbers.

        Args:
            field_name: The field, such as "victimId".

        Returns:
            The number, or None.
        """
        return as_whole_number(self.event.get(field_name))

    @property
    def event_type(self) -> str:
        """The event's type, such as "CHAMPION_KILL"."""
        value = self.event.get("type")
        return value if isinstance(value, str) else ""

    @property
    def assisting_ids(self) -> list[int]:
        """The participants who helped, for a kill."""
        return [
            assister
            for assister in (
                as_whole_number(item) for item in as_list(self.event.get("assistingParticipantIds"))
            )
            if assister is not None
        ]


class TimelineReader:
    """A timeline's frames and events, read where they are."""

    def __init__(self, timeline_payload: JsonValue | None) -> None:
        """Read the frames.

        Args:
            timeline_payload: The client's timeline, or None.
        """
        timeline = as_object(timeline_payload) or {}
        self.frames = [as_object(frame) or {} for frame in as_list(timeline.get("frames"))]

    def frame_index_at(self, minute: int) -> int | None:
        """Return the index of the frame within half a minute of a minute, the nearest one.

        Args:
            minute: The minute.

        Returns:
            The frame's index, or None when no frame is that close.
        """
        target_milliseconds = minute * MILLISECONDS_PER_MINUTE
        candidates = [
            (abs(timestamp - target_milliseconds), index)
            for index, frame in enumerate(self.frames)
            if (timestamp := as_whole_number(frame.get("timestamp"))) is not None
            and abs(timestamp - target_milliseconds) <= FRAME_TOLERANCE_MILLISECONDS
        ]
        return min(candidates)[1] if candidates else None

    def participant_frame(self, frame_index: int, participant_id: int) -> FrameView | None:
        """Return a participant's numbers at a frame, keyed by id or listed, with their path.

        Args:
            frame_index: The frame.
            participant_id: The participant.

        Returns:
            The numbers, or None when the frame does not hold them.
        """
        participant_frames = self.frames[frame_index].get("participantFrames")
        frames_object = as_object(participant_frames)
        if frames_object is not None:
            keyed = as_object(frames_object.get(str(participant_id)))
            return (
                FrameView(f"frames[{frame_index}].participantFrames.{participant_id}", keyed)
                if keyed is not None
                else None
            )
        for list_index, entry in enumerate(as_list(participant_frames)):
            entry_object = as_object(entry) or {}
            if as_whole_number(entry_object.get("participantId")) == participant_id:
                return FrameView(
                    f"frames[{frame_index}].participantFrames[{list_index}]", entry_object
                )
        return None

    def events(self) -> Iterator[LocatedEvent]:
        """Yield every event, in order, with its path.

        Yields:
            The events.
        """
        for frame_index, frame in enumerate(self.frames):
            for event_index, event in enumerate(as_list(frame.get("events"))):
                event_object = as_object(event)
                if event_object is not None:
                    yield LocatedEvent(f"frames[{frame_index}].events[{event_index}]", event_object)


def timeline_exhibits(
    timeline_payload: JsonValue | None,
    players: list[RoastPlayer],
    game_exhibits: dict[str, Exhibit],
    lane_rules: LaneRules,
) -> list[Exhibit]:
    """Return every exhibit the timeline gives.

    Args:
        timeline_payload: The client's timeline, or None when it has not come.
        players: The game's players.
        game_exhibits: The exhibits from the game's details, by key, which the Carry Impossibility
            Index adds to.
        lane_rules: Our thresholds for a lane's outcome.

    Returns:
        The exhibits; none without a timeline.
    """
    if timeline_payload is None:
        return []
    reader = TimelineReader(timeline_payload)
    exhibits = [
        *_lane_exhibits(reader, players, lane_rules),
        *_kill_exhibits(reader, players),
        *_died_rich_exhibits(reader, players),
    ]
    exhibits_by_key = {**game_exhibits, **{exhibit.key: exhibit for exhibit in exhibits}}
    return [*exhibits, *_carry_index_exhibits(reader, players, exhibits_by_key)]


def _number_exhibit(
    view: FrameView, field_name: str, *, key: str, label: str, unit: str, participant_id: int
) -> Exhibit | None:
    """Return one number of a participant's frame as an exhibit.

    Args:
        view: The participant's frame.
        field_name: The field, such as "totalGold".
        key: The exhibit's key.
        label: What it is.
        unit: Its unit.
        participant_id: The participant.

    Returns:
        The exhibit, or None when the frame does not hold the field.
    """
    value = as_whole_number(view.numbers.get(field_name))
    if value is None:
        return None
    return Exhibit(
        key=key,
        label=label,
        value=value,
        display=format_count(value),
        unit=unit,
        source=ExhibitSource(kind="timeline", path=f"{view.path}.{field_name}"),
        participant_id=participant_id,
    )


def _lane_exhibits(
    reader: TimelineReader, players: list[RoastPlayer], lane_rules: LaneRules
) -> list[Exhibit]:
    """Return each lane minute's clock and every player's gold, and at 14:00 creep score and level.

    Args:
        reader: The timeline.
        players: The game's players.
        lane_rules: Our thresholds for a lane's outcome.

    Returns:
        The frame numbers and the comparisons with the lane opponent.
    """
    exhibits: list[Exhibit] = []
    for minute in LANE_MINUTES:
        frame_index = reader.frame_index_at(minute)
        if frame_index is None:
            continue
        timestamp = as_whole_number(reader.frames[frame_index].get("timestamp")) or 0
        exhibits.append(
            Exhibit(
                key=f"clock_{minute}",
                label=f"The timeline's frame for minute {minute}",
                value=timestamp,
                display=format_clock(round(timestamp / MILLISECONDS_PER_SECOND)),
                unit="game clock",
                source=ExhibitSource(kind="timeline", path=f"frames[{frame_index}].timestamp"),
            )
        )
        for player in players:
            view = reader.participant_frame(frame_index, player.participant_id)
            if view is None:
                continue
            fields = [
                (
                    "totalGold",
                    f"gold_at_{minute}",
                    "gold",
                    f"{player.champion}'s gold at minute {minute}",
                )
            ]
            if minute == VERDICT_MINUTE:
                fields.extend(
                    [
                        (
                            "minionsKilled",
                            "minions_at_14",
                            "minions",
                            f"Lane minions {player.champion} had killed by minute 14",
                        ),
                        (
                            "jungleMinionsKilled",
                            "jungle_minions_at_14",
                            "monsters",
                            f"Jungle monsters {player.champion} had killed by minute 14",
                        ),
                        (
                            "level",
                            "level_at_14",
                            "level",
                            f"{player.champion}'s level at minute 14",
                        ),
                    ]
                )
            for field_name, name, unit, label in fields:
                found = _number_exhibit(
                    view,
                    field_name,
                    key=f"{name}/p{player.participant_id}",
                    label=label,
                    unit=unit,
                    participant_id=player.participant_id,
                )
                if found is not None:
                    exhibits.append(found)
    by_key = {exhibit.key: exhibit for exhibit in exhibits}
    exhibits.extend(_creep_scores(players, by_key))
    by_key_with_creep = {**by_key, **{exhibit.key: exhibit for exhibit in exhibits}}
    exhibits.extend(_lane_comparisons(players, by_key_with_creep, lane_rules))
    return exhibits


def _creep_scores(players: list[RoastPlayer], by_key: dict[str, Exhibit]) -> list[Exhibit]:
    """Return each player's creep score at 14:00: lane minions plus jungle monsters.

    Args:
        players: The game's players.
        by_key: The frame exhibits so far, by key.

    Returns:
        One computation per player with both counts.
    """
    creep_scores: list[Exhibit] = []
    for player in players:
        minion_key = f"minions_at_14/p{player.participant_id}"
        monster_key = f"jungle_minions_at_14/p{player.participant_id}"
        if minion_key in by_key and monster_key in by_key:
            total = _whole(by_key[minion_key]) + _whole(by_key[monster_key])
            creep_scores.append(
                Exhibit(
                    key=f"cs_at_14/p{player.participant_id}",
                    label=f"{player.champion}'s creep score at minute 14",
                    value=total,
                    display=format_count(total),
                    unit="CS",
                    source=ExhibitSource(
                        kind="computation",
                        formula="lane minions plus jungle monsters, at minute 14",
                        input_keys=(minion_key, monster_key),
                    ),
                    participant_id=player.participant_id,
                )
            )
    return creep_scores


def _lane_comparisons(
    players: list[RoastPlayer], by_key: dict[str, Exhibit], lane_rules: LaneRules
) -> list[Exhibit]:
    """Return each player's gold, creep score and level against their lane opponent's.

    Args:
        players: The game's players.
        by_key: The frame exhibits, by key.
        lane_rules: Our thresholds for a lane's outcome.

    Returns:
        The differences, their sizes without a sign, and the lane's outcome at 14:00.
    """
    champion_by_id = {player.participant_id: player.champion for player in players}
    comparisons: list[Exhibit] = []
    for player_id, opponent_id in lane_opponents(players).items():
        champion = champion_by_id[player_id]
        opponent = champion_by_id[opponent_id]
        for minute in LANE_MINUTES:
            difference = _difference(by_key, f"gold_at_{minute}", player_id, opponent_id)
            if difference is None:
                continue
            difference_key = f"gold_diff_{minute}/p{player_id}"
            comparisons.append(
                _signed_difference(
                    difference_key,
                    f"{champion}'s gold against {opponent} at minute {minute}",
                    difference=difference,
                    unit="gold",
                    input_keys=(
                        f"gold_at_{minute}/p{player_id}",
                        f"gold_at_{minute}/p{opponent_id}",
                    ),
                    player_id=player_id,
                )
            )
            if minute == VERDICT_MINUTE:
                comparisons.extend(
                    _sided(
                        difference_key,
                        "gold_ahead_14",
                        "gold_behind_14",
                        difference=difference,
                        unit="gold",
                        player_id=player_id,
                        who=f"{champion} and {opponent}",
                    )
                )
                comparisons.append(
                    Exhibit(
                        key=f"lane_outcome_14/p{player_id}",
                        label=f"{champion}'s lane against {opponent}",
                        value=lane_outcome(difference, lane_rules),
                        display=lane_outcome(difference, lane_rules),
                        unit="",
                        source=ExhibitSource(
                            kind="computation",
                            formula=lane_outcome_formula(lane_rules),
                            input_keys=(difference_key,),
                        ),
                        participant_id=player_id,
                    )
                )
        creep_difference = _difference(by_key, "cs_at_14", player_id, opponent_id)
        if creep_difference is not None:
            creep_key = f"cs_diff_14/p{player_id}"
            comparisons.append(
                _signed_difference(
                    creep_key,
                    f"{champion}'s creep score against {opponent}'s at minute 14",
                    difference=creep_difference,
                    unit="CS",
                    input_keys=(f"cs_at_14/p{player_id}", f"cs_at_14/p{opponent_id}"),
                    player_id=player_id,
                )
            )
            comparisons.extend(
                _sided(
                    creep_key,
                    "cs_ahead_14",
                    "cs_behind_14",
                    difference=creep_difference,
                    unit="CS",
                    player_id=player_id,
                    who=f"{champion} and {opponent}",
                )
            )
        level_gap = _difference(by_key, "level_at_14", opponent_id, player_id)
        if level_gap is not None and level_gap > 0:
            comparisons.append(
                Exhibit(
                    key=f"levels_behind_14/p{player_id}",
                    label=f"Levels {champion} trailed {opponent} by at minute 14",
                    value=level_gap,
                    display=format_count(level_gap),
                    unit="levels",
                    source=ExhibitSource(
                        kind="computation",
                        formula=f"{opponent}'s level minus {champion}'s, at minute 14",
                        input_keys=(f"level_at_14/p{opponent_id}", f"level_at_14/p{player_id}"),
                    ),
                    participant_id=player_id,
                )
            )
    return comparisons


def _difference(by_key: dict[str, Exhibit], name: str, first_id: int, second_id: int) -> int | None:
    """Return one player's number minus another's, when both are on file.

    Args:
        by_key: The exhibits, by key.
        name: The exhibits' name, such as "gold_at_14".
        first_id: The participant whose number comes first.
        second_id: The participant whose number is taken away.

    Returns:
        The difference, or None.
    """
    first_key = f"{name}/p{first_id}"
    second_key = f"{name}/p{second_id}"
    if first_key not in by_key or second_key not in by_key:
        return None
    return _whole(by_key[first_key]) - _whole(by_key[second_key])


def _signed_difference(
    key: str,
    label: str,
    *,
    difference: int,
    unit: str,
    input_keys: tuple[str, str],
    player_id: int,
) -> Exhibit:
    """Return a difference with its sign, as a computation.

    Args:
        key: The exhibit's key.
        label: What it compares.
        difference: The difference.
        unit: Its unit.
        input_keys: The two numbers it takes one from the other.
        player_id: The player it is about.

    Returns:
        The exhibit.
    """
    return Exhibit(
        key=key,
        label=label,
        value=difference,
        display=format_signed(difference),
        unit=unit,
        source=ExhibitSource(
            kind="computation",
            formula=f"{input_keys[0]} minus {input_keys[1]}",
            input_keys=input_keys,
        ),
        participant_id=player_id,
    )


def _sided(
    difference_key: str,
    ahead_name: str,
    behind_name: str,
    *,
    difference: int,
    unit: str,
    player_id: int,
    who: str,
) -> list[Exhibit]:
    """Return how far ahead or behind a difference is, without its sign; nothing when even.

    Args:
        difference_key: The difference's exhibit.
        ahead_name: The name for a lead, such as "gold_ahead_14".
        behind_name: The name for a deficit.
        difference: The difference.
        unit: Its unit.
        player_id: The player it is about.
        who: The two champions, for the label.

    Returns:
        One exhibit, or none.
    """
    if not difference:
        return []
    return [
        Exhibit(
            key=f"{ahead_name if difference > 0 else behind_name}/p{player_id}",
            label=f"The {unit} between {who} at minute 14",
            value=abs(difference),
            display=format_count(abs(difference)),
            unit=unit,
            source=ExhibitSource(
                kind="computation",
                formula="the difference at minute 14, without its sign",
                input_keys=(difference_key,),
            ),
            participant_id=player_id,
        )
    ]


def _clock_exhibit(key: str, label: str, located: LocatedEvent, participant_id: int) -> Exhibit:
    """Return an event's time as an exhibit.

    Args:
        key: The exhibit's key.
        label: What the time is of.
        located: The event.
        participant_id: The player it is about.

    Returns:
        The exhibit, written as a game clock.
    """
    timestamp = located.number("timestamp") or 0
    return Exhibit(
        key=key,
        label=label,
        value=timestamp,
        display=format_clock(timestamp // MILLISECONDS_PER_SECOND),
        unit="game clock",
        source=ExhibitSource(kind="timeline", path=f"{located.path}.timestamp"),
        participant_id=participant_id,
    )


def _kill_exhibits(reader: TimelineReader, players: list[RoastPlayer]) -> list[Exhibit]:
    """Return first blood, victims per killer, solo deaths and deaths before objectives.

    Args:
        reader: The timeline.
        players: The game's players.

    Returns:
        The exhibits.
    """
    by_id = {player.participant_id: player for player in players}
    opponents = lane_opponents(players)
    events = list(reader.events())
    kills = [
        located
        for located in events
        if located.event_type == CHAMPION_KILL and (located.number("victimId") or 0) in by_id
    ]
    monsters = [located for located in events if located.event_type == ELITE_MONSTER_KILL]
    exhibits: list[Exhibit] = []
    if kills:
        first_victim = by_id[kills[0].number("victimId") or 0]
        exhibits.append(
            _clock_exhibit(
                f"first_blood_clock/p{first_victim.participant_id}",
                f"When {first_victim.champion} gave up first blood",
                kills[0],
                first_victim.participant_id,
            )
        )
    victims_by_killer: dict[int, set[int]] = {}
    for located in kills:
        killer_id = located.number("killerId")
        if killer_id in by_id and killer_id is not None:
            victims_by_killer.setdefault(killer_id, set()).add(located.number("victimId") or 0)
    exhibits.extend(
        Exhibit(
            key=f"distinct_victims/p{killer_id}",
            label=f"Different players {by_id[killer_id].champion} killed",
            value=len(victims),
            display=format_count(len(victims)),
            unit="players",
            source=ExhibitSource(
                kind="computation",
                formula=f"different victimIds among the timeline's {CHAMPION_KILL} events "
                f"with killerId {killer_id}",
            ),
            participant_id=killer_id,
        )
        for killer_id, victims in victims_by_killer.items()
    )
    for victim in players:
        own_deaths = [
            located for located in kills if located.number("victimId") == victim.participant_id
        ]
        opponent_id = opponents.get(victim.participant_id)
        solo_deaths = [
            located
            for located in own_deaths
            if opponent_id is not None
            and located.number("killerId") == opponent_id
            and not located.assisting_ids
        ]
        exhibits.extend(_solo_death_exhibits(victim, by_id.get(opponent_id or 0), solo_deaths))
        exhibits.extend(_throw_exhibits(victim, own_deaths, monsters))
    return exhibits


def _solo_death_exhibits(
    victim: RoastPlayer, opponent: RoastPlayer | None, solo_deaths: list[LocatedEvent]
) -> list[Exhibit]:
    """Return each death to the lane opponent with no help, and their count.

    Args:
        victim: The player.
        opponent: Their lane opponent.
        solo_deaths: Those deaths.

    Returns:
        The clocks and the count; nothing when there were none.
    """
    if opponent is None or not solo_deaths:
        return []
    clocks = [
        _clock_exhibit(
            f"solo_death_{number}_clock/p{victim.participant_id}",
            f"When {opponent.champion} killed {victim.champion} alone",
            located,
            victim.participant_id,
        )
        for number, located in enumerate(solo_deaths, start=1)
    ]
    return [
        *clocks,
        Exhibit(
            key=f"solo_deaths_to_opponent/p{victim.participant_id}",
            label=f"Times {opponent.champion} killed {victim.champion} with no help",
            value=len(solo_deaths),
            display=format_count(len(solo_deaths)),
            unit="deaths",
            source=ExhibitSource(
                kind="computation",
                formula=f"the timeline's {CHAMPION_KILL} events with victimId "
                f"{victim.participant_id}, killerId {opponent.participant_id} (the lane opponent) "
                "and no assistingParticipantIds",
                input_keys=tuple(clock.key for clock in clocks),
            ),
            participant_id=victim.participant_id,
        ),
    ]


def _throw_exhibits(
    victim: RoastPlayer, own_deaths: list[LocatedEvent], monsters: list[LocatedEvent]
) -> list[Exhibit]:
    """Return a player's closest death in the minute before the enemy took an epic monster.

    Args:
        victim: The player.
        own_deaths: Their deaths.
        monsters: Every epic monster kill.

    Returns:
        The death's clock, the monster's clock, what it was and the seconds between; or nothing.
    """
    candidates = [
        ((monster.number("timestamp") or 0) - (death.number("timestamp") or 0), death, monster)
        for death in own_deaths
        for monster in monsters
        if monster.number("killerTeamId") not in (None, 0, victim.team_id)
        and str(monster.event.get("monsterType")) in MONSTER_NAMES
        and 0
        < (monster.number("timestamp") or 0) - (death.number("timestamp") or 0)
        <= THROW_WINDOW_MILLISECONDS
    ]
    if not candidates:
        return []
    gap_milliseconds, death, monster = min(candidates, key=lambda candidate: candidate[0])
    participant_id = victim.participant_id
    is_elder = monster.event.get("monsterSubType") == "ELDER_DRAGON"
    monster_name = MONSTER_NAMES[
        "ELDER_DRAGON" if is_elder else str(monster.event.get("monsterType"))
    ]
    death_key = f"throw_death_clock/p{participant_id}"
    monster_key = f"throw_objective_clock/p{participant_id}"
    seconds_before = gap_milliseconds // MILLISECONDS_PER_SECOND
    return [
        Exhibit(
            key=f"throw_objective/p{participant_id}",
            label=f"What the enemy took after {victim.champion} died",
            value=str(monster.event.get("monsterType")),
            display=monster_name,
            unit="",
            source=ExhibitSource(kind="timeline", path=f"{monster.path}.monsterType"),
            participant_id=participant_id,
        ),
        _clock_exhibit(death_key, f"When {victim.champion} died", death, participant_id),
        _clock_exhibit(
            monster_key, f"When the enemy took the {monster_name} after it", monster, participant_id
        ),
        Exhibit(
            key=f"throw_seconds_before/p{participant_id}",
            label=f"Seconds between {victim.champion}'s death and the enemy's {monster_name}",
            value=seconds_before,
            display=format_count(seconds_before),
            unit="seconds",
            source=ExhibitSource(
                kind="computation",
                formula="the monster's time minus the death's time, in whole seconds",
                input_keys=(death_key, monster_key),
            ),
            participant_id=participant_id,
        ),
    ]


def _died_rich_exhibits(reader: TimelineReader, players: list[RoastPlayer]) -> list[Exhibit]:
    """Return, per player, the most unspent gold they held in the frame before one of their deaths.

    Args:
        reader: The timeline.
        players: The game's players.

    Returns:
        One exhibit per player who died holding at least the threshold.
    """
    by_id = {player.participant_id: player for player in players}
    richest: dict[int, tuple[int, str]] = {}
    for frame_index, frame in enumerate(reader.frames):
        for event in as_list(frame.get("events")):
            event_object = as_object(event) or {}
            victim_id = as_whole_number(event_object.get("victimId"))
            if (
                event_object.get("type") != CHAMPION_KILL
                or victim_id not in by_id
                or frame_index == 0
            ):
                continue
            view = reader.participant_frame(frame_index - 1, victim_id or 0)
            gold = as_whole_number(view.numbers.get("currentGold")) if view is not None else None
            if (
                view is not None
                and gold is not None
                and gold >= DIED_RICH_GOLD
                and gold > richest.get(victim_id or 0, (0, ""))[0]
            ):
                richest[victim_id or 0] = (gold, f"{view.path}.currentGold")
    return [
        Exhibit(
            key=f"died_rich_gold/p{victim_id}",
            label=f"Unspent gold {by_id[victim_id].champion} held before dying",
            value=gold,
            display=format_count(gold),
            unit="gold",
            source=ExhibitSource(kind="timeline", path=path),
            participant_id=victim_id,
        )
        for victim_id, (gold, path) in richest.items()
    ]


def _carry_index_exhibits(
    reader: TimelineReader, players: list[RoastPlayer], by_key: dict[str, Exhibit]
) -> list[Exhibit]:
    """Return each losing player's Carry Impossibility Index, with the three numbers it adds up.

    The index is made up, and says so: the teammates' gold deficit to their lane opponents at
    minute 20 in hundreds, plus their combined minutes spent dead, plus the player's share of the
    team's damage in percent.

    Args:
        reader: The timeline.
        players: The game's players.
        by_key: Every exhibit so far, by key: the time dead and the damage share among them.

    Returns:
        Four exhibits per losing player whose numbers are all on file.
    """
    frame_index = reader.frame_index_at(CARRY_INDEX_MINUTE)
    if frame_index is None:
        return []
    opponents = lane_opponents(players)
    views = {
        player.participant_id: reader.participant_frame(frame_index, player.participant_id)
        for player in players
    }
    gold_by_id = {
        participant_id: as_whole_number(view.numbers.get("totalGold"))
        for participant_id, view in views.items()
        if view is not None
    }
    exhibits: list[Exhibit] = []
    for player in players:
        share_key = f"damage_share/p{player.participant_id}"
        teammates = [
            mate
            for mate in players
            if mate.team_id == player.team_id
            and mate.participant_id != player.participant_id
            and mate.participant_id in opponents
        ]
        dead_keys = [f"time_dead/p{mate.participant_id}" for mate in teammates]
        golds_known = all(
            gold_by_id.get(mate.participant_id) is not None
            and gold_by_id.get(opponents[mate.participant_id]) is not None
            for mate in teammates
        )
        if (
            player.won
            or share_key not in by_key
            or not golds_known
            or not all(key in by_key for key in dead_keys)
        ):
            continue
        deficit = sum(
            (gold_by_id[opponents[mate.participant_id]] or 0)
            - (gold_by_id[mate.participant_id] or 0)
            for mate in teammates
        )
        seconds_dead = sum(_whole(by_key[key]) for key in dead_keys)
        share_value = by_key[share_key].value
        share_percent = round(float(share_value) * 100) if isinstance(share_value, float) else 0
        pid = player.participant_id
        keys = (
            f"teammates_gold_deficit_20/p{pid}",
            f"teammates_time_dead/p{pid}",
            f"damage_share_percent/p{pid}",
        )
        index_value = (
            deficit // GOLD_PER_INDEX_POINT + seconds_dead // SECONDS_PER_MINUTE + share_percent
        )
        exhibits.extend(
            [
                Exhibit(
                    key=keys[0],
                    label=f"How far {player.champion}'s teammates trailed at minute 20",
                    value=deficit,
                    display=format_count(deficit),
                    unit="gold",
                    source=ExhibitSource(
                        kind="computation",
                        formula="the sum, over each teammate with a lane opponent, of the "
                        f"opponent's totalGold minus the teammate's, at frames[{frame_index}]",
                    ),
                    participant_id=pid,
                ),
                Exhibit(
                    key=keys[1],
                    label=f"Time {player.champion}'s teammates spent dead, combined",
                    value=seconds_dead,
                    display=format_clock(seconds_dead),
                    unit="dead",
                    source=ExhibitSource(
                        kind="computation",
                        formula="the sum of the teammates' totalTimeSpentDead",
                        input_keys=tuple(dead_keys),
                    ),
                    participant_id=pid,
                ),
                Exhibit(
                    key=keys[2],
                    label=f"{player.champion}'s share of the team's damage, in percent",
                    value=share_percent,
                    display=f"{share_percent}%",
                    unit="of the team's damage",
                    source=ExhibitSource(
                        kind="computation",
                        formula="the damage share times one hundred, rounded",
                        input_keys=(share_key,),
                    ),
                    participant_id=pid,
                ),
                Exhibit(
                    key=f"carry_impossibility_index/p{pid}",
                    label=f"{player.champion}'s Carry Impossibility Index",
                    value=index_value,
                    display=format_count(index_value),
                    unit="points",
                    source=ExhibitSource(
                        kind="computation",
                        formula="made up by this overlay: the teammates' gold deficit at minute "
                        "20 in hundreds, plus their combined minutes dead, plus the damage share "
                        "in percent",
                        input_keys=keys,
                    ),
                    participant_id=pid,
                ),
            ]
        )
    return exhibits


def _whole(exhibit: Exhibit) -> int:
    """Return an exhibit's whole number.

    Args:
        exhibit: A count, read with `as_whole_number`.

    Returns:
        Its value.
    """
    return (
        exhibit.value
        if isinstance(exhibit.value, int) and not isinstance(exhibit.value, bool)
        else 0
    )
