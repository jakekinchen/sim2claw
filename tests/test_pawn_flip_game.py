from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

from sim2claw.pawn_flip_game import (
    FILES,
    RANK_DOWN,
    RANK_UP,
    BoardState,
    CountdownGame,
    FlipGame,
    GameMove,
    GameSession,
    PawnGameError,
    PrimitiveMove,
    all_skill_ids,
    load_contract_skill_ids,
    run_pawn_game,
    validate_against_contract,
)


def test_skill_surface_matches_frozen_contract_exactly() -> None:
    assert set(all_skill_ids()) == load_contract_skill_ids()
    assert len(all_skill_ids()) == 12
    assert validate_against_contract() == "pawn_rank12_bidirectional_b_to_g_v2"


def test_primitive_moves_only_toggle_one_file_between_ranks() -> None:
    move = PrimitiveMove("b", RANK_UP, RANK_DOWN)
    assert move.skill_id == "pawn_b2_to_b1"
    assert move.instruction == "Move the brown pawn from b2 to b1."
    with pytest.raises(PawnGameError):
        PrimitiveMove("a", RANK_UP, RANK_DOWN)
    with pytest.raises(PawnGameError):
        PrimitiveMove("b", RANK_UP, RANK_UP)


def test_every_game_move_expands_to_contract_skills_only() -> None:
    contract_ids = load_contract_skill_ids()
    for game in (CountdownGame(), FlipGame()):
        state = game.initial_state()
        for move in game.legal_moves(state):
            for primitive in game.primitives(state, move):
                assert primitive.skill_id in contract_ids


def test_illegal_moves_are_rejected() -> None:
    game = CountdownGame()
    state = game.initial_state()
    with pytest.raises(PawnGameError):
        game.primitives(state, GameMove(("b", "c", "d")))
    down_b = state.apply_primitive(PrimitiveMove("b", RANK_UP, RANK_DOWN))
    with pytest.raises(PawnGameError):
        game.primitives(down_b, GameMove(("b",)))


def test_move_parsing_normalizes_order_and_rejects_junk() -> None:
    countdown = CountdownGame()
    assert countdown.parse_move("d b").files == ("b", "d")
    with pytest.raises(PawnGameError):
        countdown.parse_move("b b")
    with pytest.raises(PawnGameError):
        countdown.parse_move("a")
    flip = FlipGame()
    assert flip.parse_move("c e").files == ("e", "c")
    assert flip.parse_move("e").files == ("e",)


def _first_player_wins(game, state: BoardState) -> bool:
    """Exhaustive minimax: does the player to move win with perfect play?"""

    @lru_cache(maxsize=None)
    def solve(ranks: tuple[int, ...]) -> bool:
        board = BoardState(ranks)
        moves = game.legal_moves(board)
        if not moves:
            return False
        return any(not solve(game.apply(board, move).ranks) for move in moves)

    return solve(state.ranks)


def test_countdown_start_is_a_second_player_win() -> None:
    game = CountdownGame()
    assert not _first_player_wins(game, game.initial_state())
    assert game.recommended_first_player == "human"


def test_flip_start_is_a_first_player_win() -> None:
    game = FlipGame()
    assert _first_player_wins(game, game.initial_state())
    assert game.recommended_first_player == "robot"


@pytest.mark.parametrize("game_class", [CountdownGame, FlipGame])
def test_best_move_never_surrenders_a_winning_position(game_class) -> None:
    game = game_class()
    for encoded in range(2 ** len(FILES)):
        ranks = tuple(
            RANK_UP if encoded & (1 << index) else RANK_DOWN
            for index in range(len(FILES))
        )
        state = BoardState(ranks)
        if state.is_all_down():
            continue
        move = game.best_move(state)
        assert move in game.legal_moves(state)
        if _first_player_wins(game, state):
            assert not _first_player_wins(game, game.apply(state, move))


@pytest.mark.parametrize("game_class", [CountdownGame, FlipGame])
def test_robot_beats_every_opponent_line_from_recommended_seat(game_class) -> None:
    game = game_class()

    def robot_always_wins(state: BoardState, robot_to_move: bool) -> bool:
        if game.is_over(state):
            # The player who just moved made the final move and won.
            return not robot_to_move
        if robot_to_move:
            return robot_always_wins(game.apply(state, game.best_move(state)), False)
        return all(
            robot_always_wins(game.apply(state, move), True)
            for move in game.legal_moves(state)
        )

    robot_first = game.recommended_first_player == "robot"
    assert robot_always_wins(game.initial_state(), robot_first)


def test_session_records_turns_and_winner() -> None:
    game = CountdownGame()
    session = GameSession(game, "human")
    session.play_move(GameMove(("b", "c")))
    session.play_move(game.best_move(session.state))
    assert [turn["player"] for turn in session.turns] == ["human", "robot"]
    assert session.turns[0]["primitives"][0]["skill_id"] == "pawn_b2_to_b1"
    transcript = session.transcript("pawn_rank12_bidirectional_b_to_g_v2")
    assert transcript["game"] == "countdown"
    assert transcript["winner"] is None


def test_demo_mode_runs_to_completion_and_writes_transcript(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    transcript_path = tmp_path / "flip_transcript.json"
    exit_code = run_pawn_game(
        "flip", first_player="auto", demo=True, transcript_path=transcript_path
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "winner: robot" in output
    transcript = json.loads(transcript_path.read_text())
    assert transcript["winner"] == "robot"
    contract_ids = load_contract_skill_ids()
    emitted = [
        primitive["skill_id"]
        for turn in transcript["turns"]
        for primitive in turn["primitives"]
    ]
    assert emitted and set(emitted) <= contract_ids


def test_countdown_demo_robot_wins_from_second_seat(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = run_pawn_game("countdown", first_player="auto", demo=True)
    assert exit_code == 0
    assert "winner: robot" in capsys.readouterr().out
