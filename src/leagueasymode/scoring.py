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

The timeline's XP and positions score the estimators still to come in the same way. Each score is
a number per game; the thresholds that CI holds them to are set from the first batch of recorded
games and never lowered to make a check pass.
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, JsonValue, ValidationError, field_validator

from leagueasymode.data_dragon import PatchStats
from leagueasymode.game_state import GameSnapshot, RiotPayloadModel
from leagueasymode.inference.combat_stats import estimated_combat_stats
from leagueasymode.inference.gold import GoldTracker, PlayerKey
from leagueasymode.inference.roles import assign_roles
from leagueasymode.overlay_state import CombatStats, GoldEstimate
from leagueasymode.patch_data import CHAMPION_SUMMARY_PATH, ITEMS_PATH, ItemCatalog
from leagueasymode.player_intel import champion_aliases, history_position
from leagueasymode.recording.file_format import ClientResource
from leagueasymode.recording.reader import iter_game_frames, iter_recording_lines

GAME_DETAILS_PATH_PREFIX: Final = "/lol-match-history/v1/games/"
TIMELINE_PATH_PREFIX: Final = "/lol-match-history/v1/game-timelines/"
MILLISECONDS_PER_SECOND: Final = 1000.0
# An estimate stands for a minute's timeline frame when it is this close after the frame's time.
FRAME_ALIGNMENT_SECONDS: Final = 2.0
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


@dataclass(frozen=True)
class EstimatorScore:
    """How far one estimator is from the truth on one game."""

    estimator: str
    sample_count: int
    # A share from 0 to 1 for "share_correct" and "share_within_band"; a percentage for
    # "mean_absolute_percent_error"; gold for "mean_absolute_error_gold".
    value: float
    measure: Literal[
        "share_correct",
        "mean_absolute_percent_error",
        "mean_absolute_error_gold",
        "share_within_band",
    ]

    def describe(self) -> str:
        """Return the score in one line, as `leagueasymode score` prints it.

        Returns:
            Such as "roles: 9/10 correct (90%)".
        """
        hit_count = round(self.value * self.sample_count)
        if self.measure == "share_correct":
            return (
                f"{self.estimator}: {hit_count}/{self.sample_count} correct "
                f"({self.value * PERCENT:.0f}%)"
            )
        if self.measure == "share_within_band":
            return (
                f"{self.estimator}: holds the truth {hit_count}/{self.sample_count} times "
                f"({self.value * PERCENT:.0f}%)"
            )
        if self.measure == "mean_absolute_error_gold":
            return (
                f"{self.estimator}: {self.sample_count} player-minutes, "
                f"{self.value:.0f} gold off on average"
            )
        return f"{self.estimator}: {self.sample_count} moments, {self.value:.1f}% off on average"


@dataclass(frozen=True)
class RecordedGame:
    """What the harness reads from a recording."""

    # The last answer of the game in each minute of game time, in order.
    minute_snapshots: tuple[GameSnapshot, ...]
    # The League client's latest answer for each path it was asked.
    client_resources: Mapping[str, JsonValue]
    # The gold tracker's estimates at the first answer of each minute of game time, by minute.
    minute_gold_estimates: Mapping[int, Mapping[PlayerKey, GoldEstimate]]


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


class GameDetails(RiotPayloadModel):
    """The game's details from the League client, after the game."""

    participants: list[DetailsParticipant] = Field(default_factory=list)


class TimelineParticipantFrame(RiotPayloadModel):
    """One participant's gold at one frame of the match timeline."""

    participant_id: int = Field(default=0, alias="participantId")
    current_gold: int = Field(default=0, alias="currentGold")
    total_gold: int = Field(default=0, alias="totalGold")


class TimelineFrame(RiotPayloadModel):
    """One frame of the match timeline: every participant, about once a minute."""

    timestamp_milliseconds: int = Field(default=0, alias="timestamp")
    participant_frames: list[TimelineParticipantFrame] = Field(
        default_factory=list, alias="participantFrames"
    )

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
    """Read what the harness needs from a recording, running the gold tracker through it.

    Args:
        recording_path: The recording.

    Returns:
        The game's snapshot at the end of each minute, the client's answers, and the gold
        tracker's estimates at the start of each minute.
    """
    client_resources = {
        record.path: record.payload
        for record in iter_recording_lines(recording_path)
        if isinstance(record, ClientResource)
    }
    items_payload = client_resources.get(ITEMS_PATH)
    item_catalog = ItemCatalog.from_client_items(items_payload) if items_payload else None
    gold_tracker = GoldTracker()
    snapshot_by_minute: dict[int, GameSnapshot] = {}
    gold_estimates_by_minute: dict[int, Mapping[PlayerKey, GoldEstimate]] = {}
    for frame in iter_game_frames(recording_path):
        try:
            snapshot = GameSnapshot.model_validate(frame.payload)
        except ValidationError:
            continue
        game_time_seconds = snapshot.game_data.game_time_seconds
        game_minute = int(game_time_seconds // SECONDS_PER_MINUTE)
        snapshot_by_minute[game_minute] = snapshot
        gold_estimates = gold_tracker.update(snapshot, item_catalog)
        is_minute_start = game_time_seconds - game_minute * SECONDS_PER_MINUTE <= (
            FRAME_ALIGNMENT_SECONDS
        )
        if is_minute_start and game_minute not in gold_estimates_by_minute:
            gold_estimates_by_minute[game_minute] = gold_estimates
    return RecordedGame(
        minute_snapshots=tuple(snapshot_by_minute[minute] for minute in sorted(snapshot_by_minute)),
        client_resources=client_resources,
        minute_gold_estimates=gold_estimates_by_minute,
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
    scored_pairs = list(_gold_pairs(game))
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
    ]


def _gold_pairs(game: RecordedGame) -> Iterator[tuple[GoldEstimate, TimelineParticipantFrame]]:
    """Yield each estimate of a player's gold with the timeline's truth for the same minute.

    Args:
        game: The recorded game.

    Yields:
        The pairs, your own exact gold left out.
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
        # At 0:00 everyone holds the starting gold, which scores nothing.
        if game_minute == 0 or not is_aligned:
            continue
        estimates = game.minute_gold_estimates.get(game_minute, {})
        for truth in frame.participant_frames:
            key = key_by_participant_id.get(truth.participant_id)
            estimate = estimates.get(key) if key is not None else None
            if estimate is not None and estimate.source == "estimate":
                yield estimate, truth


def _game_timeline(game: RecordedGame) -> GameTimeline | None:
    """Return the match timeline the recording holds.

    Args:
        game: The recorded game.

    Returns:
        The timeline, or None when the recording has none it can read.
    """
    timeline_payload = next(
        (
            payload
            for path, payload in game.client_resources.items()
            if path.startswith(TIMELINE_PATH_PREFIX)
        ),
        None,
    )
    try:
        return GameTimeline.model_validate(timeline_payload)
    except ValidationError:
        return None


def _details_participants(game: RecordedGame) -> list[tuple[PlayerKey, DetailsParticipant]]:
    """Return each participant of the game's details, by team and champion alias.

    Args:
        game: The recorded game.

    Returns:
        The participants; empty when the recording has no details or no champion summary.
    """
    details_payload = next(
        (
            payload
            for path, payload in game.client_resources.items()
            if path.startswith(GAME_DETAILS_PATH_PREFIX)
        ),
        None,
    )
    alias_by_champion_id = champion_aliases(game.client_resources.get(CHAMPION_SUMMARY_PATH))
    try:
        details = GameDetails.model_validate(details_payload)
    except ValidationError:
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
