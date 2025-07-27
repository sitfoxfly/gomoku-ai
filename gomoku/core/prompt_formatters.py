"""Advanced prompt formatters for GameState representation in LLM prompts."""

from typing import Dict, Optional
from .models import GameState
from abc import ABC, abstractmethod


class PromptFormatter(ABC):
    """Abstract base class for GameState prompt formatters."""

    @abstractmethod
    def format_board(self, state: GameState) -> str:
        """Format the board for LLM consumption."""
        pass


class StandardGridFormatter(PromptFormatter):
    """Standard grid format with coordinates (current implementation)."""

    def format_board(self, state: GameState) -> str:
        """Standard coordinate grid format."""
        result = "   "
        for col in range(state.board_size):
            result += f"{col:2} "
        result += "\n"

        for row in range(state.board_size):
            result += f"{row:2} "
            for col in range(state.board_size):
                result += f" {state.board[row][col]} "
            result += "\n"

        return result


class CompactFormatter(PromptFormatter):
    """Compact format optimized for token efficiency."""

    def format_board(self, state: GameState) -> str:
        """Compact row-by-row format."""
        result = []
        for row in range(state.board_size):
            row_str = "".join(state.board[row])
            result.append(f"R{row}: {row_str}")
        return "\n".join(result)


class NaturalLanguageFormatter(PromptFormatter):
    """Natural language description format."""

    def format_board(self, state: GameState) -> str:
        """Describe board state in natural language."""
        pieces = {"X": [], "O": []}

        for row in range(state.board_size):
            for col in range(state.board_size):
                piece = state.board[row][col]
                if piece in pieces:
                    pieces[piece].append(f"({row},{col})")

        description = []
        if pieces["X"]:
            description.append(f"Black pieces at: {', '.join(pieces['X'])}")
        if pieces["O"]:
            description.append(f"White pieces at: {', '.join(pieces['O'])}")

        if not description:
            description.append("Empty board")

        return "\n".join(description)


class JSONFormatter(PromptFormatter):
    """JSON format for structured LLM processing."""

    def format_board(self, state: GameState) -> str:
        """JSON representation of board."""
        board_data = {
            "board": state.board,
            "size": state.board_size,
            "current_player": state.current_player.value,
            "move_count": len(state.move_history),
        }

        import json

        return json.dumps(board_data, indent=2)

    def format_full_prompt(self, state: GameState, context: Optional[Dict] = None) -> str:
        """Full JSON format."""
        data = {
            "board": state.board,
            "board_size": state.board_size,
            "current_player": state.current_player.value,
            "move_count": len(state.move_history),
            "last_moves": [],
        }

        # Add recent moves
        recent_moves = state.move_history[-5:] if len(state.move_history) > 5 else state.move_history
        for move in recent_moves:
            data["last_moves"].append({"row": move.row, "col": move.col, "player": move.player.value})

        # Add context if provided
        if context:
            data.update(context)

        import json

        return json.dumps(data, indent=2)


class StrategicFormatter(PromptFormatter):
    """Strategic format emphasizing patterns and formations."""

    def format_board(self, state: GameState) -> str:
        """Board with strategic pattern highlighting."""
        result = self._add_coordinates_header(state.board_size)

        for row in range(state.board_size):
            result += f"{row:2} "
            for col in range(state.board_size):
                piece = state.board[row][col]
                # Highlight center positions
                if self._is_center_region(row, col, state.board_size):
                    result += f"[{piece}]"
                else:
                    result += f" {piece} "
            result += "\n"

        return result

    def _add_coordinates_header(self, board_size: int) -> str:
        """Add coordinate header."""
        result = "   "
        for col in range(board_size):
            result += f"{col:2} "
        result += "\n"
        return result

    def _is_center_region(self, row: int, col: int, board_size: int) -> bool:
        """Check if position is in center region."""
        center = board_size // 2
        return abs(row - center) <= 2 and abs(col - center) <= 2


# Utility function for easy access
def create_prompt_formatter(format_type: str = "standard", **kwargs) -> PromptFormatter:
    """Create a prompt formatter of the specified type."""
    formatters = {
        "standard": StandardGridFormatter,
        "compact": CompactFormatter,
        "natural": NaturalLanguageFormatter,
        "json": JSONFormatter,
        "strategic": StrategicFormatter,
    }

    if format_type not in formatters:
        raise ValueError(f"Unknown format type: {format_type}. Available: {list(formatters.keys())}")

    return formatters[format_type](**kwargs)
