"""Command line interface for Gomoku AI."""

import asyncio
import argparse
import sys
from typing import Optional

from .core import Player, GameResult
from .agents import LLMGomokuAgent, SimpleGomokuAgent, StandardStrategy, AggressiveStrategy
from .llm import OpenAIGomokuClient, create_huggingface_client, POPULAR_MODELS
from .arena import GomokuArena, Tournament
from .utils import ColorBoardFormatter


def main_demo():
    """Run the main demonstration."""
    asyncio.run(_main_demo())


async def _main_demo():
    """Main demonstration of the Gomoku AI system."""
    print("=== GOMOKU AI DEMO ===\n")

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Gomoku AI Demo')
    parser.add_argument('--board-size', type=int, default=8, help='Board size (default: 8)')
    parser.add_argument('--api-key', type=str, help='OpenAI API key')
    parser.add_argument('--model', type=str, default='gpt-4o-mini', help='LLM model to use')
    parser.add_argument('--endpoint', type=str, help='Custom API endpoint')
    parser.add_argument('--no-llm', action='store_true', help='Run without LLM (simple agents only)')
    parser.add_argument('--huggingface', type=str, help='Use HuggingFace model (e.g., gpt2, microsoft/DialoGPT-medium)')
    parser.add_argument('--hf-device', type=str, default='auto', help='HuggingFace device (auto, cpu, cuda)')
    parser.add_argument('--list-hf-models', action='store_true', help='List available HuggingFace models')
    
    args = parser.parse_args()

    # Handle list models request
    if args.list_hf_models:
        print("Available HuggingFace models:")
        for key, config in POPULAR_MODELS.items():
            print(f"  {key:25} - {config['description']}")
        print("\nUsage: gomoku-demo --huggingface gpt2")
        return

    # Create arena
    board_size = args.board_size
    formatter = ColorBoardFormatter(board_size)
    arena = GomokuArena(board_size=board_size, formatter=formatter)

    if args.no_llm:
        # Simple agents only
        print("Running with simple agents only (no LLM)")
        agents = [
            SimpleGomokuAgent("Simple_Agent_1"),
            SimpleGomokuAgent("Simple_Agent_2")
        ]
    elif args.huggingface:
        # Use HuggingFace model
        try:
            print(f"Loading HuggingFace model: {args.huggingface}")
            hf_client = create_huggingface_client(
                args.huggingface, 
                device=args.hf_device
            )
            
            # Create strategies
            standard_strategy = StandardStrategy(board_size)
            aggressive_strategy = AggressiveStrategy(board_size)

            # Create agents
            agents = [
                LLMGomokuAgent("HF_Strategic", hf_client, standard_strategy, board_size),
                LLMGomokuAgent("HF_Aggressive", hf_client, aggressive_strategy, board_size),
                SimpleGomokuAgent("Simple_Agent")
            ]
            
        except ImportError:
            print("❌ HuggingFace dependencies not installed.")
            print("Install with: pip install 'gomoku-ai[huggingface]'")
            return
        except Exception as e:
            print(f"❌ Error loading HuggingFace model: {e}")
            print("Try a different model or use --list-hf-models to see available options")
            return
    else:
        # Create OpenAI LLM client
        api_key = args.api_key or "demo_key"  # Default for demo
        llm_client = OpenAIGomokuClient(
            api_key=api_key,
            model=args.model,
            endpoint=args.endpoint
        )

        # Create strategies
        standard_strategy = StandardStrategy(board_size)
        aggressive_strategy = AggressiveStrategy(board_size)

        # Create agents
        agents = [
            LLMGomokuAgent("Strategic_AI", llm_client, standard_strategy, board_size),
            LLMGomokuAgent("Aggressive_AI", llm_client, aggressive_strategy, board_size),
            SimpleGomokuAgent("Simple_Agent")
        ]

    print("Created agents:")
    for agent in agents:
        agent_type = "LLM" if isinstance(agent, LLMGomokuAgent) else "Simple"
        strategy_type = getattr(agent, 'strategy', None)
        strategy_name = strategy_type.__class__.__name__ if strategy_type else "Basic"
        print(f"  - {agent.agent_id} ({agent_type}) with {strategy_name}")

    # Run demo game
    print(f"\n=== DEMO GAME: {agents[0].agent_id} vs {agents[1].agent_id} ===")
    try:
        demo_result = await arena.run_game(agents[0], agents[1], verbose=True)

        print(f"\nGame Result:")
        print(f"Winner: {demo_result['winner']}")
        print(f"Total moves: {demo_result['moves']}")
        print(f"Game time: {demo_result.get('total_time', 0):.2f}s")

        print(f"\nFinal Board:")
        
        # Find winning sequence if there's a winner
        winning_sequence = []
        if demo_result["winner"] and demo_result["result"] in [GameResult.BLACK_WIN, GameResult.WHITE_WIN]:
            winner_player = Player.BLACK if demo_result["result"] == GameResult.BLACK_WIN else Player.WHITE
            from .core.game_logic import GomokuGame
            game = GomokuGame(board_size)
            winning_sequence = game.find_winning_sequence(demo_result["final_board"], winner_player)

        # Draw board with winning sequence highlighted
        board_display = arena.draw_board_with_winning_sequence(demo_result["final_board"], winning_sequence)
        print(board_display)

    except Exception as e:
        print(f"Error running demo: {e}")
        if not args.no_llm:
            print("Try running with --no-llm flag for simple agents only")


def tournament_cli():
    """Run tournament CLI."""
    asyncio.run(_tournament_cli())


async def _tournament_cli():
    """Tournament command line interface."""
    parser = argparse.ArgumentParser(description='Gomoku AI Tournament')
    parser.add_argument('--board-size', type=int, default=8, help='Board size (default: 8)')
    parser.add_argument('--games-per-match', type=int, default=2, help='Games per match (default: 2)')
    parser.add_argument('--api-key', type=str, help='OpenAI API key')
    parser.add_argument('--model', type=str, default='gpt-4o-mini', help='LLM model to use')
    parser.add_argument('--simple-only', action='store_true', help='Use simple agents only')
    parser.add_argument('--huggingface', type=str, help='Use HuggingFace model')
    parser.add_argument('--hf-device', type=str, default='auto', help='HuggingFace device')
    
    args = parser.parse_args()

    print("=== GOMOKU AI TOURNAMENT ===\n")

    # Create arena
    board_size = args.board_size
    arena = GomokuArena(board_size=board_size)
    tournament = Tournament(arena)

    if args.simple_only:
        # Simple agents only
        agents = [
            SimpleGomokuAgent("Simple_Agent_1"),
            SimpleGomokuAgent("Simple_Agent_2"),
            SimpleGomokuAgent("Simple_Agent_3")
        ]
    elif args.huggingface:
        # Use HuggingFace model
        try:
            print(f"Loading HuggingFace model: {args.huggingface}")
            hf_client = create_huggingface_client(args.huggingface, device=args.hf_device)
            
            # Create agents with different strategies
            agents = [
                LLMGomokuAgent("HF_Strategic", hf_client, StandardStrategy(board_size), board_size),
                LLMGomokuAgent("HF_Aggressive", hf_client, AggressiveStrategy(board_size), board_size),
                SimpleGomokuAgent("Simple_Agent")
            ]
        except ImportError:
            print("❌ HuggingFace dependencies not installed.")
            print("Install with: pip install 'gomoku-ai[huggingface]'")
            return
        except Exception as e:
            print(f"❌ Error loading HuggingFace model: {e}")
            return
    else:
        # Create OpenAI LLM client
        api_key = args.api_key or "demo_key"
        llm_client = OpenAIGomokuClient(api_key=api_key, model=args.model)

        # Create agents with different strategies
        agents = [
            LLMGomokuAgent("Strategic_AI", llm_client, StandardStrategy(board_size), board_size),
            LLMGomokuAgent("Aggressive_AI", llm_client, AggressiveStrategy(board_size), board_size),
            SimpleGomokuAgent("Simple_Agent")
        ]

    print(f"Tournament with {len(agents)} agents:")
    for agent in agents:
        print(f"  - {agent.agent_id}")

    try:
        # Run tournament
        results = await tournament.round_robin(agents, games_per_match=args.games_per_match)

        # Display results
        print("\n=== FINAL STANDINGS ===")
        for rank, (agent_id, stats) in enumerate(results["rankings"], 1):
            print(f"{rank}. {agent_id}: {stats['points']} points "
                  f"({stats['wins']}W-{stats['losses']}L-{stats['draws']}D)")

    except Exception as e:
        print(f"Error running tournament: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tournament":
        tournament_cli()
    else:
        main_demo()