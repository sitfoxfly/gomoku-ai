"""
Web interface package for Gomoku AI agent submission system.
Provides upload portal, tournament management, and leaderboards.
"""

from .app import create_app
from .models import db
from .tournament import TournamentRunner

__all__ = ['create_app', 'db', 'TournamentRunner']