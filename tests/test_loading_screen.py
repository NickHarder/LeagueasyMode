"""The game's first answer on the loading screen, as real games give it (audit DQ-03, ARCH-06)."""

from game_payloads import loading_screen_answer
from leagueasymode.engine import compute_overlay_state
from leagueasymode.engine_status import StatusBoard
from leagueasymode.game_state import GameSnapshot


def test_the_loading_screens_error_is_no_player_of_yours() -> None:
    # The API answers "Spectator mode doesn't currently support this feature" for the player on
    # this machine until the game loads; it was read as a level-1 player with no name and no gold.
    snapshot = GameSnapshot.model_validate(loading_screen_answer())
    assert snapshot.active_player is None


def test_the_status_says_there_is_no_player_of_yours_yet() -> None:
    board = StatusBoard()
    board.note_game(GameSnapshot.model_validate(loading_screen_answer()))
    (game_part,) = [part for part in board.report().parts if part.key == "game"]
    assert game_part.detail.endswith("0 players; no player of yours")


def test_the_loading_screen_gives_a_running_game_with_no_players() -> None:
    state = compute_overlay_state(loading_screen_answer())
    assert state.is_game_running
    assert state.players == []
    assert state.you is None
