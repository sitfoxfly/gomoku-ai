#!/usr/bin/env python3
"""
Convenience script to start tournament worker.

Usage:
    python start_tournament_worker.py [--worker-id my_worker] [--db-url sqlite:///gomoku_web.db]
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from gomoku.web.tournament_worker import main

if __name__ == '__main__':
    # Set default working directory
    os.chdir(project_root)
    
    # Run the worker
    main()