"""Database models for the web submission system."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
import json
import uuid

db = SQLAlchemy()


class Agent(db.Model):
    """Represents a submitted agent."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    version = db.Column(db.String(20), default="1.0.0")
    file_path = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_valid = db.Column(db.Boolean, default=False)
    validation_error = db.Column(db.Text)
    
    # Stats
    games_played = db.Column(db.Integer, default=0)
    games_won = db.Column(db.Integer, default=0)
    games_drawn = db.Column(db.Integer, default=0)
    elo_rating = db.Column(db.Integer, default=1500)
    
    @property
    def win_rate(self) -> float:
        if self.games_played == 0:
            return 0.0
        return (self.games_won / self.games_played) * 100
    
    @property
    def games_lost(self) -> int:
        return self.games_played - self.games_won - self.games_drawn
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'author': self.author,
            'description': self.description,
            'version': self.version,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'is_valid': self.is_valid,
            'games_played': self.games_played,
            'games_won': self.games_won,
            'games_drawn': self.games_drawn,
            'games_lost': self.games_lost,
            'win_rate': self.win_rate,
            'elo_rating': self.elo_rating
        }


class Tournament(db.Model):
    """Represents a tournament between agents."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')  # pending, running, completed, failed
    total_games = db.Column(db.Integer, default=0)
    completed_games = db.Column(db.Integer, default=0)
    selected_agent_ids = db.Column(db.Text)  # JSON string of agent IDs
    
    @property
    def progress(self) -> float:
        if self.total_games == 0:
            return 0.0
        return (self.completed_games / self.total_games) * 100
    
    def get_selected_agent_ids(self):
        """Get list of selected agent IDs."""
        import json
        if self.selected_agent_ids:
            return json.loads(self.selected_agent_ids)
        return []
    
    def set_selected_agent_ids(self, agent_ids):
        """Set list of selected agent IDs."""
        import json
        self.selected_agent_ids = json.dumps(agent_ids)


class Game(db.Model):
    """Represents a single game between two agents."""
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    black_agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)
    white_agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'), nullable=False)
    
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    winner_id = db.Column(db.Integer, db.ForeignKey('agent.id'))
    result = db.Column(db.String(20))  # 'black_wins', 'white_wins', 'draw', 'error'
    move_count = db.Column(db.Integer, default=0)
    game_log_path = db.Column(db.String(500))
    game_html_path = db.Column(db.String(500))
    error_message = db.Column(db.Text)
    
    # Relationships
    tournament = db.relationship('Tournament', backref='games')
    black_agent = db.relationship('Agent', foreign_keys=[black_agent_id], backref='black_games')
    white_agent = db.relationship('Agent', foreign_keys=[white_agent_id], backref='white_games')
    winner = db.relationship('Agent', foreign_keys=[winner_id], backref='won_games')
    
    def to_dict(self):
        return {
            'id': self.id,
            'tournament_id': self.tournament_id,
            'black_agent': self.black_agent.name if self.black_agent else None,
            'white_agent': self.white_agent.name if self.white_agent else None,
            'winner': self.winner.name if self.winner else None,
            'result': self.result,
            'move_count': self.move_count,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'game_log_path': self.game_log_path,
            'game_html_path': self.game_html_path
        }


class TournamentJob(db.Model):
    """Represents a tournament job in the queue."""
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, running, completed, failed, cancelled
    worker_id = db.Column(db.String(100))  # Process/worker that claimed this job
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    last_heartbeat = db.Column(db.DateTime)  # For health monitoring
    error_message = db.Column(db.Text)
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=3)
    
    # Job configuration
    priority = db.Column(db.Integer, default=0)  # Higher = more priority
    timeout_seconds = db.Column(db.Integer, default=3600)  # 1 hour default
    
    # Relationships
    tournament = db.relationship('Tournament', backref='job')
    
    def to_dict(self):
        return {
            'id': self.id,
            'tournament_id': self.tournament_id,
            'status': self.status,
            'worker_id': self.worker_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'priority': self.priority
        }


class TournamentCheckpoint(db.Model):
    """Stores tournament progress checkpoints for crash recovery."""
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    checkpoint_type = db.Column(db.String(50), nullable=False)  # 'game_completed', 'round_completed', etc.
    checkpoint_data = db.Column(db.Text)  # JSON data about current state
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tournament = db.relationship('Tournament', backref='checkpoints')
    
    def get_data(self) -> Dict[str, Any]:
        """Get checkpoint data as dictionary."""
        if self.checkpoint_data:
            return json.loads(self.checkpoint_data)
        return {}
    
    def set_data(self, data: Dict[str, Any]):
        """Set checkpoint data from dictionary."""
        self.checkpoint_data = json.dumps(data)


class WorkerProcess(db.Model):
    """Tracks tournament worker processes for health monitoring."""
    id = db.Column(db.String(100), primary_key=True)  # Process ID or unique worker name
    hostname = db.Column(db.String(255), nullable=False)
    pid = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, inactive, crashed
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_heartbeat = db.Column(db.DateTime, default=datetime.utcnow)
    current_job_id = db.Column(db.String(36), db.ForeignKey('tournament_job.id'))
    jobs_completed = db.Column(db.Integer, default=0)
    jobs_failed = db.Column(db.Integer, default=0)
    
    # Process configuration
    max_concurrent_jobs = db.Column(db.Integer, default=1)  # Single tournament constraint
    worker_type = db.Column(db.String(50), default='tournament')
    
    # Relationships
    current_job = db.relationship('TournamentJob', backref='worker')
    
    def is_healthy(self, timeout_seconds: int = 300) -> bool:
        """Check if worker is healthy based on last heartbeat."""
        if not self.last_heartbeat:
            return False
        
        time_since_heartbeat = (datetime.utcnow() - self.last_heartbeat).total_seconds()
        return time_since_heartbeat < timeout_seconds
    
    def update_heartbeat(self):
        """Update the last heartbeat timestamp."""
        self.last_heartbeat = datetime.utcnow()
    
    def to_dict(self):
        return {
            'id': self.id,
            'hostname': self.hostname,
            'pid': self.pid,
            'status': self.status,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'current_job_id': self.current_job_id,
            'jobs_completed': self.jobs_completed,
            'jobs_failed': self.jobs_failed,
            'is_healthy': self.is_healthy()
        }