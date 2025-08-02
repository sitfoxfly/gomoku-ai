# Gomoku AI Framework

A comprehensive educational framework for building and testing Gomoku (Five in a Row) AI agents. This project demonstrates clean architecture principles while providing an easy-to-use platform for learning AI game development.

## 🎯 What You'll Learn

- **AI Agent Development**: Create your own intelligent game-playing agents
- **Game Theory**: Understand strategic gameplay through implementation
- **Clean Architecture**: See SOLID principles in action with a real project
- **Game Analysis**: Comprehensive logging with illegal move tracking and result codes
- **Interactive Visualization**: Rich HTML replays with move-by-move analysis
- **LLM Integration**: Use language models for game AI (OpenAI, HuggingFace)

## 🚀 Quick Start

### Installation

```bash
# Basic installation
pip install -e .

# With HuggingFace transformer support
pip install -e ".[huggingface]"

# Full development setup
pip install -e ".[huggingface,dev]"
```

### Run Your First Game

```python
import asyncio
from gomoku.agents import SimpleGomokuAgent, LLMGomokuAgent
from gomoku.arena import GomokuArena

async def main():
    # Create a game arena
    arena = GomokuArena(board_size=8)
    
    # Create two agents
    simple_agent = SimpleGomokuAgent("SimpleBot")
    ai_agent = LLMGomokuAgent("SmartBot")
    
    # Run a game
    result = await arena.run_game(simple_agent, ai_agent, verbose=True)
    print(f"Winner: {result['winner']}")

asyncio.run(main())
```

### CLI Quick Start

```bash
# Use the CLI interface
python -m gomoku --help

# List available built-in agents
python -m gomoku list

# Play a game between two built-in agents
python -m gomoku play gomoku.agents.simple_agent.SimpleGomokuAgent gomoku.agents.openai_llm_agent.LLMGomokuAgent
```

### Advanced CLI Usage

```bash
# Discover agents from local directories and list them
python -m gomoku --discover-agents ./my_agents list --detailed

# Discover agents from GitHub repositories
python -m gomoku --github-repos https://github.com/user/gomoku-agent list

# Validate all discovered agents
python -m gomoku --discover-agents ./my_agents validate

# Validate specific agent
python -m gomoku --discover-agents ./my_agents validate --agent my_agents.agent_name.AgentClass

# Play a game with verbose output and logging
python -m gomoku --discover-agents ./my_agents play my_agents.agent1.Agent1 gomoku.agents.simple_agent.SimpleGomokuAgent --verbose --log game.json

# Generate interactive HTML visualization
python -m gomoku --discover-agents ./my_agents play agent1.AgentClass agent2.AgentClass --log game.json --html
# Or convert existing JSON logs
python -m gomoku.utils json_to_html game.json -o game.html
```

## 🤖 Building Your Own Agent

### Agent Discovery System

Create external agents that the framework can automatically discover:

1. **Create an agent.json manifest:**
```json
{
    "name": "MyCustomAgent",
    "agent_class": "my_agent.MyGomokuAgent", 
    "author": "Your Name",
    "description": "A strategic Gomoku agent",
    "version": "1.0.0"
}
```

2. **Create your agent class:**
```python
# my_agent.py
from gomoku.agents.base import Agent
from gomoku.core.models import GameState
from typing import Tuple

class MyGomokuAgent(Agent):
    async def get_move(self, game_state: GameState) -> Tuple[int, int]:
        # Your strategy here
        return (row, col)
```

3. **Discover and test:**
```bash
# Discover agents from local directory and list them
python -m gomoku --discover-agents ./my_agent_folder list --detailed

# Validate your agent (after discovery)
python -m gomoku --discover-agents ./my_agent_folder validate --agent my_agent.MyGomokuAgent

# Play against built-in agents (after discovery)
python -m gomoku --discover-agents ./my_agent_folder play my_agent.MyGomokuAgent gomoku.agents.simple_agent.SimpleGomokuAgent --verbose

# Or discover from GitHub repositories
python -m gomoku --github-repos https://github.com/username/my-agent list --detailed
```

### 1. Simple Rule-Based Agent

The easiest way to start - create an agent with basic strategy:

```python
from gomoku.agents.base import Agent
from gomoku.core.models import GameState, Player
from typing import Tuple
import random

class MyFirstAgent(Agent):
    """My first custom Gomoku agent."""
    
    async def get_move(self, game_state: GameState) -> Tuple[int, int]:
        """Return (row, col) for next move."""
        
        # Find all empty positions
        empty_positions = []
        for row in range(game_state.board_size):
            for col in range(game_state.board_size):
                if game_state.board[row][col] == Player.EMPTY.value:
                    empty_positions.append((row, col))
        
        # Strategy: prefer center, then random
        center = game_state.board_size // 2
        if (center, center) in empty_positions:
            return (center, center)
        
        return random.choice(empty_positions)

# Test your agent
agent = MyFirstAgent("MyBot")
```

### 2. Strategic Agent with Pattern Recognition

Add more intelligence with pattern detection:

```python
class StrategicAgent(Agent):
    """Agent that looks for winning patterns."""
    
    async def get_move(self, game_state: GameState) -> Tuple[int, int]:
        # 1. Check if we can win this turn
        winning_move = self.find_winning_move(game_state, self.player)
        if winning_move:
            return winning_move
            
        # 2. Block opponent's winning move
        opponent = Player.BLACK if self.player == Player.WHITE else Player.WHITE
        blocking_move = self.find_winning_move(game_state, opponent)
        if blocking_move:
            return blocking_move
            
        # 3. Create threats (3 in a row)
        threat_move = self.find_threat_move(game_state)
        if threat_move:
            return threat_move
            
        # 4. Random fallback
        return self.random_move(game_state)
    
    def find_winning_move(self, state: GameState, player: Player) -> Tuple[int, int]:
        """Find a move that creates 5 in a row."""
        # Implementation: check all empty positions for potential wins
        for row in range(state.board_size):
            for col in range(state.board_size):
                if state.is_valid_move(row, col):
                    # Simulate placing piece
                    if self.would_win(state, row, col, player):
                        return (row, col)
        return None
    
    def would_win(self, state: GameState, row: int, col: int, player: Player) -> bool:
        """Check if placing a piece at (row, col) creates 5 in a row."""
        directions = [(0,1), (1,0), (1,1), (1,-1)]  # horizontal, vertical, diagonal
        
        for dx, dy in directions:
            count = 1  # count the piece we're placing
            
            # Check positive direction
            r, c = row + dx, col + dy
            while (0 <= r < state.board_size and 0 <= c < state.board_size and 
                   state.board[r][c] == player.value):
                count += 1
                r, c = r + dx, c + dy
            
            # Check negative direction
            r, c = row - dx, col - dy
            while (0 <= r < state.board_size and 0 <= c < state.board_size and 
                   state.board[r][c] == player.value):
                count += 1
                r, c = r - dx, c - dy
            
            if count >= 5:
                return True
        return False
```

### 3. LLM-Powered Agent

Create an agent that uses language models:

```python
from gomoku.llm import OpenAIGomokuClient

class MyLLMAgent(Agent):
    """Agent powered by language models."""
    
    def _setup(self):
        """Configure the LLM client."""
        self.llm_client = OpenAIGomokuClient(
            model="gpt-4o-mini",
            api_key="your_api_key"
        )
        
        self.system_prompt = """You are a Gomoku expert. Analyze the board and respond with JSON:
        {
            "reasoning": "brief explanation", 
            "move": {"row": 0, "col": 0}
        }"""
    
    async def get_move(self, game_state: GameState) -> Tuple[int, int]:
        """Get move from LLM."""
        # Format board for LLM
        board_str = self.format_board(game_state)
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Board:\\n{board_str}\\nYour move:"}
        ]
        
        response = await self.llm_client.complete_chat(messages)
        
        # Parse JSON response
        import json
        try:
            data = json.loads(response)
            return (data["move"]["row"], data["move"]["col"])
        except:
            # Fallback to random move
            return self.random_move(game_state)
```

## 🎮 Running Games

### Single Game with Visualization

```python
import asyncio
from gomoku.arena import GomokuArena
from gomoku.utils import ColorBoardFormatter

async def demo_game():
    # Create arena with colored board display
    formatter = ColorBoardFormatter(board_size=8)
    arena = GomokuArena(board_size=8, formatter=formatter)
    
    # Create your agents
    agent1 = MyFirstAgent("Bot1")
    agent2 = StrategicAgent("Bot2")
    
    # Run game with detailed output
    result = await arena.run_game(agent1, agent2, verbose=True)
    
    print(f"\\n🏆 Game Result:")
    print(f"Winner: {result['winner']}")
    print(f"Total moves: {result['moves']}")
    print(f"Game duration: {result.get('total_time', 0):.2f}s")

asyncio.run(demo_game())
```

### Multiple Games for Statistics

```python
async def test_agents():
    arena = GomokuArena(board_size=8)
    agent1 = MyFirstAgent("Random")
    agent2 = StrategicAgent("Strategic")
    
    wins = {"Random": 0, "Strategic": 0, "Draw": 0}
    
    # Play 10 games
    for game_num in range(10):
        result = await arena.run_game(agent1, agent2, verbose=False)
        
        if result['winner']:
            wins[result['winner']] += 1
        else:
            wins["Draw"] += 1
        
        print(f"Game {game_num + 1}: Winner = {result['winner'] or 'Draw'}")
    
    print(f"\\nFinal Results: {wins}")

asyncio.run(test_agents())
```


## 🛠️ Development Tools

### Testing Your Agent

```python
# Test agent behavior
def test_agent_basic():
    agent = MyFirstAgent("TestBot")
    
    # Create test game state
    from gomoku.core.models import GameState, Player
    
    state = GameState(
        board=[['.' for _ in range(8)] for _ in range(8)],
        current_player=Player.BLACK,
        move_history=[],
        board_size=8
    )
    
    # Test move generation
    move = asyncio.run(agent.get_move(state))
    assert 0 <= move[0] < 8 and 0 <= move[1] < 8
    print(f"✅ Agent returned valid move: {move}")

test_agent_basic()
```

### Agent Performance Analysis

```python
# Analyze agent performance with detailed logging
import asyncio
from gomoku import GomokuArena

async def analyze_agent():
    arena = GomokuArena(board_size=8)
    agent = MyCustomAgent("TestAgent")
    opponent = SimpleGomokuAgent("Baseline")
    
    result = await arena.run_game(agent, opponent, verbose=True)
    
    print(f"Game Result: {result['result_code']} - {result['reason']}")
    print(f"Total Moves: {result['moves']}")
    
    # Check for illegal moves
    illegal_moves = [move for move in result['game_log'] if move.get('illegal', False)]
    if illegal_moves:
        print(f"⚠️  Found {len(illegal_moves)} illegal moves")
        for move in illegal_moves:
            print(f"   Move {move['move_number']}: {move['reason']}")
    else:
        print("✅ No illegal moves detected")

asyncio.run(analyze_agent())
```

### Debugging Game States

```python
def debug_game_state(state: GameState):
    """Helper to visualize game state during development."""
    print("\\nBoard State:")
    print("   " + " ".join(f"{i}" for i in range(state.board_size)))
    
    for row_idx, row in enumerate(state.board):
        print(f"{row_idx:2d} " + " ".join(row))
    
    print(f"\\nCurrent player: {state.current_player.value}")
    print(f"Moves played: {len(state.move_history)}")
    
    if state.move_history:
        last_move = state.move_history[-1]
        print(f"Last move: {last_move.player.value} at ({last_move.row}, {last_move.col})")
```

## 🎮 Advanced CLI Features

### Agent Discovery from GitHub

```bash
# Discover agents from GitHub repositories
python -m gomoku --github-repos https://github.com/user/gomoku-agent
python -m gomoku --github-repos https://github.com/user/repo1 https://github.com/user/repo2

# Use specific branch
python -m gomoku --github-repos https://github.com/user/repo --github-branch development
```

### Game Logging & Result Tracking

The framework provides comprehensive game logging with standardized result codes:

```bash
# Play with detailed logging
python -m gomoku --discover-agents ./agents play agent1 agent2 --verbose --log game.json

# All games include:
# - Complete move history with timing
# - Illegal move detection and logging
# - LLM conversation logs (if applicable)
# - Standardized result codes (BW, WW, DR, IM, TO, EX)
```

**Game Result Codes:**
- **BW** - Black Win (5 in a row)
- **WW** - White Win (5 in a row)  
- **DR** - Draw (board full)
- **IM** - Invalid Move (illegal position)
- **TO** - Timeout (time limit exceeded)
- **EX** - Exception (agent error)

> 📋 **See [GAME_RESULT_CODES.md](GAME_RESULT_CODES.md) for complete coding scheme documentation**

### Interactive HTML Visualization

Generate rich HTML logs with move-by-move replay and illegal move tracking:

```bash
# Play and log a game with automatic HTML generation
python -m gomoku --discover-agents ./agents play agent1 agent2 --log detailed_game.json --html

# Or convert existing JSON logs to HTML
python -m gomoku.utils json_to_html detailed_game.json -o game_replay.html

# Features include:
# - Step-by-step board states with navigation
# - Move history with timing information
# - LLM conversation logs (expandable)
# - Illegal moves highlighted in red with reasons
# - Clear result display (Draw/Winner/Error)
# - Winning sequence highlights
```

### Batch Operations

```bash
# Validate specific agent
python -m gomoku validate --agent MyCustomAgent

# Show only validated agents
python -m gomoku list --validated-only

# Validate all discovered agents
python -m gomoku validate
```

## 📚 Learning Resources

### Understanding the Codebase

- **`gomoku/core/`** - Game rules, models, and logic
- **`gomoku/agents/`** - Agent implementations and base classes
- **`gomoku/discovery/`** - Dynamic agent discovery and loading system
- **`gomoku/arena/`** - Game orchestration and match management
- **`gomoku/llm/`** - Language model integrations (OpenAI, HuggingFace)
- **`gomoku/utils/`** - Utilities like board formatters and visualization
  - `json_to_html.py` - Interactive game visualization
- **`gomoku/cli.py`** - Command-line interface

### Game Strategy Tips

1. **Opening**: Control the center of the board
2. **Threats**: Create multiple attack lines simultaneously
3. **Defense**: Always block opponent's 4-in-a-row threats
4. **Forks**: Create situations with multiple winning threats
5. **Patterns**: Learn common winning patterns and formations

### Advanced Topics

- **Minimax Algorithm**: Implement tree search for optimal play
- **Neural Networks**: Train deep learning models on game data
- **Monte Carlo Tree Search**: Use MCTS for strategic planning
- **Ensemble Methods**: Combine multiple strategies

## 🤝 Contributing

Ready to contribute? Here's how:

1. **Add New Agents**: Implement novel strategies or algorithms
2. **Enhance Game Analysis**: Add game statistics and performance metrics
3. **LLM Integration**: Support additional language model providers
4. **Visualization**: Enhance board display and game analysis
5. **Documentation**: Improve examples and tutorials

## 📄 License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.

---

**Ready to build your first Gomoku AI?** Start with the simple agent example above and gradually add more sophisticated strategies. The framework handles all the game mechanics, so you can focus on creating intelligent agents! 🚀