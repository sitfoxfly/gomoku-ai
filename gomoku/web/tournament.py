"""Tournament management and execution system."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..arena.game_arena import GomokuArena
from ..core.models import GameResult
from ..utils.visualization import ColorBoardFormatter
from ..utils.json_to_html import JSONToHTMLConverter
from .models import db, Agent, Tournament, Game


class TournamentRunner:
    """Manages and executes tournaments between agents."""

    def __init__(self, upload_dir: str = "uploads", log_dir: str = "game_logs", board_size: int = 8):
        self.upload_dir = Path(upload_dir)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.board_size = board_size

        # Create arena with color formatter for better visualization
        self.arena = GomokuArena(
            board_size=board_size,
            time_limit=30.0,  # 30 second timeout per move
            formatter=ColorBoardFormatter(board_size)
        )

    async def run_tournament(self, tournament_id: int) -> bool:
        """Run a complete tournament between all valid agents."""
        print(f"Starting tournament {tournament_id}")
        tournament = Tournament.query.get(tournament_id)
        if not tournament:
            print(f"Tournament {tournament_id} not found")
            return False

        # Get selected agents or all valid agents if none selected
        selected_agent_ids = tournament.get_selected_agent_ids()
        if selected_agent_ids:
            agents = Agent.query.filter(Agent.id.in_(selected_agent_ids), Agent.is_valid==True).all()
            print(f"Found {len(agents)} selected agents for tournament {tournament_id}")
        else:
            agents = Agent.query.filter_by(is_valid=True).all()
            print(f"Found {len(agents)} valid agents for tournament {tournament_id} (no selection specified)")

        for agent in agents:
            print(f"  - Agent: {agent.name} by {agent.author}")

        if len(agents) < 2:
            print(f"Not enough agents to run tournament: {len(agents)} < 2")
            tournament.status = 'failed'
            db.session.commit()
            return False

        tournament.status = 'running'
        tournament.started_at = datetime.utcnow()

        # Calculate total games (round-robin: each agent plays every other agent)
        total_games = len(agents) * (len(agents) - 1)  # Each pair plays twice (as black/white)
        tournament.total_games = total_games
        tournament.completed_games = 0
        db.session.commit()

        # Run all games
        print(f"Starting {total_games} games...")
        for i, agent1 in enumerate(agents):
            for j, agent2 in enumerate(agents):
                if i != j:  # Don't play against self
                    # Check if tournament was cancelled
                    tournament = Tournament.query.get(tournament_id)
                    if tournament and tournament.status == 'cancelled':
                        print(f"Tournament {tournament_id} was cancelled, stopping execution")
                        return True

                    try:
                        print(f"Playing game: {agent1.name} vs {agent2.name}")
                        await self._play_game(tournament_id, agent1.id, agent2.id)
                        tournament.completed_games += 1
                        print(f"Game completed. Progress: {tournament.completed_games}/{tournament.total_games}")
                        db.session.commit()
                    except Exception as e:
                        print(f"Error in game {agent1.name} vs {agent2.name}: {e}")
                        # Continue with next game

        tournament.status = 'completed'
        tournament.completed_at = datetime.utcnow()
        db.session.commit()

        # Update agent ELO ratings
        self._update_elo_ratings(tournament_id)

        return True

    async def _play_game(self, tournament_id: int, black_agent_id: int, white_agent_id: int) -> Optional[Game]:
        """Play a single game between two agents."""
        black_agent_db = Agent.query.get(black_agent_id)
        white_agent_db = Agent.query.get(white_agent_id)

        if not black_agent_db or not white_agent_db:
            return None

        # Create game record
        game = Game(
            tournament_id=tournament_id,
            black_agent_id=black_agent_id,
            white_agent_id=white_agent_id,
            started_at=datetime.utcnow()
        )
        db.session.add(game)
        db.session.commit()

        try:
            # Load agents directly from their file paths
            black_agent = await self._load_agent_from_path(black_agent_db.file_path)
            white_agent = await self._load_agent_from_path(white_agent_db.file_path)

            if not black_agent or not white_agent:
                game.result = 'error'
                game.error_message = 'Failed to load agents'
                game.completed_at = datetime.utcnow()
                db.session.commit()
                return game

            # Create log file path
            log_filename = f"game_{game.id}_{black_agent_db.name}_vs_{white_agent_db.name}.json"
            log_path = self.log_dir / log_filename

            # Play the game
            result = await self.arena.run_game(black_agent, white_agent, verbose=False)

            # Update game record
            game.completed_at = datetime.utcnow()
            game.move_count = result.get('moves', 0)

            # Create game data structure for JSON and HTML
            game_data = {
                'game_metadata': {
                    'agent1': black_agent_db.name,
                    'agent2': white_agent_db.name,
                    'board_size': self.board_size,
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'game_id': game.id
                },
                'game_result': result
            }

            # Save game log to JSON file
            import json
            with open(log_path, 'w') as f:
                json.dump(game_data, f, indent=2)
            game.game_log_path = str(log_path)

            # Generate HTML visualization
            html_filename = f"game_{game.id}_{black_agent_db.name}_vs_{white_agent_db.name}.html"
            html_path = self.log_dir / html_filename
            try:
                converter = JSONToHTMLConverter(self.board_size, show_llm_logs=False)
                html_content = converter.generate_html(game_data)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                game.game_html_path = str(html_path)
            except Exception as e:
                print(f"Failed to generate HTML for game {game.id}: {e}")
                # Continue without HTML - not a fatal error

            # Determine winner and update stats
            game_result = result.get('result')
            if game_result == GameResult.BLACK_WIN.value:
                game.result = 'black_wins'
                game.winner_id = black_agent_id
                black_agent_db.games_won += 1
            elif game_result == GameResult.WHITE_WIN.value:
                game.result = 'white_wins'
                game.winner_id = white_agent_id
                white_agent_db.games_won += 1
            elif game_result == GameResult.DRAW.value:
                game.result = 'draw'
                # Both agents get a draw recorded
                black_agent_db.games_drawn += 1
                white_agent_db.games_drawn += 1
            else:
                game.result = 'error'
                game.error_message = result.get('reason', 'Unknown error')

            # Update game counts (only increment for completed games, not errors)
            if game_result in [GameResult.BLACK_WIN.value, GameResult.WHITE_WIN.value, GameResult.DRAW.value]:
                black_agent_db.games_played += 1
                white_agent_db.games_played += 1

            db.session.commit()
            return game

        except Exception as e:
            game.result = 'error'
            game.error_message = str(e)
            game.completed_at = datetime.utcnow()
            db.session.commit()
            return game

    async def _load_agent_from_path(self, file_path: str):
        """Load an agent directly from its file path without using discovery system."""
        try:
            import importlib.util
            import sys
            import json
            from ..agents.base import Agent

            agent_path = Path(file_path)

            # Read the agent.json to get the agent class
            with open(agent_path / 'agent.json', 'r') as f:
                manifest = json.load(f)

            agent_class_name = manifest['agent_class']
            if '.' not in agent_class_name:
                print(f"Invalid agent_class format: {agent_class_name}")
                return None

            module_name, class_name = agent_class_name.rsplit('.', 1)

            # Import the agent module directly
            module_path = agent_path / f"{module_name}.py"
            if not module_path.exists():
                print(f"Agent module file not found: {module_name}.py")
                return None

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                print(f"Could not load module spec for {module_name}")
                return None

            module = importlib.util.module_from_spec(spec)

            # Add the agent directory to sys.path temporarily so imports work
            original_path = sys.path.copy()
            sys.path.insert(0, str(agent_path))

            try:
                spec.loader.exec_module(module)

                # Get the agent class
                if not hasattr(module, class_name):
                    print(f"Agent class '{class_name}' not found in module")
                    return None

                agent_class = getattr(module, class_name)

                # Check that it inherits from Agent
                if not issubclass(agent_class, Agent):
                    print(f"Class '{class_name}' does not inherit from Agent base class")
                    return None

                # Instantiate the agent with a unique ID
                agent_name = manifest.get('name', class_name)
                agent = agent_class(agent_name)

                return agent

            finally:
                # Restore original sys.path
                sys.path[:] = original_path

        except Exception as e:
            print(f"Failed to load agent from {file_path}: {e}")
            return None

    def _update_elo_ratings(self, tournament_id: int):
        """Update ELO ratings based on tournament results."""
        games = Game.query.filter_by(tournament_id=tournament_id).all()

        # Simple ELO calculation (K-factor = 32)
        K = 32

        # Store original ratings to avoid order dependency
        agent_ratings = {}
        rating_changes = {}

        # Get all agents and their ratings at tournament start
        for game in games:
            if game.result in ['black_wins', 'white_wins']:
                black_agent = game.black_agent
                white_agent = game.white_agent

                # Store original ratings if not already stored
                if black_agent.id not in agent_ratings:
                    agent_ratings[black_agent.id] = black_agent.elo_rating
                    rating_changes[black_agent.id] = 0
                if white_agent.id not in agent_ratings:
                    agent_ratings[white_agent.id] = white_agent.elo_rating
                    rating_changes[white_agent.id] = 0

        # Calculate rating changes using original ratings
        for game in games:
            if game.result in ['black_wins', 'white_wins']:
                black_agent = game.black_agent
                white_agent = game.white_agent

                # Use original ratings for calculation
                black_original_rating = agent_ratings[black_agent.id]
                white_original_rating = agent_ratings[white_agent.id]

                # Expected scores based on original ratings
                expected_black = 1 / (1 + 10**((white_original_rating - black_original_rating) / 400))
                expected_white = 1 - expected_black

                # Actual scores
                actual_black = 1 if game.result == 'black_wins' else 0
                actual_white = 1 if game.result == 'white_wins' else 0

                # Accumulate rating changes
                rating_changes[black_agent.id] += K * (actual_black - expected_black)
                rating_changes[white_agent.id] += K * (actual_white - expected_white)

        # Apply all rating changes at once
        for agent_id, change in rating_changes.items():
            agent = Agent.query.get(agent_id)
            if agent:
                agent.elo_rating += change

        db.session.commit()

    def create_tournament(self, name: str = None, selected_agent_ids: List[int] = None) -> Tournament:
        """Create a new tournament."""
        if name is None or not name.strip():
            name = f"Tournament {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

        tournament = Tournament(name=name)

        if selected_agent_ids:
            if len(selected_agent_ids) != 2:
                raise ValueError("Tournament is restricted to exactly 2 agents")
            tournament.set_selected_agent_ids(selected_agent_ids)

        db.session.add(tournament)
        db.session.commit()
        return tournament

    def get_leaderboard(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get current leaderboard ordered by ELO rating."""
        agents = (Agent.query
                 .filter_by(is_valid=True)
                 .filter(Agent.games_played > 0)
                 .order_by(Agent.elo_rating.desc())
                 .limit(limit)
                 .all())

        return [agent.to_dict() for agent in agents]

    def get_recent_games(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most recent completed games."""
        games = (Game.query
                .filter(Game.completed_at.isnot(None))
                .order_by(Game.completed_at.desc())
                .limit(limit)
                .all())

        return [game.to_dict() for game in games]