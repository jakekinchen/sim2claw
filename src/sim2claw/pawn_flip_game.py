"""Turn-based demo games composed only from the 12 frozen B-G toggle skills.

Every physical action either game can ever request is one of the twelve
directed skills frozen in ``configs/evaluations/pawn_rank12_bidirectional_v2``:
moving the pawn of a single file (b through g) between rank 1 and rank 2.
No sideways travel, no other squares, no other pieces.

Two rule sets share that move surface:

- ``countdown``: all six pawns start on rank 2 ("up"). On a turn a player
  moves one or two pawns down to rank 1. Whoever moves the last pawn down
  wins. Perfect play leaves a multiple of three pawns up, so the player who
  moves second from the six-up start always wins.
- ``flip``: each file's pawn is either up (rank 2) or down (rank 1). On a
  turn a player moves one up pawn down and may additionally toggle any single
  pawn on a file strictly to its left (in either direction). Whoever makes
  the last move wins. This is the classic Turning Turtles game: an up pawn
  on the i-th file is a Nim heap of size i, so perfect play targets XOR zero.
  From the all-up start the first player always wins.

This module is game logic only. It emits skill identities and canonical
instruction strings; it never claims camera, serial, servo, or motion
authority. Dispatching the emitted skills to hardware stays behind the
reviewed gateway path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

from .paths import REPO_ROOT


FILES: tuple[str, ...] = ("b", "c", "d", "e", "f", "g")
FILE_HEAP: dict[str, int] = {name: index + 1 for index, name in enumerate(FILES)}
RANK_UP = 2
RANK_DOWN = 1
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "pawn_rank12_bidirectional_v2.json"
)
CANONICAL_INSTRUCTION = "Move the brown pawn from {SOURCE} to {DESTINATION}."


class PawnGameError(ValueError):
    """Raised for illegal moves, malformed input, or contract mismatches."""


@dataclass(frozen=True)
class PrimitiveMove:
    """One directed toggle of a single file's pawn between ranks 1 and 2."""

    file: str
    source_rank: int
    destination_rank: int

    def __post_init__(self) -> None:
        if self.file not in FILES:
            raise PawnGameError(f"file out of scope: {self.file!r}")
        if {self.source_rank, self.destination_rank} != {RANK_DOWN, RANK_UP}:
            raise PawnGameError(
                "a primitive move must connect rank 1 and rank 2 on one file"
            )

    @property
    def source_square(self) -> str:
        return f"{self.file}{self.source_rank}"

    @property
    def destination_square(self) -> str:
        return f"{self.file}{self.destination_rank}"

    @property
    def skill_id(self) -> str:
        return f"pawn_{self.source_square}_to_{self.destination_square}"

    @property
    def instruction(self) -> str:
        return CANONICAL_INSTRUCTION.format(
            SOURCE=self.source_square, DESTINATION=self.destination_square
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "skill_id": self.skill_id,
            "source_square": self.source_square,
            "destination_square": self.destination_square,
            "instruction": self.instruction,
        }


def all_skill_ids() -> tuple[str, ...]:
    """The full directed skill surface either game can request."""

    ids = []
    for name in FILES:
        ids.append(PrimitiveMove(name, RANK_DOWN, RANK_UP).skill_id)
        ids.append(PrimitiveMove(name, RANK_UP, RANK_DOWN).skill_id)
    return tuple(ids)


def load_contract_skill_ids(contract_path: Path | None = None) -> set[str]:
    path = contract_path or DEFAULT_CONTRACT_PATH
    contract = json.loads(path.read_text())
    skills = contract.get("skills")
    if not isinstance(skills, list) or not skills:
        raise PawnGameError(f"contract has no skills list: {path}")
    return {str(skill["skill_id"]) for skill in skills}


def validate_against_contract(contract_path: Path | None = None) -> str:
    """Fail closed unless the game's skill surface equals the frozen contract."""

    path = contract_path or DEFAULT_CONTRACT_PATH
    contract_ids = load_contract_skill_ids(path)
    game_ids = set(all_skill_ids())
    if contract_ids != game_ids:
        raise PawnGameError(
            "game skill surface does not match the frozen contract: "
            f"missing={sorted(contract_ids - game_ids)} "
            f"extra={sorted(game_ids - contract_ids)}"
        )
    contract = json.loads(path.read_text())
    return str(contract.get("evaluation_set_id", path.name))


@dataclass(frozen=True)
class BoardState:
    """Rank (1 or 2) of the single pawn on each in-scope file."""

    ranks: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.ranks) != len(FILES):
            raise PawnGameError("board state must cover exactly files b through g")
        if any(rank not in (RANK_DOWN, RANK_UP) for rank in self.ranks):
            raise PawnGameError("every pawn must sit on rank 1 or rank 2")

    @classmethod
    def all_up(cls) -> "BoardState":
        return cls(tuple(RANK_UP for _ in FILES))

    def rank_of(self, file: str) -> int:
        return self.ranks[FILES.index(file)]

    def is_up(self, file: str) -> bool:
        return self.rank_of(file) == RANK_UP

    def up_files(self) -> tuple[str, ...]:
        return tuple(name for name in FILES if self.is_up(name))

    def is_all_down(self) -> bool:
        return not self.up_files()

    def apply_primitive(self, move: PrimitiveMove) -> "BoardState":
        if self.rank_of(move.file) != move.source_rank:
            raise PawnGameError(
                f"pawn on file {move.file} is not on rank {move.source_rank}"
            )
        ranks = list(self.ranks)
        ranks[FILES.index(move.file)] = move.destination_rank
        return BoardState(tuple(ranks))

    def toggle_primitive(self, file: str) -> PrimitiveMove:
        source = self.rank_of(file)
        destination = RANK_UP if source == RANK_DOWN else RANK_DOWN
        return PrimitiveMove(file, source, destination)

    def render(self) -> str:
        row2 = " ".join("P" if rank == RANK_UP else "." for rank in self.ranks)
        row1 = " ".join("." if rank == RANK_UP else "P" for rank in self.ranks)
        return (
            f"rank 2 | {row2}\n"
            f"rank 1 | {row1}\n"
            f"         {' '.join(FILES)}"
        )


@dataclass(frozen=True)
class GameMove:
    """A game-level turn: an ordered sequence of file toggles."""

    files: tuple[str, ...]

    def describe(self) -> str:
        return " then ".join(self.files)


class PawnToggleGame:
    """Shared surface for the two rule sets."""

    name: str
    rules_text: str
    recommended_first_player: str

    def initial_state(self) -> BoardState:
        return BoardState.all_up()

    def legal_moves(self, state: BoardState) -> list[GameMove]:
        raise NotImplementedError

    def primitives(self, state: BoardState, move: GameMove) -> list[PrimitiveMove]:
        if move not in self.legal_moves(state):
            raise PawnGameError(f"illegal move: {move.describe()}")
        primitives: list[PrimitiveMove] = []
        current = state
        for name in move.files:
            primitive = current.toggle_primitive(name)
            primitives.append(primitive)
            current = current.apply_primitive(primitive)
        return primitives

    def apply(self, state: BoardState, move: GameMove) -> BoardState:
        for primitive in self.primitives(state, move):
            state = state.apply_primitive(primitive)
        return state

    def is_over(self, state: BoardState) -> bool:
        return state.is_all_down()

    def best_move(self, state: BoardState) -> GameMove:
        raise NotImplementedError

    def parse_move(self, text: str) -> GameMove:
        tokens = tuple(token for token in text.replace(",", " ").lower().split())
        if not tokens or any(token not in FILES for token in tokens):
            raise PawnGameError(
                f"enter file letters from {'/'.join(FILES)}, e.g. 'e' or 'e c'"
            )
        return GameMove(tokens)


class CountdownGame(PawnToggleGame):
    """Move one or two up pawns down; whoever moves the last pawn down wins."""

    name = "countdown"
    rules_text = (
        "All six pawns start on rank 2. On your turn move one or two pawns "
        "down to rank 1. Whoever moves the last pawn down wins."
    )
    # Six is a multiple of three, so the second player holds the win.
    recommended_first_player = "human"

    def legal_moves(self, state: BoardState) -> list[GameMove]:
        up = state.up_files()
        moves = [GameMove((name,)) for name in up]
        for i, first in enumerate(up):
            for second in up[i + 1 :]:
                moves.append(GameMove((first, second)))
        return moves

    def best_move(self, state: BoardState) -> GameMove:
        up = state.up_files()
        if not up:
            raise PawnGameError("no legal moves: the game is over")
        remainder = len(up) % 3
        if remainder == 0:
            return GameMove((up[0],))
        return GameMove(up[-remainder:])

    def parse_move(self, text: str) -> GameMove:
        move = super().parse_move(text)
        if len(move.files) > 2 or len(set(move.files)) != len(move.files):
            raise PawnGameError("choose one or two distinct files, e.g. 'b' or 'b d'")
        return GameMove(tuple(sorted(move.files, key=FILE_HEAP.__getitem__)))


class FlipGame(PawnToggleGame):
    """Turning Turtles: flip one up pawn down, optionally toggle one to its left."""

    name = "flip"
    rules_text = (
        "Each pawn is up (rank 2) or down (rank 1). On your turn move one up "
        "pawn down, and you may also toggle one pawn on a file to its left, "
        "either direction. Whoever makes the last move wins."
    )
    # The all-up start has Nim value 1^2^3^4^5^6 = 7, a first-player win.
    recommended_first_player = "robot"

    def legal_moves(self, state: BoardState) -> list[GameMove]:
        moves: list[GameMove] = []
        for primary in state.up_files():
            moves.append(GameMove((primary,)))
            for secondary in FILES:
                if FILE_HEAP[secondary] < FILE_HEAP[primary]:
                    moves.append(GameMove((primary, secondary)))
        return moves

    @staticmethod
    def nim_value(state: BoardState) -> int:
        value = 0
        for name in state.up_files():
            value ^= FILE_HEAP[name]
        return value

    def best_move(self, state: BoardState) -> GameMove:
        up = state.up_files()
        if not up:
            raise PawnGameError("no legal moves: the game is over")
        value = self.nim_value(state)
        if value:
            for primary in reversed(up):
                target = value ^ FILE_HEAP[primary]
                if target == 0:
                    return GameMove((primary,))
                if target < FILE_HEAP[primary]:
                    return GameMove((primary, FILES[target - 1]))
        # Losing position: keep the game going with the smallest single flip.
        return GameMove((up[0],))

    def parse_move(self, text: str) -> GameMove:
        move = super().parse_move(text)
        if len(move.files) > 2 or len(set(move.files)) != len(move.files):
            raise PawnGameError(
                "choose an up pawn, optionally with one file to its left, "
                "e.g. 'e' or 'e c'"
            )
        files = move.files
        if len(files) == 2 and FILE_HEAP[files[0]] < FILE_HEAP[files[1]]:
            files = (files[1], files[0])
        return GameMove(files)


GAMES: dict[str, type[PawnToggleGame]] = {
    CountdownGame.name: CountdownGame,
    FlipGame.name: FlipGame,
}


def _scripted_opponent(game: PawnToggleGame, state: BoardState) -> GameMove:
    return game.legal_moves(state)[0]


def _iter_human_moves(
    game: PawnToggleGame, state_source: "GameSession"
) -> Iterator[GameMove]:
    while True:
        try:
            text = input("your move> ").strip()
        except EOFError:
            raise PawnGameError("input closed; game abandoned")
        if text.lower() in {"q", "quit", "exit"}:
            raise PawnGameError("game abandoned by player")
        try:
            move = game.parse_move(text)
            game.primitives(state_source.state, move)
        except PawnGameError as error:
            print(f"  illegal move: {error}")
            continue
        yield move


class GameSession:
    """Runs one game and records every emitted skill for the transcript."""

    def __init__(self, game: PawnToggleGame, first_player: str) -> None:
        if first_player not in ("human", "robot"):
            raise PawnGameError("first player must be 'human' or 'robot'")
        self.game = game
        self.state = game.initial_state()
        self.to_play = first_player
        self.turns: list[dict[str, Any]] = []
        self.winner: str | None = None

    def play_move(self, move: GameMove) -> list[PrimitiveMove]:
        primitives = self.game.primitives(self.state, move)
        self.state = self.game.apply(self.state, move)
        self.turns.append(
            {
                "player": self.to_play,
                "move": list(move.files),
                "primitives": [primitive.as_dict() for primitive in primitives],
            }
        )
        if self.game.is_over(self.state):
            self.winner = self.to_play
        self.to_play = "robot" if self.to_play == "human" else "human"
        return primitives

    def transcript(self, evaluation_set_id: str) -> dict[str, Any]:
        return {
            "schema_version": "sim2claw.pawn_toggle_game_transcript.v1",
            "game": self.game.name,
            "skill_contract_evaluation_set_id": evaluation_set_id,
            "proof_class": "game_transcript_only_no_physical_result",
            "turns": self.turns,
            "winner": self.winner,
        }


def run_pawn_game(
    game_name: str,
    first_player: str = "auto",
    demo: bool = False,
    transcript_path: Path | None = None,
    contract_path: Path | None = None,
) -> int:
    if game_name not in GAMES:
        raise PawnGameError(f"unknown game: {game_name!r}")
    game = GAMES[game_name]()
    evaluation_set_id = validate_against_contract(contract_path)
    if first_player == "auto":
        first_player = game.recommended_first_player
    session = GameSession(game, first_player)

    print(f"game: {game.name}")
    print(f"skills validated against: {evaluation_set_id}")
    print(game.rules_text)
    print(f"{first_player} moves first\n")

    human_moves = None if demo else _iter_human_moves(game, session)
    while not game.is_over(session.state):
        print(session.state.render())
        if session.to_play == "robot":
            move = game.best_move(session.state)
            print(f"robot plays: {move.describe()}")
        elif demo:
            move = _scripted_opponent(game, session.state)
            print(f"scripted opponent plays: {move.describe()}")
        else:
            assert human_moves is not None
            move = next(human_moves)
        mover = session.to_play
        primitives = session.play_move(move)
        if mover == "robot":
            for primitive in primitives:
                print(f"  [{primitive.skill_id}] {primitive.instruction}")
        print()

    print(session.state.render())
    print(f"\nwinner: {session.winner}")
    if transcript_path is not None:
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(
            json.dumps(session.transcript(evaluation_set_id), indent=2, sort_keys=True)
            + "\n"
        )
        print(f"transcript written: {transcript_path}")
    return 0
