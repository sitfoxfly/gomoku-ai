"""Game arena for orchestrating matches."""

import asyncio
import time
from typing import Dict, List
from ..core.models import GameState, Player, GameResult, Move
from ..core.game_logic import GomokuGame
from ..utils.visualization import BoardFormatter
from ..agents.base import Agent
from ..utils.visualization import ColorBoardFormatter
from ..llm.interfaces import LLMClient, LLMLoggingProxy


class GomokuArena:
    """Orchestrates games between agents with visualization and timing."""

    def __init__(self, board_size: int = 15, time_limit: float = 30.0, formatter: BoardFormatter = None):
        self.board_size = board_size
        self.time_limit = time_limit  # seconds per move
        self.formatter = formatter or ColorBoardFormatter(board_size)

    def board_to_string(self, state: GameState) -> str:
        """Convert board to readable string representation."""
        return self.formatter.format_board(state)

    def draw_board_with_winning_sequence(self, board: List[List[str]], winning_sequence: List[tuple]) -> str:
        """Draw board with winning sequence highlighted."""
        return self.formatter.format_board_with_highlights(board, winning_sequence)

    def move_history_to_string(self, moves: List[Move]) -> str:
        """Convert move history to readable format."""
        result = []
        for i, move in enumerate(moves):
            player_name = "Black(X)" if move.player == Player.BLACK else "White(O)"
            result.append(f"{i+1}. {player_name}: ({move.row}, {move.col})")
        return "\n".join(result)

    def _find_and_wrap_llm_clients(self, agent: Agent) -> Agent:
        """Find and wrap any LLMClient instances in the agent with logging proxy."""
        for attr_name in dir(agent):
            try:
                attr_value = getattr(agent, attr_name)
                
                # Check if this attribute is an LLMClient but NOT already a proxy
                if isinstance(attr_value, LLMClient) and not isinstance(attr_value, LLMLoggingProxy):
                    # Wrap with logging proxy
                    proxy = LLMLoggingProxy(attr_value)
                    setattr(agent, attr_name, proxy)
            except (AttributeError, TypeError):
                continue
        
        return agent

    def _find_llm_logs(self, agent: Agent) -> List:
        """Find any llm_logs attribute in the agent."""
        for attr_name in dir(agent):
            try:
                attr_value = getattr(agent, attr_name)
                if hasattr(attr_value, 'llm_logs') and isinstance(getattr(attr_value, 'llm_logs'), list):
                    return getattr(attr_value, 'llm_logs')
            except (AttributeError, TypeError):
                continue
        return []

    async def run_game(self, agent1: Agent, agent2: Agent, verbose: bool = True) -> Dict:
        """Run a complete game between two agents."""
        # Initialize game state
        game = GomokuGame(board_size=self.board_size)

        # Wrap any LLM clients with logging proxies
        agent1 = self._find_and_wrap_llm_clients(agent1)
        agent2 = self._find_and_wrap_llm_clients(agent2)

        # Assign players
        agent1.player = Player.BLACK
        agent2.player = Player.WHITE
        agents = {Player.BLACK: agent1, Player.WHITE: agent2}

        game_log = []
        start_time = time.time()

        while True:
            current_agent = agents[game.current_player]

            if verbose:
                print(f"\n{game.current_player.name}'s turn ({current_agent.agent_id})")
                print(self.board_to_string(game.state))

            # Get move with timeout
            try:
                move_start = time.time()
                
                # Track LLM logs before the move
                agent_logs = self._find_llm_logs(current_agent)
                initial_log_count = len(agent_logs)
                
                move = await asyncio.wait_for(current_agent.get_move(game.state.copy()), timeout=self.time_limit)
                move_time = time.time() - move_start

                row, col = move

                # Make move
                if not game.make_move(row, col):
                    # Invalid move
                    if verbose:
                        print(f"Invalid move by {current_agent.agent_id}: ({row}, {col})")
                        print("Final board:")
                        print(self.board_to_string(game.state))

                    winner = Player.WHITE if game.current_player == Player.BLACK else Player.BLACK
                    return {
                        "winner": agents[winner].agent_id,
                        "loser": current_agent.agent_id,
                        "result": GameResult.INVALID_MOVE,
                        "reason": f"Invalid move by {current_agent.agent_id} at ({row}, {col})",
                        "moves": len(game.state.move_history),
                        "game_log": game_log,
                        "final_board": game.state.board,
                        "move_history": self.move_history_to_string(game.state.move_history),
                        "winning_sequence": [],
                    }

                # Collect all LLM logs from this turn
                llm_conversations = []
                current_log_count = len(agent_logs)
                if current_log_count > initial_log_count:
                    llm_conversations = agent_logs[initial_log_count:current_log_count]
                
                game_log.append(
                    {
                        "move_number": len(game.state.move_history),
                        "player": current_agent.agent_id,
                        "position": (row, col),
                        "time": move_time,
                        "llm_conversations": llm_conversations,
                    }
                )

                if verbose:
                    print(f"Move: ({row}, {col}) in {move_time:.2f}s")

                # Check for winner
                winner = game.check_winner()
                if winner:
                    # Find winning sequence
                    winning_sequence = game.find_winning_sequence(winner)
                    
                    if verbose:
                        print(f"\n🏆 Game Over! {agents[winner].agent_id} wins!")
                        print("Final board:")
                        print(self.board_to_string(game.state))
                    
                    return {
                        "winner": agents[winner].agent_id,
                        "loser": agents[Player.WHITE if winner == Player.BLACK else Player.BLACK].agent_id,
                        "result": GameResult.BLACK_WIN if winner == Player.BLACK else GameResult.WHITE_WIN,
                        "reason": "Five in a row",
                        "moves": len(game.state.move_history),
                        "game_log": game_log,
                        "final_board": game.state.board,
                        "move_history": self.move_history_to_string(game.state.move_history),
                        "total_time": time.time() - start_time,
                        "winning_sequence": winning_sequence,
                    }

                # Check for draw
                if game.state.is_board_full():
                    if verbose:
                        print(f"\n🤝 Game Over! Draw - Board is full!")
                        print("Final board:")
                        print(self.board_to_string(game.state))
                    
                    return {
                        "winner": None,
                        "result": GameResult.DRAW,
                        "reason": "Board full",
                        "moves": len(game.state.move_history),
                        "game_log": game_log,
                        "final_board": game.state.board,
                        "move_history": self.move_history_to_string(game.state.move_history),
                        "total_time": time.time() - start_time,
                        "winning_sequence": [],
                    }

            except asyncio.TimeoutError:
                if verbose:
                    print(f"Timeout by {current_agent.agent_id}")
                    print("Final board:")
                    print(self.board_to_string(game.state))

                winner = Player.WHITE if game.current_player == Player.BLACK else Player.BLACK
                return {
                    "winner": agents[winner].agent_id,
                    "loser": current_agent.agent_id,
                    "result": GameResult.INVALID_MOVE,
                    "reason": f"Timeout (>{self.time_limit}s)",
                    "moves": len(game.state.move_history),
                    "game_log": game_log,
                    "final_board": game.state.board,
                    "move_history": self.move_history_to_string(game.state.move_history),
                    "winning_sequence": [],
                }
