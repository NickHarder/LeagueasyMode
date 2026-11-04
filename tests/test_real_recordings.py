"""The owner's real games, replayed through the engine (audit ARCH-09).

Every other test builds its game from `game_payloads.py`, and those payloads named turrets and
inhibitors as no real game does: the suite stayed green while, in every game played, no turret or
inhibitor was read. These replay anonymized, trimmed copies of two games the owner played on
2026-10-29 (`tests/fixtures/recorded-games/`), as the engine met them:

- a Swiftplay on the Rift, 20 minutes, with 18 turrets and 3 inhibitors down;
- an ARAM: Mayhem on the Howling Abyss, with the enemy's inhibitor down at 14:24 and back at
  18:34.

The copies keep the game's answers, the client's game data and this game's details and timeline;
the other players' match histories, ranked stats and past timelines are left out.
`test_accuracy_thresholds.py` scores both.
"""

from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Final

from leagueasymode.engine import compute_overlay_state
from leagueasymode.game_state import GameSnapshot
from leagueasymode.inference.backs import BackTracker
from leagueasymode.inference.clues import ClueTracker
from leagueasymode.inference.experience import ExperienceTracker
from leagueasymode.inference.gold import GoldTracker
from leagueasymode.inference.jungle_path import JunglePathTracker
from leagueasymode.inference.sightings import SightingTracker
from leagueasymode.inference.wards import WardTracker
from leagueasymode.inference.you import YouTracker
from leagueasymode.overlay_state import OverlayState
from leagueasymode.patch_data import ITEMS_PATH, ItemCatalog
from leagueasymode.recording.file_format import ClientResource
from leagueasymode.recording.reader import iter_game_frames, iter_recording_lines

# One answer every this many seconds of game time is replayed: every answer took minutes.
REPLAY_STEP_SECONDS: Final = 5.0
RECORDINGS_DIRECTORY: Final = Path(__file__).parent / "fixtures" / "recorded-games"
RIFT_GAME: Final = RECORDINGS_DIRECTORY / "game-2026-10-29T04-00-16Z-anonymized.jsonl.xz"
ARAM_GAME: Final = RECORDINGS_DIRECTORY / "game-2026-10-29T21-09-39Z-anonymized.jsonl.xz"


@cache
def replayed(recording_path: Path) -> tuple[tuple[GameSnapshot, OverlayState], ...]:
    """An answer every few seconds of a recording, with the state the engine made of it, every
    tracker on."""
    items_payload = next(
        record.payload
        for record in iter_recording_lines(recording_path)
        if isinstance(record, ClientResource) and record.path == ITEMS_PATH
    )
    item_catalog = ItemCatalog.from_client_items(items_payload) if items_payload else None
    gold_tracker = GoldTracker()
    experience_tracker = ExperienceTracker()
    back_tracker = BackTracker()
    clue_tracker = ClueTracker()
    sighting_tracker = SightingTracker()
    jungle_tracker = JunglePathTracker()
    ward_tracker = WardTracker()
    you_tracker = YouTracker()
    pairs: list[tuple[GameSnapshot, OverlayState]] = []
    next_game_time_seconds = 0.0
    for frame in iter_game_frames(recording_path):
        if not isinstance(frame.payload, dict) or "gameData" not in frame.payload:
            continue
        snapshot = GameSnapshot.model_validate(frame.payload)
        if snapshot.game_data.game_time_seconds < next_game_time_seconds:
            continue
        next_game_time_seconds = snapshot.game_data.game_time_seconds + REPLAY_STEP_SECONDS
        state = compute_overlay_state(
            frame.payload,
            item_catalog,
            gold_tracker=gold_tracker,
            experience_tracker=experience_tracker,
            back_tracker=back_tracker,
            clue_tracker=clue_tracker,
            sighting_tracker=sighting_tracker,
            jungle_tracker=jungle_tracker,
            ward_tracker=ward_tracker,
            you_tracker=you_tracker,
        )
        pairs.append((snapshot, state))
    return tuple(pairs)


def states_from(recording_path: Path, game_time_seconds: float) -> Iterator[OverlayState]:
    return (
        state
        for snapshot, state in replayed(recording_path)
        if snapshot.game_data.game_time_seconds >= game_time_seconds
    )


def test_both_games_make_a_state_with_ten_players_all_through() -> None:
    for recording_path in (RIFT_GAME, ARAM_GAME):
        states = [state for _, state in replayed(recording_path)]
        assert len(states) > 150
        assert all(state.is_game_running for state in states)
        assert all(len(state.players) == 10 for state in states)


def test_on_the_rift_the_first_turret_down_shows_in_its_lane() -> None:
    # The Swiftplay's first turret, "Turret_TChaos_L0_P3_…", fell at 6:22: Chaos's bot outer.
    before = next(states_from(RIFT_GAME, 0.0))
    after = next(states_from(RIFT_GAME, 385.0))
    assert before.structures == []
    assert [(lane.lane, lane.turrets_down) for lane in after.structures] == [("bot", 1)]


def test_on_the_rift_a_fallen_inhibitor_is_timed_for_five_minutes() -> None:
    # "Inhib_TOrder_L1_P1_…", Order's mid inhibitor, fell at 18:28 (1108 s).
    state = next(states_from(RIFT_GAME, 1110.0))
    mid = [timer for timer in state.inhibitors if timer.lane == "mid"]
    assert len(mid) == 1
    assert 1108.0 + 299.0 <= mid[0].respawns_at_game_time_seconds <= 1108.0 + 301.0
    assert mid[0].is_rule_verified


def test_in_aram_a_fallen_inhibitor_is_timed_for_four_minutes_ten_and_goes_when_back() -> None:
    # "Inhib_TOrder_L1_P1_…" fell at 14:24 (864 s) and the feed said it respawned at 18:34.
    # The owner played Chaos: Order's inhibitor is the enemy's.
    (timer,) = next(states_from(ARAM_GAME, 866.0)).inhibitors
    assert timer.side == "enemy"
    assert 864.0 + 249.0 <= timer.respawns_at_game_time_seconds <= 864.0 + 251.0
    assert timer.is_rule_verified
    # By then the owner's own inhibitor is down too (16:16), its timer still running.
    assert [later.side for later in next(states_from(ARAM_GAME, 1116.0)).inhibitors] == ["ally"]


def test_in_aram_the_rifts_widgets_stay_off() -> None:
    for _, state in replayed(ARAM_GAME):
        assert not state.is_summoners_rift
        assert state.dragon is None
        assert state.win_chance is None
        assert state.jungle_paths == []
