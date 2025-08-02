"""Core data models for Gomoku game."""

from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from enum import Enum
from abc import ABC, abstractmethod


class Player(Enum):
    BLACK = "X"  # First player
    WHITE = "O"  # Second player
    EMPTY = "."


class GameResult(Enum):
    # Normal game endings
    BLACK_WIN = "black_win"              # Code: BW - Black wins by getting 5 in a row
    WHITE_WIN = "white_win"              # Code: WW - White wins by getting 5 in a row
    DRAW = "draw"                        # Code: DR - Game ends in draw (board full)
    
    # Illegal move endings
    INVALID_MOVE = "invalid_move"        # Code: IM - Invalid position (occupied/out of bounds)
    TIMEOUT = "timeout"                  # Code: TO - Player exceeded time limit
    
    # Error endings
    EXCEPTION = "exception"              # Code: EX - Agent crashed or threw exception
    RESIGNATION = "resignation"          # Code: RS - Agent resigned (future use)
    
    def get_code(self) -> str:
        """Get standardized 2-letter code for this result."""
        code_map = {
            GameResult.BLACK_WIN: "BW",
            GameResult.WHITE_WIN: "WW", 
            GameResult.DRAW: "DR",
            GameResult.INVALID_MOVE: "IM",
            GameResult.TIMEOUT: "TO",
            GameResult.EXCEPTION: "EX",
            GameResult.RESIGNATION: "RS",
        }
        return code_map.get(self, "UK")  # UK = Unknown
    
    @classmethod
    def from_code(cls, code: str) -> 'GameResult':
        """Get GameResult from 2-letter code."""
        code_map = {
            "BW": cls.BLACK_WIN,
            "WW": cls.WHITE_WIN,
            "DR": cls.DRAW,
            "IM": cls.INVALID_MOVE,
            "TO": cls.TIMEOUT,
            "EX": cls.EXCEPTION,
            "RS": cls.RESIGNATION,
        }
        if code not in code_map:
            raise ValueError(f"Unknown game result code: {code}")
        return code_map[code]


@dataclass
class Move:
    row: int
    col: int
    player: Player


@dataclass
class GameState:
    board: List[List[str]]
    current_player: Player
    move_history: List[Move]
    board_size: int

    def copy(self):
        """Deep copy of game state"""
        return GameState(
            board=[row[:] for row in self.board],
            current_player=self.current_player,
            move_history=[Move(move.row, move.col, move.player) for move in self.move_history],
            board_size=self.board_size,
        )

    def is_valid_move(self, row: int, col: int) -> bool:
        """Check if move is valid."""
        if row < 0 or row >= self.board_size or col < 0 or col >= self.board_size:
            return False
        return self.board[row][col] == Player.EMPTY.value

    def is_board_full(self) -> bool:
        """Check if board is full (draw)."""
        for row in self.board:
            if Player.EMPTY.value in row:
                return False
        return True

    def get_legal_moves(self) -> List[Tuple[int, int]]:
        """Get all legal moves."""
        moves = []
        for row in range(self.board_size):
            for col in range(self.board_size):
                if self.board[row][col] == Player.EMPTY.value:
                    moves.append((row, col))
        return moves

    def _check_direction(self, row: int, col: int, dr: int, dc: int, player: str) -> int:
        """Count consecutive pieces in one direction."""
        count = 0
        r, c = row + dr, col + dc

        while 0 <= r < self.board_size and 0 <= c < self.board_size and self.board[r][c] == player:
            count += 1
            r += dr
            c += dc

        return count

    def check_win_at_position(self, row: int, col: int, win_condition: int = 5) -> bool:
        """Check if placing a piece at (row, col) creates a win."""
        if self.board[row][col] == Player.EMPTY.value:
            return False

        player = self.board[row][col]
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]  # horizontal, vertical, diagonals

        for dr, dc in directions:
            count = 1  # Current piece
            count += self._check_direction(row, col, dr, dc, player)
            count += self._check_direction(row, col, -dr, -dc, player)

            if count >= win_condition:
                return True

        return False

    def format_board(self, formatter: str = "standard") -> str:
        """Format the board using specified formatter keyword.

        Args:
            formatter: Formatter type ('standard', 'compact', 'natural', 'json', 'strategic', 'simple', 'color')

        Returns:
            Formatted board string
        """
        from ..utils.visualization import create_formatter
        return create_formatter(formatter).format_board(self)


# Note: BoardFormatter classes have been consolidated in gomoku.utils.visualization
