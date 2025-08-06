# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Installation and Setup
```bash
# Basic installation
pip install -e .

# With HuggingFace transformer support
pip install -e ".[huggingface]"

# With web interface support
pip install -e ".[web]"

# Full development setup
pip install -e ".[huggingface,web,dev]"
```

### Running and Testing
```bash
# Run the demo
python demo.py

# Run the CLI interface
python -m gomoku --help

# Discover and run agents
python -m gomoku --discover-agents ./agents play agent1 agent2

# Convert JSON logs to HTML
python -m gomoku.utils json_to_html game_log.json

# Run the web interface (agent submission system)
python -m gomoku web run --debug

# Initialize web database
python -m gomoku web init-db

# Run tests (if test directory exists)
pytest

# Code formatting and linting
black .
flake8 .
mypy .
```

## Architecture Overview

This is a modular Gomoku (Five in a Row) AI framework designed for educational purposes and AI agent development. The architecture follows clean design principles with clear separation of concerns.

### Core Components

**`gomoku/core/`** - Game engine and models
- `models.py`: Core data structures (GameState, Player, Move, GameResult) and board formatters
- `game_logic.py`: Game rules, win condition checking, and state management  
- `interfaces.py`: Abstract interfaces for extensibility (BoardFormatter)

**`gomoku/agents/`** - AI agent implementations
- `base.py`: Abstract Agent class that all agents inherit from
- `simple_agent.py`: Basic rule-based agent
- `openai_llm_agent.py`: OpenAI-powered agent using GPT models
- `hf_llm_agent.py`: HuggingFace transformer-based agent

**`gomoku/discovery/`** - Agent discovery and loading
- `agent_loader.py`: Dynamic agent discovery and loading system for external agents

**`gomoku/arena/`** - Game orchestration
- `game_arena.py`: Manages games between agents with timing, visualization, and result tracking

**`gomoku/llm/`** - Language model integrations
- `openai_client.py`: OpenAI API client wrapper
- `huggingface_client.py`: HuggingFace transformers client
- `interfaces.py`: Abstract LLM client interfaces

**`gomoku/utils/`** - Utilities and visualization
- `visualization.py`: Board formatting and display utilities (ColorBoardFormatter)
- `json_to_html.py`: Convert JSON game logs to interactive HTML visualizations
- `__main__.py`: CLI entry point for utility commands

### Key Design Patterns

1. **Strategy Pattern**: Agents implement the same interface but use different strategies
2. **Dependency Injection**: Arena accepts formatters and agents as dependencies
3. **Abstract Interfaces**: BoardFormatter and Agent base classes enable extensibility
4. **Async/Await**: All agent interactions are asynchronous to support timeouts and LLM calls

### Agent Development

All agents inherit from `Agent` base class and must implement:
- `async def get_move(self, game_state: GameState) -> Tuple[int, int]`

The framework supports:
- Rule-based agents (pattern matching, minimax, etc.)
- LLM-powered agents (OpenAI, HuggingFace)
- Hybrid approaches combining multiple strategies

### Game Flow

1. Arena creates GameState with empty board
2. Agents are assigned Player.BLACK and Player.WHITE
3. Arena calls agent.get_move() with current GameState copy
4. Arena validates move and updates GameState
5. Arena checks for win conditions (5 in a row) or draw
6. Process repeats until game ends

### Board Representation

- Board stored as List[List[str]] with "X", "O", "." for pieces
- Multiple formatter classes for different display styles (standard, compact, JSON, strategic)
- GameState includes move history, current player, and utility methods

## CLI Interface

The framework includes a comprehensive CLI for agent discovery, validation, and gameplay:

```bash
# Discover agents from local directories
python -m gomoku --discover-agents ./student_agents ./my_agents

# Discover agents from GitHub repositories
python -m gomoku --github-repos https://github.com/user/gomoku-agent

# List discovered agents
python -m gomoku list --detailed

# Validate all agents
python -m gomoku validate

# Play a game between two agents
python -m gomoku play agent1_name agent2_name --json-log game.json

# Convert game logs to interactive HTML
python -m gomoku.utils json_to_html game.json -o game.html
```

### Agent Discovery System

The `AgentLoader` class enables dynamic discovery of agents from:
- Local directories containing `agent.json` manifests
- GitHub repositories with agent implementations
- Built-in framework agents

Each external agent requires an `agent.json` manifest:
```json
{
    "name": "MyAgent",
    "agent_class": "my_agent.MyGomokuAgent",
    "author": "Student Name",
    "description": "A strategic Gomoku agent",
    "version": "1.0.0"
}
```

### Game Visualization

The framework provides rich game visualization through:
- **Interactive HTML logs**: Step-by-step game replay with LLM conversation logs
- **Color-coded boards**: Terminal visualization with highlighting
- **JSON export**: Complete game data with move history and timing

## Educational Resources

### Tutorial Notebook

The repository includes `create_llm_agent_tutorial.ipynb`, a comprehensive Jupyter notebook that teaches:
- Building LLM agents from scratch
- Understanding the game framework architecture
- Implementing strategic reasoning
- Running agent competitions
- Integration with the CLI system

### Testing Strategy

The codebase uses pytest with async support. When writing tests:
- Use `pytest-asyncio` for testing async agent methods
- Create GameState instances for testing game logic
- Mock LLM clients when testing agent behavior
- Use the AgentLoader for testing external agent discovery

## Web Interface (Agent Submission System)

The framework includes a complete web-based submission system that allows students to upload their agents and compete in automated tournaments.

### Features

**Upload Portal**
- Simple web interface for agent file uploads
- Automatic validation of agent code and structure
- Security scanning to prevent malicious code
- Real-time feedback on upload status

**Tournament System**
- Automated round-robin tournaments between all valid agents
- Background processing with progress tracking
- ELO rating system for fair ranking
- Detailed game logs and statistics

**Leaderboard & Analytics**
- Real-time rankings based on ELO ratings
- Win/loss statistics and performance metrics
- Game history and replay functionality
- Agent performance tracking over time

### Architecture

**`gomoku/web/`** - Web interface components
- `app.py`: Flask application with upload and tournament endpoints
- `models.py`: Database models for agents, tournaments, and games
- `tournament.py`: Tournament runner and ELO rating system
- `validator.py`: Security and functionality validation pipeline
- `templates/`: HTML templates for web interface

### Running the Web Interface

```bash
# Install web dependencies
pip install -e ".[web]"

# Initialize database
python -m gomoku web init-db

# Run development server
python -m gomoku web run --debug

# Run production server
python -m gomoku web run --host 0.0.0.0 --port 8000
```

### Security Features

- **Code Validation**: AST parsing to detect dangerous imports and functions
- **Sandbox Execution**: Isolated environment for running untrusted agents
- **Resource Limits**: CPU, memory, and time constraints
- **File System**: Read-only access except for logs

### Student Workflow

1. **Develop Agent**: Create Python file implementing the Agent interface
2. **Upload via Web**: Use browser to upload agent with metadata
3. **Validation**: System automatically validates code safety and functionality
4. **Tournament Entry**: Valid agents automatically enter tournaments
5. **Monitor Performance**: Track progress on leaderboard and view game replays

### Database Schema

- **Agent**: Stores uploaded agents with validation status and statistics
- **Tournament**: Tracks tournament sessions and progress
- **Game**: Individual games with move history and results

### API Endpoints

- `POST /upload`: Agent file upload with validation
- `GET /api/leaderboard`: Current rankings and statistics
- `GET /api/games/recent`: Recent game results
- `POST /tournaments/create`: Start new tournament
- `GET /api/tournaments/:id/status`: Tournament progress tracking