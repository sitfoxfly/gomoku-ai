#!/usr/bin/env python3
"""Tournament worker process for executing tournaments in background."""

import asyncio
import logging
import os
import signal
import socket
import sys
import time
import traceback
import atexit
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gomoku.web.models import db, Agent, Tournament, TournamentJob, TournamentCheckpoint, WorkerProcess
from gomoku.web.job_manager import JobManager
from gomoku.arena.game_arena import GomokuArena
from gomoku.core.models import GameResult
from gomoku.utils.visualization import ColorBoardFormatter
from gomoku.utils.json_to_html import JSONToHTMLConverter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('tournament_worker.log')
    ]
)
logger = logging.getLogger(__name__)


class TournamentWorker:
    """Worker process for executing tournaments with crash recovery."""
    
    def __init__(self, worker_id: Optional[str] = None, db_url: str = 'sqlite:///gomoku_web.db'):
        self.worker_id = worker_id or f"worker_{socket.gethostname()}_{os.getpid()}"
        self.db_url = db_url
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        
        # Worker state
        self.running = True
        self.current_job = None
        self.job_manager = JobManager()
        
        # Async resources
        self.event_loop = None
        self._async_cleanup_registered = False
        
        # Tournament execution
        self.board_size = 8
        self.arena = GomokuArena(
            board_size=self.board_size,
            time_limit=30.0,
            formatter=ColorBoardFormatter(self.board_size)
        )
        
        # Paths
        self.upload_dir = Path('uploads')
        self.log_dir = Path('game_logs')
        self.log_dir.mkdir(exist_ok=True)
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        self._cleanup_async_resources()
    
    def start(self):
        """Start the worker process."""
        logger.info(f"Starting tournament worker {self.worker_id} on {self.hostname}:{self.pid}")
        
        try:
            # Initialize async resources
            self._setup_async_resources()
            
            # Initialize Flask app context for database access
            from gomoku.web.app import create_app
            app = create_app({'SQLALCHEMY_DATABASE_URI': self.db_url})
            
            with app.app_context():
                # Register worker in database
                self._register_worker()
                
                # Main work loop
                self._work_loop()
                
        except Exception as e:
            logger.error(f"Worker startup failed: {e}")
            logger.error(traceback.format_exc())
            sys.exit(1)
        finally:
            # Cleanup on shutdown
            self._cleanup_async_resources()
            try:
                with app.app_context():
                    self._cleanup_worker()
            except:
                pass
    
    def _register_worker(self):
        """Register this worker in the database."""
        try:
            # Remove any existing worker with same ID
            existing_worker = WorkerProcess.query.get(self.worker_id)
            if existing_worker:
                db.session.delete(existing_worker)
            
            # Create new worker record
            worker = WorkerProcess(
                id=self.worker_id,
                hostname=self.hostname,
                pid=self.pid,
                status='active',
                max_concurrent_jobs=1,  # Single tournament constraint
                worker_type='tournament'
            )
            
            db.session.add(worker)
            db.session.commit()
            
            logger.info(f"Registered worker {self.worker_id}")
            
        except Exception as e:
            logger.error(f"Error registering worker: {e}")
            raise
    
    def _cleanup_worker(self):
        """Clean up worker record on shutdown."""
        try:
            worker = WorkerProcess.query.get(self.worker_id)
            if worker:
                worker.status = 'inactive'
                worker.current_job_id = None
                db.session.commit()
            
            logger.info(f"Cleaned up worker {self.worker_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up worker: {e}")
    
    def _setup_async_resources(self):
        """Setup async event loop and resources."""
        try:
            # Create a new event loop for this worker
            self.event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.event_loop)
            
            # Register cleanup handler
            if not self._async_cleanup_registered:
                atexit.register(self._cleanup_async_resources)
                self._async_cleanup_registered = True
            
            logger.info("Async resources initialized")
            
        except Exception as e:
            logger.error(f"Error setting up async resources: {e}")
    
    def _cleanup_async_resources(self):
        """Clean up async resources gracefully."""
        try:
            if self.event_loop and not self.event_loop.is_closed():
                logger.info("Cleaning up async resources...")
                
                # Cancel all pending tasks
                pending = asyncio.all_tasks(self.event_loop)
                for task in pending:
                    task.cancel()
                
                # Wait for tasks to be cancelled and close the loop
                if pending:
                    self.event_loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                
                # Close the event loop
                self.event_loop.close()
                self.event_loop = None
                logger.info("Async resources cleaned up successfully")
                
        except Exception as e:
            logger.error(f"Error cleaning up async resources: {e}")
    
    def _work_loop(self):
        """Main work loop - polls for jobs and executes them."""
        heartbeat_interval = 30  # 30 seconds
        poll_interval = 5  # 5 seconds
        last_heartbeat = 0
        
        logger.info("Starting work loop...")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Update heartbeat
                if current_time - last_heartbeat >= heartbeat_interval:
                    self._update_heartbeat()
                    last_heartbeat = current_time
                
                # Check for new jobs
                if not self.current_job:
                    self.current_job = self.job_manager.get_next_job(self.worker_id)
                    
                    if self.current_job:
                        logger.info(f"Picked up job {self.current_job.id} for tournament {self.current_job.tournament_id}")
                        self._execute_tournament_job(self.current_job)
                        self.current_job = None
                    else:
                        # No jobs available, sleep and continue
                        time.sleep(poll_interval)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"Error in work loop: {e}")
                logger.error(traceback.format_exc())
                time.sleep(poll_interval)
        
        logger.info("Work loop ended")
    
    def _update_heartbeat(self):
        """Update worker heartbeat."""
        try:
            worker = WorkerProcess.query.get(self.worker_id)
            if worker:
                worker.update_heartbeat()
                db.session.commit()
            
            # Also update job heartbeat if we have one
            if self.current_job:
                self.job_manager.update_job_heartbeat(self.current_job.id)
                
        except Exception as e:
            logger.error(f"Error updating heartbeat: {e}")
    
    def _execute_tournament_job(self, job: TournamentJob):
        """Execute a tournament job with checkpointing and recovery."""
        logger.info(f"Starting execution of job {job.id} for tournament {job.tournament_id}")
        
        try:
            # Get tournament
            tournament = Tournament.query.get(job.tournament_id)
            if not tournament:
                self.job_manager.complete_job(job.id, False, "Tournament not found")
                return
            
            # Update tournament status
            tournament.status = 'running'
            tournament.started_at = datetime.utcnow()
            db.session.commit()
            
            # Check for existing checkpoints (recovery)
            checkpoint = self._get_latest_checkpoint(job.tournament_id)
            if checkpoint:
                logger.info(f"Found checkpoint for tournament {job.tournament_id}, attempting recovery")
                success = self._resume_tournament_from_checkpoint(tournament, checkpoint)
            else:
                logger.info(f"No checkpoint found, starting tournament {job.tournament_id} from beginning")
                success = self._run_tournament_from_start(tournament)
            
            # Complete job
            if success:
                tournament.status = 'completed'
                tournament.completed_at = datetime.utcnow()
                self.job_manager.complete_job(job.id, True)
                logger.info(f"Tournament {job.tournament_id} completed successfully")
            else:
                tournament.status = 'failed'
                tournament.completed_at = datetime.utcnow()
                self.job_manager.complete_job(job.id, False, "Tournament execution failed")
                logger.error(f"Tournament {job.tournament_id} failed")
            
            db.session.commit()
            
        except Exception as e:
            error_msg = f"Tournament execution error: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            # Mark job as failed
            self.job_manager.complete_job(job.id, False, error_msg)
            
            # Mark tournament as failed
            tournament = Tournament.query.get(job.tournament_id)
            if tournament:
                tournament.status = 'failed'
                tournament.completed_at = datetime.utcnow()
                db.session.commit()
    
    def _get_latest_checkpoint(self, tournament_id: int) -> Optional[TournamentCheckpoint]:
        """Get the latest checkpoint for a tournament."""
        return (TournamentCheckpoint.query
                .filter_by(tournament_id=tournament_id)
                .order_by(TournamentCheckpoint.created_at.desc())
                .first())
    
    def _create_checkpoint(self, tournament_id: int, checkpoint_type: str, data: dict):
        """Create a progress checkpoint."""
        try:
            checkpoint = TournamentCheckpoint(
                tournament_id=tournament_id,
                checkpoint_type=checkpoint_type,
                checkpoint_data=data
            )
            checkpoint.set_data(data)
            
            db.session.add(checkpoint)
            db.session.commit()
            
            logger.debug(f"Created checkpoint {checkpoint_type} for tournament {tournament_id}")
            
        except Exception as e:
            logger.error(f"Error creating checkpoint: {e}")
    
    def _resume_tournament_from_checkpoint(self, tournament: Tournament, checkpoint: TournamentCheckpoint) -> bool:
        """Resume tournament execution from a checkpoint."""
        try:
            checkpoint_data = checkpoint.get_data()
            logger.info(f"Resuming tournament {tournament.id} from checkpoint: {checkpoint.checkpoint_type}")
            
            # Get agents
            selected_agent_ids = tournament.get_selected_agent_ids()
            if selected_agent_ids:
                agents = Agent.query.filter(Agent.id.in_(selected_agent_ids), Agent.is_valid==True).all()
            else:
                agents = Agent.query.filter_by(is_valid=True).all()
            
            if len(agents) < 2:
                logger.error(f"Not enough agents for tournament {tournament.id}")
                return False
            
            # Resume from checkpoint
            completed_matchups = set(checkpoint_data.get('completed_matchups', []))
            
            # Run remaining matchups
            total_matchups = len(agents) * (len(agents) - 1)  # Round-robin
            
            for i, agent1 in enumerate(agents):
                for j, agent2 in enumerate(agents):
                    if i != j:  # Don't play against self
                        matchup_id = f"{agent1.id}_vs_{agent2.id}"
                        
                        if matchup_id in completed_matchups:
                            logger.debug(f"Skipping completed matchup: {agent1.name} vs {agent2.name}")
                            continue
                        
                        # Check if we should continue running
                        if not self.running:
                            logger.info("Worker shutdown requested during tournament")
                            return False
                        
                        # Play the game
                        success = self.event_loop.run_until_complete(self._play_tournament_game(tournament.id, agent1.id, agent2.id))
                        if not success:
                            logger.error(f"Game failed: {agent1.name} vs {agent2.name}")
                            continue
                        
                        # Add to completed matchups
                        completed_matchups.add(matchup_id)
                        
                        # Update tournament progress
                        tournament.completed_games = len(completed_matchups)
                        db.session.commit()
                        
                        # Create checkpoint every 10 games
                        if len(completed_matchups) % 10 == 0:
                            self._create_checkpoint(tournament.id, 'games_progress', {
                                'completed_matchups': list(completed_matchups),
                                'total_matchups': total_matchups,
                                'completed_games': tournament.completed_games
                            })
            
            # Update ELO ratings
            self._update_elo_ratings(tournament.id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error resuming tournament from checkpoint: {e}")
            return False
    
    def _run_tournament_from_start(self, tournament: Tournament) -> bool:
        """Run tournament from the beginning."""
        try:
            # Get agents
            selected_agent_ids = tournament.get_selected_agent_ids()
            if selected_agent_ids:
                agents = Agent.query.filter(Agent.id.in_(selected_agent_ids), Agent.is_valid==True).all()
            else:
                agents = Agent.query.filter_by(is_valid=True).all()
            
            if len(agents) < 2:
                logger.error(f"Not enough agents for tournament {tournament.id}")
                return False
            
            logger.info(f"Starting tournament with {len(agents)} agents")
            
            # Calculate total games and update tournament
            total_games = len(agents) * (len(agents) - 1)  # Round-robin
            tournament.total_games = total_games
            tournament.completed_games = 0
            db.session.commit()
            
            # Create initial checkpoint
            self._create_checkpoint(tournament.id, 'tournament_started', {
                'agent_ids': [agent.id for agent in agents],
                'total_games': total_games,
                'started_at': datetime.utcnow().isoformat()
            })
            
            completed_matchups = set()
            
            # Run all games (round-robin)
            for i, agent1 in enumerate(agents):
                for j, agent2 in enumerate(agents):
                    if i != j:  # Don't play against self
                        # Check if we should continue running
                        if not self.running:
                            logger.info("Worker shutdown requested during tournament")
                            return False
                        
                        # Play the game
                        success = self.event_loop.run_until_complete(self._play_tournament_game(tournament.id, agent1.id, agent2.id))
                        if not success:
                            logger.error(f"Game failed: {agent1.name} vs {agent2.name}")
                            continue
                        
                        # Track progress
                        matchup_id = f"{agent1.id}_vs_{agent2.id}"
                        completed_matchups.add(matchup_id)
                        
                        tournament.completed_games += 1
                        db.session.commit()
                        
                        logger.info(f"Tournament progress: {tournament.completed_games}/{tournament.total_games} games")
                        
                        # Create checkpoint every 10 games
                        if tournament.completed_games % 10 == 0:
                            self._create_checkpoint(tournament.id, 'games_progress', {
                                'completed_matchups': list(completed_matchups),
                                'total_matchups': total_games,
                                'completed_games': tournament.completed_games
                            })
            
            # Update ELO ratings
            self._update_elo_ratings(tournament.id)
            
            # Final checkpoint
            self._create_checkpoint(tournament.id, 'tournament_completed', {
                'completed_matchups': list(completed_matchups),
                'total_matchups': total_games,
                'completed_games': tournament.completed_games,
                'completed_at': datetime.utcnow().isoformat()
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Error running tournament: {e}")
            return False
    
    async def _play_tournament_game(self, tournament_id: int, black_agent_id: int, white_agent_id: int) -> bool:
        """Play a single game between two agents."""
        try:
            from gomoku.web.tournament import TournamentRunner
            runner = TournamentRunner()
            
            # Use existing game playing logic
            game = await runner._play_game(tournament_id, black_agent_id, white_agent_id)
            return game is not None
            
        except Exception as e:
            logger.error(f"Error playing game: {e}")
            return False
    
    def _update_elo_ratings(self, tournament_id: int):
        """Update ELO ratings based on tournament results."""
        try:
            from gomoku.web.tournament import TournamentRunner
            runner = TournamentRunner()
            runner._update_elo_ratings(tournament_id)
            logger.info(f"Updated ELO ratings for tournament {tournament_id}")
        except Exception as e:
            logger.error(f"Error updating ELO ratings: {e}")


def main():
    """Main entry point for the tournament worker."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Tournament Worker Process')
    parser.add_argument('--worker-id', help='Unique worker ID')
    parser.add_argument('--db-url', default='sqlite:///gomoku_web.db', help='Database URL')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    
    args = parser.parse_args()
    
    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    
    # Create and start worker
    worker = TournamentWorker(args.worker_id, args.db_url)
    worker.start()


if __name__ == '__main__':
    main()