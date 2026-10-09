"""The scoring harness: how far each estimator is from the truth, on a recorded game.

A recording holds the game's answers and the League client's around them, the game's details
among them, which say who played where. Each estimator is run on the recording as it ran live and
compared with what is known to be true:

- **Roles** (estimator 1): the scoreboard's positions are hidden from the estimator, which works
  them out again from the other signals; the truth is the position the game gave, or, in a queue
  that gives none, the one the game's details record.
- **Combat stats** (estimator 2): the game gives the exact stats of the player on this machine all
  game long, so the estimate made for them as for anyone else is compared with those, once a
  minute.
- **Gold** (estimator 3): the post-game timeline gives every player's earned and unspent gold
  each minute. The gold tracker runs through the recording as it ran live, your own exact gold
  tuning it, and its estimate at the start of each minute is compared with the timeline's for
  every player but you; the band is scored by how often it holds the truth.
- **Experience** (estimator 4): the same, against the timeline's experience, for every player:
  nobody's is exact.
- **Build path** (estimator 5): the next item predicted for each player at the end of each
  minute, from their components and class (their match history is not in the harness), against
  the first finished item the timeline shows them buy after it.
- **Positions** (estimator 7): each player's likely regions at the start of each minute, from the
  clues as they came live, against the region of the map nearest their timeline position: how
  often the likeliest was right, and the chance given to the true one on average.
- **Jungle path** (estimator 8): at each minute of the timeline, a jungler whose decoded camp was
  finished within 30 seconds before it should be near that camp; how far the timeline puts them
  from it, on average.
- **Control wards** (estimator 9): the timeline records each control ward placed; one seen
  within 10 seconds of it is matched, both ways. Where it was is not recorded, so only the moment
  is scored.
- **The map** (phase 4.1): every player's position each minute on the timeline should lie near a
  path of the hand-built map; how far it lies on average says how well the map was drawn.
- **Fights** (estimator 10): the timeline records every kill, with its killer, assisters and
  place. Kills each within 15 seconds of the last and 3000 units of the first make one fight; a
  fight of two kills or more is won by the team that lost fewer champions (an even trade is
  left out). The chance its players had, from the last answer before its first kill, is scored
  by its Brier score.
- **Objective contests** (estimator 11): the timeline records each epic monster's kill, the team
  that took it and where. For each of your team's takes of Dragon, the Elder or Baron, the chance
  given 20 seconds before it is scored against whether it was contested: a kill within 30 seconds
  before and 10 after it, within 3000 units of it, with one of the other team's champions in it.
  Its Brier score.
- **Win chance** (estimator 12): the game's details say which team won. The chance given at the
  start of each minute is scored by its Brier score, the mean squared distance from the result:
  0.25 for a coin flip every minute, 0 for a sure and right answer.
- **Backs** (estimator 6): the timeline records every purchase. One made alive (not within a
  minute of a death) past 1:30 starts a trip to base, and each purchase more than 30 seconds
  after a trip's first starts another; a trip the back tracker saw within 20 seconds of it is
  matched. Scored both ways: the timeline's trips seen, and the trips seen that it has.

The timeline's positions score the estimators still to come in the same way. Each score is
a number per game; the thresholds that CI holds them to are set from the first batch of recorded
games and never lowered to make a check pass.
"""

import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, JsonValue, ValidationError, field_validator

from leagueasymode.data_dragon import PatchStats
from leagueasymode.game_state import GameSnapshot, RiotPayloadModel
from leagueasymode.inference.backs import BackTracker
from leagueasymode.inference.build_path import next_item
from leagueasymode.inference.clues import ClueTracker
from leagueasymode.inference.combat_stats import DEFAULT_MOVE_SPEED, estimated_combat_stats
from leagueasymode.inference.contests import ContestedObjective, objective_contests
from leagueasymode.inference.experience import ExperienceTracker
from leagueasymode.inference.fights import FIGHT_RULES, fighter_of, strength_log_ratio
from leagueasymode.inference.fitting import logistic
from leagueasymode.inference.gold import GoldTracker, PlayerKey, player_key, team_gold_of
from leagueasymode.inference.jungle_path import JunglePathTracker
from leagueasymode.inference.objectives import (
    buff_timers,
    dragon_timer,
    inhibitor_timers,
    objective_timers,
)
from leagueasymode.inference.positions import position_estimate
from leagueasymode.inference.rift_map import RIFT_MAP, RiftMap
from leagueasymode.inference.roles import assign_roles
from leagueasymode.inference.wards import WardTracker
from leagueasymode.inference.win_chance import WinFeatures, win_chance, win_features
from leagueasymode.overlay_state import (
    CombatStats,
    GoldEstimate,
    LevelEstimate,
    PositionClue,
    PositionEstimate,
)
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH, ITEMS_PATH, ItemCatalog
from leagueasymode.player_intel import champion_aliases, history_position
from leagueasymode.recording.file_format import ClientResource
from leagueasymode.recording.reader import iter_game_frames, iter_recording_lines

GAME_DETAILS_PATH_PREFIX: Final = "/lol-match-history/v1/games/"
TIMELINE_PATH_PREFIX: Final = "/lol-match-history/v1/game-timelines/"
MILLISECONDS_PER_SECOND: Final = 1000.0
# An estimate stands for a minute's timeline frame when it is this close after the frame's time.
FRAME_ALIGNMENT_SECONDS: Final = 2.0
ITEM_PURCHASED_EVENT: Final = "ITEM_PURCHASED"
CHAMPION_KILL_EVENT: Final = "CHAMPION_KILL"
# Purchases before this are the game's start; within this long after a death, the death's.
TRIPS_START_AT_SECONDS: Final = 90.0
DEATH_SHOPPING_SECONDS: Final = 60.0
# A purchase this long after a trip's first starts another trip.
SAME_TRIP_SECONDS: Final = 30.0
# A trip seen this close to one the timeline shows is the same trip.
TRIP_MATCH_SECONDS: Final = 20.0
# A jungler's decoded camp this recent before a frame of the timeline is where they should be.
RECENT_CAMP_SECONDS: Final = 30.0
WARD_PLACED_EVENT: Final = "WARD_PLACED"
CONTROL_WARD_TYPE: Final = "CONTROL_WARD"
# A placement seen this close to one the timeline records is the same.
WARD_MATCH_SECONDS: Final = 10.0
# Kills this close in time to the last of a fight, and in place to its first, belong to it.
FIGHT_GAP_SECONDS: Final = 15.0
FIGHT_RADIUS_UNITS: Final = 3000.0
FIGHT_SMALLEST_KILL_COUNT: Final = 2
ELITE_MONSTER_KILL_EVENT: Final = "ELITE_MONSTER_KILL"
# A take is weighed from the last answer this long before it; a kill this close in time and place,
# with one of the other team's champions in it, is a contest.
CONTEST_LEAD_SECONDS: Final = 20.0
CONTEST_BEFORE_SECONDS: Final = 30.0
CONTEST_AFTER_SECONDS: Final = 10.0
CONTEST_RADIUS_UNITS: Final = 3000.0
ELDER_SUB_TYPE: Final = "ELDER_DRAGON"
SECONDS_PER_MINUTE: Final = 60
TEAM_BY_ID: Final = {100: "ORDER", 200: "CHAOS"}
PERCENT: Final = 100.0
# The stats compared with the game's exact ones; ability power is left out, zero without items.
SCORED_STATS: Final[tuple[Callable[[CombatStats], float], ...]] = (
    lambda stats: stats.health,
    lambda stats: stats.armor,
    lambda stats: stats.magic_resist,
    lambda stats: stats.attack_damage,
    lambda stats: stats.attack_speed,
    lambda stats: stats.move_speed,
)


# Every estimator the harness scores, by the name its score carries.
ESTIMATOR_NAMES: Final = frozenset(
    {
        "roles",
        "combat stats (yours)",
        "gold earned",
        "gold unspent",
        "gold band",
        "experience",
        "experience band",
        "next item",
        "backs (of the timeline's)",
        "backs (of those seen)",
        "positions (likeliest region)",
        "positions (chance on the truth)",
        "jungle path",
        "control wards (of the timeline's)",
        "control wards (of those seen)",
        "map",
        "fights",
        "objective contests",
        "win chance",
    }
)
# Whether a higher or a lower value of each measure is better.
MEASURE_DIRECTION: Final[Mapping[str, Literal["higher", "lower"]]] = {
    "share_correct": "higher",
    "share_within_band": "higher",
    "share_matched": "higher",
    "mean_chance": "higher",
    "mean_absolute_percent_error": "lower",
    "mean_absolute_error_gold": "lower",
    "mean_absolute_error_experience": "lower",
    "mean_distance_units": "lower",
    "brier_score": "lower",
    "fight_brier_score": "lower",
    "contest_brier_score": "lower",
}
# How each measure reads, in one line.
SCORE_DESCRIPTIONS: Final = {
    "share_correct": "{estimator}: {hit_count}/{sample_count} correct ({percent:.0f}%)",
    "share_within_band": (
        "{estimator}: holds the truth {hit_count}/{sample_count} times ({percent:.0f}%)"
    ),
    "share_matched": "{estimator}: {hit_count}/{sample_count} matched ({percent:.0f}%)",
    "mean_absolute_percent_error": (
        "{estimator}: {sample_count} moments, {value:.1f}% off on average"
    ),
    "mean_absolute_error_gold": (
        "{estimator}: {sample_count} player-minutes, {value:.0f} gold off on average"
    ),
    "mean_absolute_error_experience": (
        "{estimator}: {sample_count} player-minutes, {value:.0f} experience off on average"
    ),
    "mean_chance": (
        "{estimator}: {sample_count} player-minutes, {percent:.0f}% on the truth on average"
    ),
    "mean_distance_units": (
        "{estimator}: {sample_count} positions, {value:.0f} units off on average"
    ),
    "brier_score": (
        "{estimator}: {sample_count} minutes, Brier score {value:.3f} (a coin flip scores 0.250)"
    ),
    "fight_brier_score": (
        "{estimator}: {sample_count} fights, Brier score {value:.3f} (a coin flip scores 0.250)"
    ),
    "contest_brier_score": (
        "{estimator}: {sample_count} takes, Brier score {value:.3f} (a coin flip scores 0.250)"
    ),
}


@dataclass(frozen=True)
class EstimatorScore:
    """How far one estimator is from the truth on one game."""

    estimator: str
    sample_count: int
    # A share from 0 to 1 for "share_correct" and "share_within_band"; a percentage for
    # "mean_absolute_percent_error"; gold or experience for the mean absolute errors.
    value: float
    measure: Literal[
        "share_correct",
        "mean_absolute_percent_error",
        "mean_absolute_error_gold",
        "mean_absolute_error_experience",
        "share_within_band",
        "share_matched",
        "mean_distance_units",
        "mean_chance",
        "brier_score",
        "fight_brier_score",
        "contest_brier_score",
    ]

    def describe(self) -> str:
        """Return the score in one line, as `leagueasymode score` prints it.

        Returns:
            Such as "roles: 9/10 correct (90%)".
        """
        return SCORE_DESCRIPTIONS[self.measure].format(
            estimator=self.estimator,
            hit_count=round(self.value * self.sample_count),
            sample_count=self.sample_count,
            percent=self.value * PERCENT,
            value=self.value,
        )


@dataclass(frozen=True)
class RecordedGame:
    """What the harness reads from a recording."""

    # The last answer of the game in each minute of game time, in order.
    minute_snapshots: tuple[GameSnapshot, ...]
    # The League client's latest answer for each path it was asked.
    client_resources: Mapping[str, JsonValue]
    # The gold tracker's estimates at the first answer of each minute of game time, by minute.
    minute_gold_estimates: Mapping[int, Mapping[PlayerKey, GoldEstimate]]
    # The experience tracker's, the same way.
    minute_level_estimates: Mapping[int, Mapping[PlayerKey, LevelEstimate]]
    # When the back tracker saw each player shop on a trip to base, in game seconds.
    trips_seen: Mapping[PlayerKey, tuple[float, ...]]
    # Where each player likely was at the first answer of each minute, by minute.
    minute_position_estimates: Mapping[int, Mapping[PlayerKey, PositionEstimate]]
    # Each jungler's last decoded camp and when they finished it, at each minute's start.
    minute_jungle_camps: Mapping[int, Mapping[PlayerKey, tuple[str, float]]]
    # When the ward tracker saw each player place a control ward, in game seconds.
    control_wards_seen: Mapping[PlayerKey, tuple[float, ...]]
    # What the win chance read at the first answer of each minute, by minute.
    minute_win_features: Mapping[int, WinFeatures]
    # The last answer before each of the timeline's fights, by the game time of its first kill.
    fight_snapshots: Mapping[float, GameSnapshot]
    # The last answer 20 seconds or more before each epic monster's kill, with every player's
    # clues to where they were then, by the game time of the kill.
    contest_moments: Mapping[float, tuple[GameSnapshot, Mapping[PlayerKey, list[PositionClue]]]]


class DetailsTimeline(RiotPayloadModel):
    """Where a participant played, as the game's details record it."""

    lane: str = ""
    role: str = ""


class DetailsParticipant(RiotPayloadModel):
    """One participant of the game's details."""

    participant_id: int = Field(default=0, alias="participantId")
    champion_id: int = Field(default=0, alias="championId")
    team_id: int = Field(default=0, alias="teamId")
    team_position: str = Field(default="", alias="teamPosition")
    timeline: DetailsTimeline = Field(default_factory=DetailsTimeline)


class DetailsTeam(RiotPayloadModel):
    """One team of the game's details, and whether it won."""

    team_id: int = Field(default=0, alias="teamId")
    # "Win" or "Fail".
    win: str = ""


class GameDetails(RiotPayloadModel):
    """The game's details from the League client, after the game."""

    participants: list[DetailsParticipant] = Field(default_factory=list)
    teams: list[DetailsTeam] = Field(default_factory=list)


class TimelinePosition(RiotPayloadModel):
    """A place on the map, in game units."""

    x: int = 0  # ai-kit: ignore-name  the timeline's own name for the coordinate
    y: int = 0  # ai-kit: ignore-name  as above


class TimelineParticipantFrame(RiotPayloadModel):
    """One participant's gold, experience and position at one frame of the match timeline."""

    participant_id: int = Field(default=0, alias="participantId")
    position: TimelinePosition | None = None
    current_gold: int = Field(default=0, alias="currentGold")
    total_gold: int = Field(default=0, alias="totalGold")
    experience: int = Field(default=0, alias="xp")


class TimelineEvent(RiotPayloadModel):
    """One event of the match timeline: a purchase or a kill, among others."""

    event_type: str = Field(default="", alias="type")
    timestamp_milliseconds: int = Field(default=0, alias="timestamp")
    # The buyer of a purchase, and what they bought.
    participant_id: int = Field(default=0, alias="participantId")
    item_id: int = Field(default=0, alias="itemId")
    # The champion a kill killed, who killed them (0 for a turret or a monster), who helped,
    # and where.
    victim_id: int = Field(default=0, alias="victimId")
    killer_id: int = Field(default=0, alias="killerId")
    assisting_participant_ids: list[int] = Field(
        default_factory=list, alias="assistingParticipantIds"
    )
    position: TimelinePosition | None = None
    # The placer of a ward, and its kind.
    creator_id: int = Field(default=0, alias="creatorId")
    ward_type: str = Field(default="", alias="wardType")
    # An epic monster's kill: the team that took it, and the monster.
    killer_team_id: int = Field(default=0, alias="killerTeamId")
    monster_type: str = Field(default="", alias="monsterType")
    monster_sub_type: str = Field(default="", alias="monsterSubType")


@dataclass(frozen=True)
class MonsterTake:
    """An epic monster's kill on the timeline: when, which, by which team, and where."""

    seconds: float
    objective: ContestedObjective
    team_id: int
    position: TimelinePosition | None


@dataclass(frozen=True)
class TimelineFight:
    """Kills close in time and place: who took part, and who died."""

    start_seconds: float
    participant_ids: frozenset[int]
    victim_ids: tuple[int, ...]


class TimelineFrame(RiotPayloadModel):
    """One frame of the match timeline: every participant, about once a minute."""

    timestamp_milliseconds: int = Field(default=0, alias="timestamp")
    participant_frames: list[TimelineParticipantFrame] = Field(
        default_factory=list, alias="participantFrames"
    )
    events: list[TimelineEvent] = Field(default_factory=list)

    @field_validator("participant_frames", mode="before")
    @classmethod
    def _frames_as_a_list(cls, value: object) -> object:
        """Take the participants' frames keyed by participant id, as the timeline sends them.

        Args:
            value: The frames, keyed by id or listed.

        Returns:
            The frames, listed.
        """
        return list(value.values()) if isinstance(value, dict) else value


class GameTimeline(RiotPayloadModel):
    """The match timeline from the League client, after the game."""

    frames: list[TimelineFrame] = Field(default_factory=list)


def read_recorded_game(recording_path: Path) -> RecordedGame:
    """Read what the harness needs from a recording, running the trackers through it.

    Args:
        recording_path: The recording.

    Returns:
        The game's snapshot at the end of each minute, the client's answers, and the gold and
        experience trackers' estimates at the start of each minute.
    """
    client_resources = {
        record.path: record.payload
        for record in iter_recording_lines(recording_path)
        if isinstance(record, ClientResource)
    }
    items_payload = client_resources.get(ITEMS_PATH)
    item_catalog = ItemCatalog.from_client_items(items_payload) if items_payload else None
    gold_tracker = GoldTracker()
    experience_tracker = ExperienceTracker()
    back_tracker = BackTracker()
    clue_tracker = ClueTracker()
    jungle_tracker = JunglePathTracker()
    ward_tracker = WardTracker()
    jungle_camps_by_minute: dict[int, Mapping[PlayerKey, tuple[str, float]]] = {}
    trips_by_player: dict[PlayerKey, list[float]] = {}
    position_estimates_by_minute: dict[int, Mapping[PlayerKey, PositionEstimate]] = {}
    snapshot_by_minute: dict[int, GameSnapshot] = {}
    gold_estimates_by_minute: dict[int, Mapping[PlayerKey, GoldEstimate]] = {}
    level_estimates_by_minute: dict[int, Mapping[PlayerKey, LevelEstimate]] = {}
    win_features_by_minute: dict[int, WinFeatures] = {}
    timeline = _timeline_in(client_resources)
    fight_starts = [fight.start_seconds for fight in timeline_fights(timeline)] if timeline else []
    fight_snapshots: dict[float, GameSnapshot] = {}
    take_times = [take.seconds for take in monster_takes(timeline)] if timeline else []
    contest_moments: dict[float, tuple[GameSnapshot, Mapping[PlayerKey, list[PositionClue]]]] = {}
    for frame in iter_game_frames(recording_path):
        try:
            snapshot = GameSnapshot.model_validate(frame.payload)
        except ValidationError:
            continue
        game_time_seconds = snapshot.game_data.game_time_seconds
        game_minute = int(game_time_seconds // SECONDS_PER_MINUTE)
        snapshot_by_minute[game_minute] = snapshot
        for fight_start in fight_starts:
            if game_time_seconds < fight_start:
                fight_snapshots[fight_start] = snapshot
        gold_estimates = gold_tracker.update(snapshot, item_catalog)
        level_estimates = experience_tracker.update(snapshot)
        last_backs = back_tracker.update(snapshot, item_catalog)
        for key, last_back in last_backs.items():
            player_trips = trips_by_player.setdefault(key, [])
            if last_back.shopped_at_game_time_seconds not in player_trips:
                player_trips.append(last_back.shopped_at_game_time_seconds)
        position_clues = clue_tracker.update(snapshot, last_backs)
        for take_time in take_times:
            if game_time_seconds <= take_time - CONTEST_LEAD_SECONDS:
                contest_moments[take_time] = (snapshot, position_clues)
        jungle_tracker.update(snapshot)
        ward_tracker.update(snapshot, {})
        is_minute_start = game_time_seconds - game_minute * SECONDS_PER_MINUTE <= (
            FRAME_ALIGNMENT_SECONDS
        )
        if is_minute_start and game_minute not in gold_estimates_by_minute:
            gold_estimates_by_minute[game_minute] = gold_estimates
            level_estimates_by_minute[game_minute] = level_estimates
            position_estimates_by_minute[game_minute] = _position_estimates(
                snapshot, position_clues
            )
            jungle_camps_by_minute[game_minute] = jungle_tracker.last_clears()
            win_features_by_minute[game_minute] = win_features(
                snapshot,
                team_gold=team_gold_of(snapshot, gold_estimates),
                team_item_gold=None,
                dragon=dragon_timer(snapshot),
                buffs=buff_timers(snapshot),
                inhibitors=inhibitor_timers(snapshot),
            )
    return RecordedGame(
        minute_snapshots=tuple(snapshot_by_minute[minute] for minute in sorted(snapshot_by_minute)),
        client_resources=client_resources,
        minute_gold_estimates=gold_estimates_by_minute,
        minute_level_estimates=level_estimates_by_minute,
        trips_seen={key: tuple(trips) for key, trips in trips_by_player.items()},
        minute_position_estimates=position_estimates_by_minute,
        minute_jungle_camps=jungle_camps_by_minute,
        control_wards_seen=ward_tracker.placements(),
        minute_win_features=win_features_by_minute,
        fight_snapshots=fight_snapshots,
        contest_moments=contest_moments,
    )


def score_roles(game: RecordedGame) -> EstimatorScore | None:
    """Score the role estimator on the game's last snapshot, with the positions hidden from it.

    Args:
        game: The recorded game.

    Returns:
        The share of players whose role it found, or None when no player's role is known.
    """
    if not game.minute_snapshots:
        return None
    last_snapshot = game.minute_snapshots[-1]
    details_positions = _details_positions(game)
    true_positions = [
        player.position or details_positions.get((player.team, player.champion_alias().lower()), "")
        for player in last_snapshot.players
    ]
    hidden_snapshot = last_snapshot.model_copy(
        update={
            "players": [
                player.model_copy(update={"position": ""}) for player in last_snapshot.players
            ]
        }
    )
    estimated_roles = [guess.role for guess in assign_roles(hidden_snapshot)]
    scored_pairs = [
        (true_position, estimated_role)
        for true_position, estimated_role in zip(true_positions, estimated_roles, strict=True)
        if true_position
    ]
    if not scored_pairs:
        return None
    correct_count = sum(
        1 for true_position, estimated in scored_pairs if true_position == estimated
    )
    return EstimatorScore(
        estimator="roles",
        sample_count=len(scored_pairs),
        value=correct_count / len(scored_pairs),
        measure="share_correct",
    )


def score_combat_stats(game: RecordedGame, patch_stats: PatchStats | None) -> EstimatorScore | None:
    """Score the combat stats estimate on the player on this machine, against the game's own.

    Args:
        game: The recorded game.
        patch_stats: The patch's stats; None when they cannot be had.

    Returns:
        The mean absolute error in percent, over each minute and each stat, or None when nothing
        could be compared.
    """
    if patch_stats is None:
        return None
    percent_errors: list[float] = []
    scored_moment_count = 0
    for snapshot in game.minute_snapshots:
        active_player = snapshot.active_player
        own_player = next(
            (player for player in snapshot.players if snapshot.is_active_player(player)), None
        )
        if active_player is None or active_player.champion_stats is None or own_player is None:
            continue
        estimate = estimated_combat_stats(own_player, patch_stats)
        if estimate is None:
            continue
        exact = active_player.champion_stats
        exact_values = (
            exact.max_health,
            exact.armor,
            exact.magic_resist,
            exact.attack_damage,
            exact.attack_speed,
            exact.move_speed,
        )
        scored_moment_count += 1
        percent_errors.extend(
            abs(stat_of(estimate) - exact_value) / exact_value * PERCENT
            for stat_of, exact_value in zip(SCORED_STATS, exact_values, strict=True)
            if exact_value > 0
        )
    if not percent_errors:
        return None
    return EstimatorScore(
        estimator="combat stats (yours)",
        sample_count=scored_moment_count,
        value=sum(percent_errors) / len(percent_errors),
        measure="mean_absolute_percent_error",
    )


def score_gold(game: RecordedGame) -> list[EstimatorScore]:
    """Score the gold estimates of every player but you against the match timeline.

    Args:
        game: The recorded game.

    Returns:
        How far the earned and the unspent gold are off on average, and how often the band holds
        the earned gold; nothing without a timeline, the game's details, or an estimate to score.
    """
    scored_pairs = [
        (estimate, truth)
        for estimate, truth in _timeline_pairs(game, game.minute_gold_estimates)
        if estimate.source == "estimate"
    ]
    if not scored_pairs:
        return []
    pair_count = len(scored_pairs)
    return [
        EstimatorScore(
            estimator="gold earned",
            sample_count=pair_count,
            value=sum(
                abs(estimate.total_gold - truth.total_gold) for estimate, truth in scored_pairs
            )
            / pair_count,
            measure="mean_absolute_error_gold",
        ),
        EstimatorScore(
            estimator="gold unspent",
            sample_count=pair_count,
            value=sum(
                abs(estimate.unspent_gold - truth.current_gold) for estimate, truth in scored_pairs
            )
            / pair_count,
            measure="mean_absolute_error_gold",
        ),
        EstimatorScore(
            estimator="gold band",
            sample_count=pair_count,
            value=sum(
                1
                for estimate, truth in scored_pairs
                if abs(estimate.total_gold - truth.total_gold) <= estimate.band_gold
            )
            / pair_count,
            measure="share_within_band",
        ),
    ]


def score_experience(game: RecordedGame) -> list[EstimatorScore]:
    """Score the experience estimates of every player against the match timeline.

    Args:
        game: The recorded game.

    Returns:
        How far the experience is off on average, and how often the band holds it; nothing
        without a timeline, the game's details, or an estimate to score.
    """
    scored_pairs = list(_timeline_pairs(game, game.minute_level_estimates))
    if not scored_pairs:
        return []
    pair_count = len(scored_pairs)
    return [
        EstimatorScore(
            estimator="experience",
            sample_count=pair_count,
            value=sum(
                abs(estimate.experience - truth.experience) for estimate, truth in scored_pairs
            )
            / pair_count,
            measure="mean_absolute_error_experience",
        ),
        EstimatorScore(
            estimator="experience band",
            sample_count=pair_count,
            value=sum(
                1
                for estimate, truth in scored_pairs
                if abs(estimate.experience - truth.experience) <= estimate.band_experience
            )
            / pair_count,
            measure="share_within_band",
        ),
    ]


def score_next_items(game: RecordedGame, patch_stats: PatchStats | None) -> EstimatorScore | None:
    """Score the next item predicted for each player against the next one they bought.

    Args:
        game: The recorded game.
        patch_stats: The patch's stats, for the champions' classes; None when they cannot be had.

    Returns:
        The share of predictions that named the next finished item bought; None without a
        timeline, the game's details, the item catalog, or a purchase to score.
    """
    timeline = _game_timeline(game)
    items_payload = game.client_resources.get(ITEMS_PATH)
    item_catalog = ItemCatalog.from_client_items(items_payload) if items_payload else None
    if timeline is None or item_catalog is None:
        return None
    scored_pairs = list(_next_item_pairs(game, timeline, item_catalog, patch_stats))
    if not scored_pairs:
        return None
    return EstimatorScore(
        estimator="next item",
        sample_count=len(scored_pairs),
        value=sum(1 for predicted, bought in scored_pairs if predicted == bought)
        / len(scored_pairs),
        measure="share_correct",
    )


def score_positions(game: RecordedGame) -> list[EstimatorScore]:
    """Score where each player was estimated to be against their timeline position.

    Args:
        game: The recorded game.

    Returns:
        How often the likeliest region was the true one, and the chance given to the true one on
        average; nothing without positions to score.
    """
    scored_pairs = [
        (estimate, RIFT_MAP.nearest_point(truth.position.x, truth.position.y).region)
        for estimate, truth in _timeline_pairs(game, game.minute_position_estimates)
        if truth.position is not None
    ]
    if not scored_pairs:
        return []
    pair_count = len(scored_pairs)
    return [
        EstimatorScore(
            estimator="positions (likeliest region)",
            sample_count=pair_count,
            value=sum(
                1
                for estimate, true_region in scored_pairs
                if estimate.regions and estimate.regions[0].region == true_region
            )
            / pair_count,
            measure="share_correct",
        ),
        EstimatorScore(
            estimator="positions (chance on the truth)",
            sample_count=pair_count,
            value=sum(
                next(
                    (chance.chance for chance in estimate.regions if chance.region == true_region),
                    0.0,
                )
                for estimate, true_region in scored_pairs
            )
            / pair_count,
            measure="mean_chance",
        ),
    ]


def score_jungle_path(game: RecordedGame) -> EstimatorScore | None:
    """Score each jungler's decoded camps by how far the timeline puts them from each.

    Args:
        game: The recorded game.

    Returns:
        The mean distance, over the minutes whose start came within 30 seconds of a decoded
        camp; None without such a minute.
    """
    distances = [
        math.hypot(
            truth.position.x - RIFT_MAP.points[camp].x_position,
            truth.position.y - RIFT_MAP.points[camp].y_position,
        )
        for game_minute, camp_and_time, truth in _timeline_items(game, game.minute_jungle_camps)
        if truth.position is not None
        for camp, cleared_at_seconds in [camp_and_time]
        if game_minute * SECONDS_PER_MINUTE - cleared_at_seconds <= RECENT_CAMP_SECONDS
    ]
    if not distances:
        return None
    return EstimatorScore(
        estimator="jungle path",
        sample_count=len(distances),
        value=sum(distances) / len(distances),
        measure="mean_distance_units",
    )


def score_control_wards(game: RecordedGame) -> list[EstimatorScore]:
    """Score the control wards seen placed against those the timeline records.

    Args:
        game: The recorded game.

    Returns:
        The share of the timeline's placements seen, and of those seen that it has; nothing
        without a timeline, the game's details, or a placement to score.
    """
    timeline = _game_timeline(game)
    if timeline is None:
        return []
    events = [event for frame in timeline.frames for event in frame.events]
    timeline_placements = {
        key: tuple(
            event.timestamp_milliseconds / MILLISECONDS_PER_SECOND
            for event in events
            if event.event_type == WARD_PLACED_EVENT
            and event.ward_type == CONTROL_WARD_TYPE
            and event.creator_id == participant.participant_id
        )
        for key, participant in _details_participants(game)
    }
    true_placements = [
        (key, placed_at) for key, times in timeline_placements.items() for placed_at in times
    ]
    seen_placements = [
        (key, placed_at) for key, times in game.control_wards_seen.items() for placed_at in times
    ]
    if not true_placements or not seen_placements:
        return []
    return [
        EstimatorScore(
            estimator="control wards (of the timeline's)",
            sample_count=len(true_placements),
            value=sum(
                1
                for key, placed_at in true_placements
                if _is_within(placed_at, game.control_wards_seen.get(key, ()), WARD_MATCH_SECONDS)
            )
            / len(true_placements),
            measure="share_matched",
        ),
        EstimatorScore(
            estimator="control wards (of those seen)",
            sample_count=len(seen_placements),
            value=sum(
                1
                for key, placed_at in seen_placements
                if _is_within(placed_at, timeline_placements.get(key, ()), WARD_MATCH_SECONDS)
            )
            / len(seen_placements),
            measure="share_matched",
        ),
    ]


def score_map(game: RecordedGame, rift_map: RiftMap = RIFT_MAP) -> EstimatorScore | None:
    """Score the map by how far the timeline's positions lie from its paths.

    Args:
        game: The recorded game.
        rift_map: The map.

    Returns:
        The mean distance from each position to the nearest path; None without positions.
    """
    timeline = _game_timeline(game)
    positions = (
        [
            (truth.position.x, truth.position.y)
            for frame in timeline.frames
            for truth in frame.participant_frames
            if truth.position is not None
        ]
        if timeline is not None
        else []
    )
    if not positions:
        return None
    segments = [
        (rift_map.points[name], rift_map.points[neighbour])
        for name in rift_map.points
        for neighbour, _ in rift_map.neighbours(name)
        if name < neighbour
    ]
    return EstimatorScore(
        estimator="map",
        sample_count=len(positions),
        value=sum(
            min(
                _distance_to_segment(
                    x_position,
                    y_position,
                    (start.x_position, start.y_position),
                    (end.x_position, end.y_position),
                )
                for start, end in segments
            )
            for x_position, y_position in positions
        )
        / len(positions),
        measure="mean_distance_units",
    )


def score_backs(game: RecordedGame) -> list[EstimatorScore]:
    """Score the trips to base seen against the purchases the match timeline records.

    Args:
        game: The recorded game.

    Returns:
        The share of the timeline's trips seen, and of the trips seen that it has; nothing
        without a timeline, the game's details, or a trip to score.
    """
    timeline = _game_timeline(game)
    if timeline is None:
        return []
    timeline_trips = {
        key: _timeline_trips(timeline, participant.participant_id)
        for key, participant in _details_participants(game)
    }
    true_trips = [(key, trip) for key, trips in timeline_trips.items() for trip in trips]
    trips_seen = [(key, trip) for key, trips in game.trips_seen.items() for trip in trips]
    if not true_trips or not trips_seen:
        return []
    return [
        EstimatorScore(
            estimator="backs (of the timeline's)",
            sample_count=len(true_trips),
            value=sum(1 for key, trip in true_trips if _is_near(trip, game.trips_seen.get(key, ())))
            / len(true_trips),
            measure="share_matched",
        ),
        EstimatorScore(
            estimator="backs (of those seen)",
            sample_count=len(trips_seen),
            value=sum(1 for key, trip in trips_seen if _is_near(trip, timeline_trips.get(key, ())))
            / len(trips_seen),
            measure="share_matched",
        ),
    ]


def score_fights(game: RecordedGame, patch_stats: PatchStats | None) -> EstimatorScore | None:
    """Score the chance each fight's players had against which team won it.

    Args:
        game: The recorded game.
        patch_stats: The patch's stats, for everyone's combat stats but yours.

    Returns:
        The Brier score; None when the recording has no fight that can be scored.
    """
    samples = fight_samples(game, patch_stats)
    squared_errors = [
        (logistic(FIGHT_RULES.steepness * log_ratio) - result) ** 2 for log_ratio, result in samples
    ]
    if not squared_errors:
        return None
    return EstimatorScore(
        estimator="fights",
        sample_count=len(squared_errors),
        value=sum(squared_errors) / len(squared_errors),
        measure="fight_brier_score",
    )


def score_contests(game: RecordedGame, patch_stats: PatchStats | None) -> EstimatorScore | None:
    """Score the chance of a contest given before each of your team's takes against the truth.

    Args:
        game: The recorded game.
        patch_stats: The patch's stats, for the time your team takes.

    Returns:
        The Brier score; None when the recording has no take that can be scored.
    """
    timeline = _game_timeline(game)
    team_by_id = {
        participant.participant_id: key[0] for key, participant in _details_participants(game)
    }
    if timeline is None or patch_stats is None or not team_by_id:
        return None
    squared_errors = [
        (chance - (1.0 if _was_contested(take, timeline, team_by_id) else 0.0)) ** 2
        for take in monster_takes(timeline)
        if take.seconds in game.contest_moments
        for chance in _contest_chance_before(take, game.contest_moments[take.seconds], patch_stats)
    ]
    if not squared_errors:
        return None
    return EstimatorScore(
        estimator="objective contests",
        sample_count=len(squared_errors),
        value=sum(squared_errors) / len(squared_errors),
        measure="contest_brier_score",
    )


def monster_takes(timeline: GameTimeline) -> list[MonsterTake]:
    """Return the timeline's kills of Dragon, the Elder Dragon and Baron.

    Args:
        timeline: The match timeline.

    Returns:
        The takes, oldest first.
    """
    return sorted(
        (
            MonsterTake(
                seconds=event.timestamp_milliseconds / MILLISECONDS_PER_SECOND,
                objective=objective,
                team_id=event.killer_team_id,
                position=event.position,
            )
            for frame in timeline.frames
            for event in frame.events
            if event.event_type == ELITE_MONSTER_KILL_EVENT
            for objective in _contested_objective(event)
        ),
        key=lambda take: take.seconds,
    )


def fight_samples(game: RecordedGame, patch_stats: PatchStats | None) -> list[tuple[float, float]]:
    """Return each fight of the timeline the fight model can weigh, as the refit takes them.

    Args:
        game: The recorded game.
        patch_stats: The patch's stats, for everyone's combat stats but yours.

    Returns:
        Each fight's logarithm of your side's strength over theirs, and its result (1 when your
        team lost fewer); none without a timeline or the patch's stats.
    """
    timeline = _game_timeline(game)
    if timeline is None or patch_stats is None:
        return []
    team_by_id = {
        participant.participant_id: key[0] for key, participant in _details_participants(game)
    }
    key_by_id = {
        participant.participant_id: key for key, participant in _details_participants(game)
    }
    return [
        sample
        for fight in timeline_fights(timeline)
        if fight.start_seconds in game.fight_snapshots
        for sample in _fight_sample(
            fight, game.fight_snapshots[fight.start_seconds], team_by_id, key_by_id, patch_stats
        )
    ]


def win_samples(game: RecordedGame) -> list[tuple[WinFeatures, float]]:
    """Return what the win chance read at the start of each minute, with the game's result.

    Args:
        game: The recorded game.

    Returns:
        Each minute's features and the result (1 when your team won), in order; none when the
        recording has no result.
    """
    has_ally_won = ally_result(game)
    if has_ally_won is None:
        return []
    result = 1.0 if has_ally_won else 0.0
    return [(features, result) for _, features in sorted(game.minute_win_features.items())]


def timeline_gold_leads(game: RecordedGame) -> dict[int, float]:
    """Return your team's gold lead each minute, as the timeline has it.

    Args:
        game: The recorded game.

    Returns:
        Your team's gold earned less theirs, by minute; none without a timeline or details.
    """
    timeline = _game_timeline(game)
    team_by_id = {
        participant.participant_id: key[0] for key, participant in _details_participants(game)
    }
    if timeline is None or not team_by_id or not game.minute_snapshots:
        return {}
    ally_team = game.minute_snapshots[0].ally_team()
    return {
        round(frame.timestamp_milliseconds / MILLISECONDS_PER_SECOND / SECONDS_PER_MINUTE): float(
            sum(
                participant_frame.total_gold
                * (1 if team_by_id.get(participant_frame.participant_id) == ally_team else -1)
                for participant_frame in frame.participant_frames
                if participant_frame.participant_id in team_by_id
            )
        )
        for frame in timeline.frames
    }


def timeline_fights(timeline: GameTimeline) -> list[TimelineFight]:
    """Return the timeline's fights: kills close in time and place, two or more of them.

    Args:
        timeline: The match timeline.

    Returns:
        The fights, oldest first.
    """
    kills = sorted(
        (
            event
            for frame in timeline.frames
            for event in frame.events
            if event.event_type == CHAMPION_KILL_EVENT
        ),
        key=lambda event: event.timestamp_milliseconds,
    )
    clusters: list[list[TimelineEvent]] = []
    for event in kills:
        cluster = clusters[-1] if clusters else None
        if cluster is not None and _is_same_fight(cluster, event):
            cluster.append(event)
        else:
            clusters.append([event])
    return [
        TimelineFight(
            start_seconds=cluster[0].timestamp_milliseconds / MILLISECONDS_PER_SECOND,
            participant_ids=frozenset(
                participant_id
                for event in cluster
                for participant_id in [
                    event.killer_id,
                    event.victim_id,
                    *event.assisting_participant_ids,
                ]
                if participant_id > 0
            ),
            victim_ids=tuple(event.victim_id for event in cluster),
        )
        for cluster in clusters
        if len(cluster) >= FIGHT_SMALLEST_KILL_COUNT
    ]


def score_win_chance(game: RecordedGame) -> EstimatorScore | None:
    """Score the win chance at the start of each minute against the game's result.

    Args:
        game: The recorded game.

    Returns:
        The Brier score; None when the recording has no result or no minute.
    """
    samples = win_samples(game)
    if not samples:
        return None
    squared_errors = [
        (win_chance(features).ally_chance - result) ** 2 for features, result in samples
    ]
    return EstimatorScore(
        estimator="win chance",
        sample_count=len(squared_errors),
        value=sum(squared_errors) / len(squared_errors),
        measure="brier_score",
    )


def score_recording(recording_path: Path, patch_stats: PatchStats | None) -> list[EstimatorScore]:
    """Score every estimator the recording can score.

    Args:
        recording_path: The recording.
        patch_stats: The patch's stats; None when they cannot be had.

    Returns:
        The scores, in the plan's order of the estimators; one that cannot be scored is left out.
    """
    return score_game(read_recorded_game(recording_path), patch_stats)


def score_game(game: RecordedGame, patch_stats: PatchStats | None) -> list[EstimatorScore]:
    """Score every estimator a recorded game can score.

    Args:
        game: The recorded game.
        patch_stats: The patch's stats; None when they cannot be had.

    Returns:
        The scores, in the plan's order of the estimators; one that cannot be scored is left out.
    """
    return [
        *(
            score
            for score in (score_roles(game), score_combat_stats(game, patch_stats))
            if score is not None
        ),
        *score_gold(game),
        *score_experience(game),
        *(
            score
            for score in [
                score_next_items(game, patch_stats),
                score_fights(game, patch_stats),
                score_contests(game, patch_stats),
            ]
            if score is not None
        ),
        *score_backs(game),
        *score_positions(game),
        *score_control_wards(game),
        *(
            score
            for score in [score_jungle_path(game), score_map(game), score_win_chance(game)]
            if score is not None
        ),
    ]


def _timeline_items[Estimate](
    game: RecordedGame, estimates_by_minute: Mapping[int, Mapping[PlayerKey, Estimate]]
) -> Iterator[tuple[int, Estimate, TimelineParticipantFrame]]:
    """Yield each estimate of a player with the timeline's truth and the minute they share.

    Args:
        game: The recorded game.
        estimates_by_minute: A tracker's estimates at the start of each minute.

    Yields:
        The minute, the estimate and the truth.
    """
    key_by_participant_id = {
        participant.participant_id: key for key, participant in _details_participants(game)
    }
    timeline = _game_timeline(game)
    if timeline is None:
        return
    for frame in timeline.frames:
        frame_seconds = frame.timestamp_milliseconds / MILLISECONDS_PER_SECOND
        game_minute = round(frame_seconds / SECONDS_PER_MINUTE)
        is_aligned = (
            abs(frame_seconds - game_minute * SECONDS_PER_MINUTE) <= FRAME_ALIGNMENT_SECONDS
        )
        # At 0:00 everyone is in their fountain, which scores nothing.
        if game_minute == 0 or not is_aligned:
            continue
        estimates = estimates_by_minute.get(game_minute, {})
        for truth in frame.participant_frames:
            key = key_by_participant_id.get(truth.participant_id)
            estimate = estimates.get(key) if key is not None else None
            if estimate is not None:
                yield game_minute, estimate, truth


def _timeline_pairs[Estimate](
    game: RecordedGame, estimates_by_minute: Mapping[int, Mapping[PlayerKey, Estimate]]
) -> Iterator[tuple[Estimate, TimelineParticipantFrame]]:
    """Yield each estimate of a player with the timeline's truth for the same minute.

    Args:
        game: The recorded game.
        estimates_by_minute: A tracker's estimates at the start of each minute.

    Yields:
        The pairs.
    """
    for _, estimate, truth in _timeline_items(game, estimates_by_minute):
        yield estimate, truth


def _timeline_trips(timeline: GameTimeline, participant_id: int) -> tuple[float, ...]:
    """Return when a participant shopped on each trip to base, by the timeline's purchases.

    Args:
        timeline: The match timeline.
        participant_id: The participant.

    Returns:
        Each trip's first purchase, in game seconds.
    """
    events = [event for frame in timeline.frames for event in frame.events]
    death_seconds = [
        event.timestamp_milliseconds / MILLISECONDS_PER_SECOND
        for event in events
        if event.event_type == CHAMPION_KILL_EVENT and event.victim_id == participant_id
    ]
    purchase_seconds = sorted(
        event.timestamp_milliseconds / MILLISECONDS_PER_SECOND
        for event in events
        if event.event_type == ITEM_PURCHASED_EVENT and event.participant_id == participant_id
    )
    trip_seconds: list[float] = []
    for bought_at_seconds in purchase_seconds:
        is_death_shopping = any(
            0 <= bought_at_seconds - died_at_seconds <= DEATH_SHOPPING_SECONDS
            for died_at_seconds in death_seconds
        )
        is_same_trip = bool(trip_seconds) and (
            bought_at_seconds - trip_seconds[-1] <= SAME_TRIP_SECONDS
        )
        if (
            bought_at_seconds >= TRIPS_START_AT_SECONDS
            and not is_death_shopping
            and not is_same_trip
        ):
            trip_seconds.append(bought_at_seconds)
    return tuple(trip_seconds)


def _position_estimates(
    snapshot: GameSnapshot, position_clues: Mapping[PlayerKey, list[PositionClue]]
) -> dict[PlayerKey, PositionEstimate]:
    """Return where each living player likely is, as the overlay would have shown it.

    Move speeds are taken at the default, since the harness reads no patch stats.

    Args:
        snapshot: The game's state.
        position_clues: Each player's clues so far.

    Returns:
        The estimates by key; the dead are left out.
    """
    estimates = {
        player_key(player): position_estimate(
            player,
            role_guess.role,
            position_clues.get(player_key(player), []),
            move_speed=DEFAULT_MOVE_SPEED,
            game_time_seconds=snapshot.game_data.game_time_seconds,
            ally_team=snapshot.ally_team(),
        )
        for player, role_guess in zip(snapshot.players, assign_roles(snapshot), strict=True)
    }
    return {key: estimate for key, estimate in estimates.items() if estimate is not None}


def _next_item_pairs(
    game: RecordedGame,
    timeline: GameTimeline,
    item_catalog: ItemCatalog,
    patch_stats: PatchStats | None,
) -> Iterator[tuple[int, int]]:
    """Yield each player's predicted next item at each minute's end, with the one they bought.

    Args:
        game: The recorded game.
        timeline: Its match timeline.
        item_catalog: The patch's items.
        patch_stats: The patch's stats; None when they cannot be had.

    Yields:
        The predicted item's id and the bought one's, where both are known.
    """
    participant_id_by_key = {
        key: participant.participant_id for key, participant in _details_participants(game)
    }
    events = [event for frame in timeline.frames for event in frame.events]
    for snapshot in game.minute_snapshots:
        game_time_seconds = snapshot.game_data.game_time_seconds
        for player in snapshot.players:
            predicted = next_item(
                player, item_catalog, patch_stats, game_time_seconds=game_time_seconds
            )
            bought_item_id = _next_finished_purchase(
                events,
                participant_id_by_key.get(player_key(player), 0),
                game_time_seconds,
                {item.item_id for item in player.items},
                item_catalog,
            )
            if predicted is not None and bought_item_id is not None:
                yield predicted.item_id, bought_item_id


def _next_finished_purchase(
    events: list[TimelineEvent],
    participant_id: int,
    after_seconds: float,
    owned_item_ids: set[int],
    item_catalog: ItemCatalog,
) -> int | None:
    """Return the first finished item a participant bought after a moment, not owned then.

    Args:
        events: The timeline's events.
        participant_id: The participant; 0 when unknown.
        after_seconds: The moment.
        owned_item_ids: What they owned then.
        item_catalog: The patch's items.

    Returns:
        The item's id, or None when they bought none after it.
    """
    purchases = sorted(
        (event.timestamp_milliseconds / MILLISECONDS_PER_SECOND, event.item_id)
        for event in events
        if event.event_type == ITEM_PURCHASED_EVENT
        and participant_id
        and event.participant_id == participant_id
    )
    return next(
        (
            item_id
            for bought_at_seconds, item_id in purchases
            if bought_at_seconds > after_seconds
            and item_catalog.is_finished(item_id)
            and item_id not in owned_item_ids
        ),
        None,
    )


def _distance_to_segment(
    x_position: float,
    y_position: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Return how far a place lies from a straight path.

    Args:
        x_position: The place's x.
        y_position: Its y.
        start: The path's one end.
        end: Its other end.

    Returns:
        The distance to the path's nearest point, in game units.
    """
    start_x, start_y = start
    path_x = end[0] - start_x
    path_y = end[1] - start_y
    length_squared = path_x**2 + path_y**2
    along = (
        min(
            max(
                ((x_position - start_x) * path_x + (y_position - start_y) * path_y)
                / length_squared,
                0.0,
            ),
            1.0,
        )
        if length_squared > 0
        else 0.0
    )
    return math.hypot(
        x_position - (start_x + along * path_x), y_position - (start_y + along * path_y)
    )


def _is_within(
    moment_seconds: float, other_moments_seconds: tuple[float, ...], within_seconds: float
) -> bool:
    """Return whether one of other moments is close to a moment.

    Args:
        moment_seconds: The moment.
        other_moments_seconds: The others.
        within_seconds: How close counts.

    Returns:
        Whether one is within that of it.
    """
    return any(abs(moment_seconds - other) <= within_seconds for other in other_moments_seconds)


def _is_near(trip_seconds: float, other_trips_seconds: tuple[float, ...]) -> bool:
    """Return whether a trip has one of other trips close to it.

    Args:
        trip_seconds: When the trip's shopping began.
        other_trips_seconds: The other trips'.

    Returns:
        Whether one is within 20 seconds of it.
    """
    return any(abs(trip_seconds - other) <= TRIP_MATCH_SECONDS for other in other_trips_seconds)


def _contested_objective(event: TimelineEvent) -> list[ContestedObjective]:
    """Return the monster an epic monster's kill on the timeline took, when it is weighed.

    Args:
        event: The kill.

    Returns:
        The monster, alone; nothing for the Herald, the Voidgrubs or another.
    """
    if event.monster_type == "DRAGON":
        return ["elder_dragon" if event.monster_sub_type == ELDER_SUB_TYPE else "dragon"]
    if event.monster_type == "BARON_NASHOR":
        return ["baron"]
    return []


def _contest_chance_before(
    take: MonsterTake,
    moment: tuple[GameSnapshot, Mapping[PlayerKey, list[PositionClue]]],
    patch_stats: PatchStats,
) -> list[float]:
    """Return the chance of a contest the overlay gave before a take of the player's team.

    Args:
        take: The take.
        moment: The game's answer before it, and the clues then.
        patch_stats: The patch's stats.

    Returns:
        The chance, alone; nothing for the other team's take, or a monster not weighed then.
    """
    snapshot, position_clues = moment
    if TEAM_BY_ID.get(take.team_id) != snapshot.ally_team():
        return []
    contests = objective_contests(
        snapshot,
        dragon=dragon_timer(snapshot),
        objectives=objective_timers(snapshot),
        position_clues=position_clues,
        patch_stats=patch_stats,
    )
    return [contest.contest_chance for contest in contests if contest.objective == take.objective]


def _was_contested(
    take: MonsterTake, timeline: GameTimeline, team_by_id: Mapping[int, str]
) -> bool:
    """Return whether the other team fought at a monster as it was taken.

    Args:
        take: The take.
        timeline: The match timeline.
        team_by_id: Each participant's team.

    Returns:
        Whether a kill close in time and place had one of the other team's champions in it.
    """
    taking_team = TEAM_BY_ID.get(take.team_id)
    return any(
        any(
            team_by_id.get(participant_id) not in {None, taking_team}
            for participant_id in [
                event.killer_id,
                event.victim_id,
                *event.assisting_participant_ids,
            ]
        )
        for frame in timeline.frames
        for event in frame.events
        if event.event_type == CHAMPION_KILL_EVENT
        and -CONTEST_BEFORE_SECONDS
        <= event.timestamp_milliseconds / MILLISECONDS_PER_SECOND - take.seconds
        <= CONTEST_AFTER_SECONDS
        and _is_within_units(event.position, take.position, CONTEST_RADIUS_UNITS)
    )


def _is_within_units(
    place: TimelinePosition | None, other_place: TimelinePosition | None, units: float
) -> bool:
    """Return whether two places are close; a place not known is taken to be.

    Args:
        place: One place.
        other_place: The other.
        units: How close, in game units.

    Returns:
        Whether they are within that distance.
    """
    if place is None or other_place is None:
        return True
    return math.dist((place.x, place.y), (other_place.x, other_place.y)) <= units


def _is_same_fight(cluster: list[TimelineEvent], kill: TimelineEvent) -> bool:
    """Return whether a kill belongs to a fight: soon after its last kill, near its first.

    Args:
        cluster: The fight's kills so far, oldest first.
        kill: The next kill.

    Returns:
        Whether it belongs; a kill without a place belongs by time alone.
    """
    gap_seconds = (
        kill.timestamp_milliseconds - cluster[-1].timestamp_milliseconds
    ) / MILLISECONDS_PER_SECOND
    return gap_seconds <= FIGHT_GAP_SECONDS and _is_within_units(
        cluster[0].position, kill.position, FIGHT_RADIUS_UNITS
    )


def _fight_sample(
    fight: TimelineFight,
    snapshot: GameSnapshot,
    team_by_id: Mapping[int, str],
    key_by_id: Mapping[int, PlayerKey],
    patch_stats: PatchStats,
) -> list[tuple[float, float]]:
    """Return what the fight model read of a fight's players, and the result; nothing for a trade.

    Args:
        fight: The fight.
        snapshot: The game's last answer before it.
        team_by_id: Each participant's team.
        key_by_id: Each participant's key.
        patch_stats: The patch's stats.

    Returns:
        The logarithm of your side's strength over theirs and the result, alone; nothing when
        the teams lost as many, or a fighter is unknown.
    """
    ally_team = snapshot.ally_team()
    ally_deaths = sum(1 for victim_id in fight.victim_ids if team_by_id.get(victim_id) == ally_team)
    enemy_deaths = len(fight.victim_ids) - ally_deaths
    player_by_key = {player_key(player): player for player in snapshot.players}
    fighters = [
        (
            team_by_id.get(participant_id) == ally_team,
            fighter_of(snapshot, player_by_key[key_by_id[participant_id]], patch_stats),
        )
        for participant_id in sorted(fight.participant_ids)
        if key_by_id.get(participant_id) in player_by_key
    ]
    known = [(is_ally, fighter) for is_ally, fighter in fighters if fighter is not None]
    log_ratio = strength_log_ratio(
        [fighter for is_ally, fighter in known if is_ally],
        [fighter for is_ally, fighter in known if not is_ally],
    )
    if ally_deaths == enemy_deaths or log_ratio is None or len(known) != len(fight.participant_ids):
        return []
    return [(log_ratio, 1.0 if enemy_deaths > ally_deaths else 0.0)]


def _game_timeline(game: RecordedGame) -> GameTimeline | None:
    """Return the match timeline the recording holds.

    Args:
        game: The recorded game.

    Returns:
        The timeline, or None when the recording has none it can read.
    """
    return _timeline_in(game.client_resources)


def _timeline_in(client_resources: Mapping[str, JsonValue]) -> GameTimeline | None:
    """Return the match timeline among the League client's answers.

    Args:
        client_resources: The client's latest answer for each path it was asked.

    Returns:
        The timeline, or None when there is none that can be read.
    """
    timeline_payload = next(
        (
            payload
            for path, payload in client_resources.items()
            if path.startswith(TIMELINE_PATH_PREFIX)
        ),
        None,
    )
    try:
        return GameTimeline.model_validate(timeline_payload)
    except ValidationError:
        return None


def _game_details(game: RecordedGame) -> GameDetails | None:
    """Return the game's details the recording holds.

    Args:
        game: The recorded game.

    Returns:
        The details, or None when the recording has none it can read.
    """
    details_payload = next(
        (
            payload
            for path, payload in game.client_resources.items()
            if path.startswith(GAME_DETAILS_PATH_PREFIX)
        ),
        None,
    )
    try:
        return GameDetails.model_validate(details_payload)
    except ValidationError:
        return None


def ally_result(game: RecordedGame) -> bool | None:
    """Return whether the team of the player on this machine won, from the game's details.

    Args:
        game: The recorded game.

    Returns:
        Whether it won; None when the recording does not say.
    """
    details = _game_details(game)
    if details is None or not game.minute_snapshots:
        return None
    ally_team = game.minute_snapshots[0].ally_team()
    ally_team_result = next(
        (team.win for team in details.teams if TEAM_BY_ID.get(team.team_id) == ally_team), None
    )
    return {"Win": True, "Fail": False}.get(ally_team_result or "")


def _details_participants(game: RecordedGame) -> list[tuple[PlayerKey, DetailsParticipant]]:
    """Return each participant of the game's details, by team and champion alias.

    Args:
        game: The recorded game.

    Returns:
        The participants; empty when the recording has no details or no champion summary.
    """
    details = _game_details(game)
    alias_by_champion_id = champion_aliases(game.client_resources.get(CHAMPION_SUMMARY_PATH))
    if details is None:
        return []
    return [
        (
            (
                TEAM_BY_ID[participant.team_id],
                alias_by_champion_id[participant.champion_id].lower(),
            ),
            participant,
        )
        for participant in details.participants
        if participant.team_id in TEAM_BY_ID and participant.champion_id in alias_by_champion_id
    ]


def _details_positions(game: RecordedGame) -> dict[PlayerKey, str]:
    """Return where each player played, by team and champion alias, from the game's details.

    Args:
        game: The recorded game.

    Returns:
        The positions; empty when the recording has no details or no champion summary.
    """
    return {
        key: history_position(
            participant.timeline.lane, participant.timeline.role, participant.team_position
        )
        for key, participant in _details_participants(game)
    }
