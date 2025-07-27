"""Board formatting utilities to avoid circular imports."""

from .models import GameState
from .prompt_formatters import create_prompt_formatter


def format_board(state: GameState, formatter: str = "standard") -> str:
    """Format the board using specified formatter keyword.
    
    Args:
        state: GameState to format
        formatter: Formatter type ('standard', 'compact', 'natural', 'json', 'strategic')
        
    Returns:
        Formatted board string
    """
    formatter_instance = create_prompt_formatter(formatter)
    return formatter_instance.format_board(state)