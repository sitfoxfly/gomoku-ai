"""Command-line interface for the Gomoku AI framework."""

import argparse
import asyncio
import json
from pathlib import Path
from .discovery import AgentLoader
from .arena.game_arena import GomokuArena
from .core.models import GameResult, Player
from .utils.json_to_html import JSONToHTMLConverter


def _serialize_game_result(result):
    """Convert game result dict to JSON-serializable format."""
    serialized = {}
    
    for key, value in result.items():
        if isinstance(value, GameResult):
            serialized[key] = value.value
        elif isinstance(value, Player):
            serialized[key] = value.value
        elif key == 'game_log':
            # Serialize the game log with all moves
            serialized[key] = []
            for move in value:
                serialized_move = {}
                for move_key, move_value in move.items():
                    if isinstance(move_value, (GameResult, Player)):
                        serialized_move[move_key] = move_value.value
                    else:
                        serialized_move[move_key] = move_value
                serialized[key].append(serialized_move)
        else:
            serialized[key] = value
    
    return serialized


def create_parser():
    """Create the argument parser."""
    parser = argparse.ArgumentParser(description="Gomoku AI Framework")
    
    # Agent discovery options
    parser.add_argument(
        "--discover-agents", 
        action="append",
        metavar="DIR",
        help="Discover agents from local directories"
    )
    parser.add_argument(
        "--github-repos", 
        action="append",
        metavar="URL",
        help="Discover agents from GitHub repositories"
    )
    parser.add_argument(
        "--github-branch", 
        default="main",
        help="Branch to use for GitHub repositories (default: main)"
    )
    
    # Game options
    parser.add_argument(
        "--agent1", 
        help="First agent name"
    )
    parser.add_argument(
        "--agent2", 
        help="Second agent name"
    )
    parser.add_argument(
        "--board-size", 
        type=int, 
        default=8,
        help="Board size (default: 8)"
    )
    parser.add_argument(
        "--time-limit", 
        type=float, 
        default=30.0,
        help="Time limit per move in seconds (default: 30.0)"
    )
    
    # Commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # List agents command
    list_parser = subparsers.add_parser("list", help="List discovered agents")
    list_parser.add_argument("--validated-only", action="store_true", help="Show only validated agents")
    list_parser.add_argument("--detailed", action="store_true", help="Show detailed information")
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate discovered agents")
    validate_parser.add_argument("--agent", help="Validate specific agent")
    
    # Play command
    play_parser = subparsers.add_parser("play", help="Play a game between two agents")
    play_parser.add_argument("agent1", help="First agent name")
    play_parser.add_argument("agent2", help="Second agent name")
    play_parser.add_argument("--verbose", action="store_true", default=True, help="Verbose output")
    play_parser.add_argument("--log", help="Generate JSON log file at specified path")
    play_parser.add_argument("--html", action="store_true", help="Automatically generate HTML visualization when JSON log is created")
    
    # Web command
    web_parser = subparsers.add_parser("web", help="Web interface commands")
    web_subparsers = web_parser.add_subparsers(dest="web_command", help="Web sub-commands")
    
    # Web run command
    web_run_parser = web_subparsers.add_parser("run", help="Run the web server")
    web_run_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    web_run_parser.add_argument("--port", type=int, default=5000, help="Port to bind to (default: 5000)")
    web_run_parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    
    # Web init-db command
    web_init_parser = web_subparsers.add_parser("init-db", help="Initialize the database")
    
    return parser


async def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Initialize agent loader
    loader = AgentLoader()
    
    try:
        # Discover agents
        total_discovered = 0
        
        if args.discover_agents:
            print(f"Discovering agents from directories: {args.discover_agents}")
            total_discovered += loader.discover_from_directories(args.discover_agents)
        
        if args.github_repos:
            print(f"Discovering agents from GitHub repositories: {args.github_repos}")
            total_discovered += loader.discover_from_github_repos(args.github_repos, args.github_branch)
        
        if total_discovered > 0:
            print(f"Discovered {total_discovered} agents")
        
        # Handle commands
        if args.command == "list":
            await handle_list_command(loader, args)
        elif args.command == "validate":
            await handle_validate_command(loader, args)
        elif args.command == "play":
            await handle_play_command(loader, args)
        elif args.command == "web":
            await handle_web_command(args)
        elif args.agent1 and args.agent2:
            # Direct play without subcommand
            await play_game(loader, args.agent1, args.agent2, args)
        else:
            # Default: list agents if any were discovered
            if total_discovered > 0:
                await handle_list_command(loader, args)
            else:
                print("No agents discovered. Use --discover-agents or --github-repos to find agents.")
                parser.print_help()
    
    finally:
        loader.cleanup()


async def handle_list_command(loader: AgentLoader, args):
    """Handle the list command."""
    agents = loader.list_agents(validated_only=args.validated_only)
    
    if not agents:
        print("No agents found.")
        return
    
    print(f"\nDiscovered Agents ({len(agents)}):")
    print("-" * 50)
    
    for metadata in agents:
        status = "✓" if metadata.validated else "?" if metadata.validation_error is None else "✗"
        print(f"{status} {metadata.name}")
        
        if args.detailed:
            print(f"    Display Name: {metadata.display_name}")
            print(f"    Author: {metadata.author or 'Unknown'}")
            print(f"    Version: {metadata.version or 'Unknown'}")
            print(f"    Description: {metadata.description or 'No description'}")
            print(f"    Agent Class: {metadata.agent_class}")
            print(f"    Source: {metadata.source_type} ({metadata.source_path})")
            if metadata.validation_error:
                print(f"    Error: {metadata.validation_error}")
            print()


async def handle_validate_command(loader: AgentLoader, args):
    """Handle the validate command."""
    if args.agent:
        # Validate specific agent
        if args.agent not in loader.discovered_agents:
            print(f"Agent '{args.agent}' not found.")
            return
        
        print(f"Validating agent: {args.agent}")
        success = loader.validate_agent(args.agent)
        metadata = loader.get_agent_info(args.agent)
        
        if success:
            print("✓ Validation successful")
        else:
            print(f"✗ Validation failed: {metadata.validation_error}")
    else:
        # Validate all agents
        print("Validating all agents...")
        results = loader.validate_all_agents()
        
        successful = sum(1 for success in results.values() if success)
        total = len(results)
        
        print(f"\nValidation Results: {successful}/{total} successful")
        print("-" * 40)
        
        for agent_name, success in results.items():
            status = "✓" if success else "✗"
            print(f"{status} {agent_name}")
            
            if not success:
                metadata = loader.get_agent_info(agent_name)
                if metadata and metadata.validation_error:
                    print(f"    Error: {metadata.validation_error}")


async def handle_play_command(loader: AgentLoader, args):
    """Handle the play command."""
    await play_game(loader, args.agent1, args.agent2, args)


def parse_agent_spec(agent_spec: str) -> tuple[str, str]:
    """Parse agent specification in format 'agent_name' or 'agent_name:custom_name'."""
    if ':' in agent_spec:
        agent_name, instance_id = agent_spec.split(':', 1)
        return agent_name.strip(), instance_id.strip()
    else:
        return agent_spec.strip(), None


async def handle_web_command(args):
    """Handle web interface commands."""
    try:
        from .web.app import create_app
        from .web.models import db
    except ImportError as e:
        print("Web interface not available. Install with: pip install flask flask-sqlalchemy")
        print(f"Import error: {e}")
        return
    
    if args.web_command == "run":
        print(f"Starting web server at http://{args.host}:{args.port}")
        if args.debug:
            print("Running in debug mode")
        
        app = create_app()
        
        # Initialize database if it doesn't exist
        with app.app_context():
            db.create_all()
            print("Database initialized")
        
        app.run(host=args.host, port=args.port, debug=args.debug)
        
    elif args.web_command == "init-db":
        app = create_app()
        with app.app_context():
            db.create_all()
            print("Database initialized successfully!")
    else:
        print("Web command required. Use 'run' or 'init-db'")


async def play_game(loader: AgentLoader, agent1_spec: str, agent2_spec: str, args):
    """Play a game between two agents."""
    try:
        agent1_name, agent1_id = parse_agent_spec(agent1_spec)
        agent2_name, agent2_id = parse_agent_spec(agent2_spec)
        
        print(f"Loading agents: {agent1_spec} vs {agent2_spec}")
        
        agent1 = loader.get_agent(agent1_name, agent1_id)
        agent2 = loader.get_agent(agent2_name, agent2_id)
        
        arena = GomokuArena(
            board_size=args.board_size,
            time_limit=args.time_limit
        )
        
        print(f"Starting game: {agent1.agent_id} (Black) vs {agent2.agent_id} (White)")
        print(f"Board size: {args.board_size}x{args.board_size}")
        print(f"Time limit: {args.time_limit}s per move")
        print("-" * 50)
        
        result = await arena.run_game(agent1, agent2, verbose=getattr(args, 'verbose', True))
        
        print("-" * 50)
        print("Game Result:")
        print(f"Winner: {result['winner']}")
        print(f"Reason: {result['reason']}")
        print(f"Moves: {result['moves']}")
        if 'total_time' in result:
            print(f"Total time: {result['total_time']:.2f}s")
        
        # Generate JSON log if requested
        if hasattr(args, 'log') and args.log:
            try:
                # Prepare complete game data for JSON with proper serialization
                game_data = {
                    "game_metadata": {
                        "agent1": agent1_spec,
                        "agent2": agent2_spec,
                        "board_size": args.board_size,
                        "time_limit": args.time_limit,
                        "timestamp": __import__('time').time()
                    },
                    "game_result": _serialize_game_result(result)
                }
                
                json_path = Path(args.log)
                json_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Write as JSON
                with json_path.open('w', encoding='utf-8') as f:
                    json.dump(game_data, f, indent=2)
                
                print(f"JSON log saved to: {json_path.absolute()}")
                
                # Generate HTML if requested
                if hasattr(args, 'html') and args.html:
                    try:
                        html_path = json_path.with_suffix('.html')
                        # Use board size from game metadata (same as console version)
                        board_size = game_data.get('game_metadata', {}).get('board_size', args.board_size)
                        converter = JSONToHTMLConverter(board_size, show_llm_logs=True)
                        html_content = converter.generate_html(game_data)
                        
                        html_path.write_text(html_content, encoding='utf-8')
                        print(f"HTML visualization saved to: {html_path.absolute()}")
                        print(f"Open in browser: file://{html_path.absolute()}")
                    except Exception as html_error:
                        print(f"Error generating HTML: {html_error}")
                        print(f"You can still convert manually with: python -m gomoku.utils json_to_html {json_path}")
                else:
                    print(f"Convert to HTML with: python -m gomoku.utils json_to_html {json_path}")
                
            except Exception as e:
                print(f"Error generating JSON log: {e}")
        
    except Exception as e:
        print(f"Error running game: {e}")


if __name__ == "__main__":
    asyncio.run(main())