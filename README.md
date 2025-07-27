# Improved Gomoku Architecture

This repository demonstrates a well-architected Gomoku (Five in a Row) game implementation with AI agents, following SOLID principles and modern software design patterns.

## 🏗️ Architecture Overview

The new architecture addresses the issues in the original implementation:

### Before (Original)
- ❌ Circular imports between `agents.py` and `gomoku.py`
- ❌ Single responsibility violation - `agents.py` contained too many concerns
- ❌ Tight coupling making testing and extension difficult
- ❌ No strategy pattern - AI behavior hardcoded
- ❌ LLM client tightly coupled to OpenAI

### After (Improved)
- ✅ Clean modular structure with no circular dependencies
- ✅ Single responsibility principle - each module has one purpose
- ✅ Dependency injection enabling easy testing and mocking
- ✅ Strategy pattern for pluggable AI behaviors
- ✅ Interface-based design supporting multiple providers


## 🎯 Key Design Patterns

### 1. Strategy Pattern
Different AI strategies can be plugged into agents:

```python
# Create strategies
standard_strategy = StandardStrategy(board_size)
aggressive_strategy = AggressiveStrategy(board_size)

# Inject into agents
agent1 = LLMGomokuAgent("Strategic_AI", llm_client, standard_strategy)
agent2 = LLMGomokuAgent("Aggressive_AI", llm_client, aggressive_strategy)
```

### 2. Dependency Injection
Components depend on abstractions, not concrete implementations:

```python
# Arena accepts any BoardFormatter
formatter = ColorBoardFormatter(board_size)
arena = GomokuArena(board_size=board_size, formatter=formatter)

# Agent accepts any LLMClient and GameStrategy
agent = LLMGomokuAgent(agent_id, llm_client, strategy, board_size)
```

### 3. Interface Segregation
Clean interfaces define contracts:

```python
class LLMClient(ABC):
    @abstractmethod
    async def complete(self, prompt: str) -> str: pass

class GameStrategy(ABC):
    @abstractmethod
    def evaluate_position(self, state: GameState, player) -> float: pass
    @abstractmethod
    def get_candidate_moves(self, state: GameState) -> List[Tuple[int, int]]: pass
```

## 🤖 LLM Provider Support

This implementation supports multiple LLM providers:

### OpenAI API
- **Agent**: `LLMGomokuAgent`
- **Requirements**: OpenAI API key
- **Models**: GPT-3.5, GPT-4, custom OpenAI-compatible endpoints

### Hugging Face Transformers
- **Agent**: `HfGomokuAgent` 
- **Requirements**: `transformers`, `torch`, `accelerate`
- **Models**: Local inference with any HuggingFace model (default: microsoft/Phi-3.5-mini-instruct)
- **Benefits**: No API costs, offline usage, full privacy control

### Installation Options

```bash
# Basic installation (OpenAI only)
pip install -e .

# With Hugging Face support
pip install -e ".[huggingface]"

# Full development setup
pip install -e ".[huggingface,dev,docs]"
```

## 🚀 Quick Start

### Basic Usage

```python
import asyncio
from gomoku.agents import LLMGomokuAgent, HfGomokuAgent
from gomoku.arena import GomokuArena
from gomoku.utils import ColorBoardFormatter

async def main():
    # Create arena with dependency injection
    board_size = 8
    formatter = ColorBoardFormatter(board_size)
    arena = GomokuArena(board_size=board_size, formatter=formatter)
    
    # Create agents - supports both OpenAI and Hugging Face
    openai_agent = LLMGomokuAgent("Qwen-OpenAI")  # Uses OpenAI API
    hf_agent = HfGomokuAgent("Qwen-HF")           # Uses local Hugging Face models
    
    # Run game
    result = await arena.run_game(openai_agent, hf_agent, verbose=True)
    print(f"Winner: {result['winner']}")

asyncio.run(main())
```

### Tournament

```python
from gomoku.arena import Tournament

# Create tournament
tournament = Tournament(arena)
agents = [ai_agent1, ai_agent2, simple_agent]

# Run round-robin
results = await tournament.round_robin(agents, games_per_match=4)
```

## 🧪 Testing Benefits

The new architecture makes testing much easier:

```python
# Mock LLM client for testing
class MockLLMClient(LLMClient):
    async def complete(self, prompt: str) -> str:
        return '{"row": 7, "col": 7, "reasoning": "test move"}'

# Test agent with mock
mock_client = MockLLMClient()
strategy = StandardStrategy(15)
agent = LLMGomokuAgent("test", mock_client, strategy, 15)

# Test strategy in isolation
threats = strategy.analyze_threats(game_state, Player.BLACK)
```

## 🔧 Extension Examples

### Using Different LLM Providers

The framework supports multiple LLM providers:

```python
# OpenAI API (requires API key)
openai_agent = LLMGomokuAgent("OpenAI-Agent")

# Hugging Face local models (no API key needed)
hf_agent = HfGomokuAgent("HF-Agent")

# Custom LLM provider
class AnthropicClient(LLMClient):
    async def complete(self, prompt: str) -> str:
        # Implementation for Anthropic API
        pass

claude_agent = CustomAgent("Claude", AnthropicClient())
```

### Adding a New Strategy

```python
class DefensiveStrategy(GameStrategy):
    def evaluate_position(self, state: GameState, player) -> float:
        # Defensive evaluation logic
        pass
    
    def get_candidate_moves(self, state: GameState) -> List[Tuple[int, int]]:
        # Defensive move selection
        pass

# Use with existing agent
defensive_agent = LLMGomokuAgent("Defender", llm_client, DefensiveStrategy(15), 15)
```

### Adding a New Board Formatter

```python
class HTMLFormatter(BoardFormatter):
    def format_board(self, state: GameState) -> str:
        # Generate HTML representation
        pass

# Use with arena
arena = GomokuArena(board_size=15, formatter=HTMLFormatter(15))
```

## 📊 Architecture Benefits

| Aspect | Old Architecture | New Architecture |
|--------|------------------|------------------|
| **Coupling** | Tight (circular imports) | Loose (dependency injection) |
| **Testability** | Difficult | Easy (mockable interfaces) |
| **Extensibility** | Limited | High (strategy pattern) |
| **Maintainability** | Mixed responsibilities | Clear separation |
| **SOLID Principles** | Violations | Compliant |

## 🎮 Running the Examples

```bash
# Install dependencies
pip install -r requirements.txt

# For Hugging Face support (optional)
pip install -e ".[huggingface]"

# Run the main demo
python main.py

# Install as package
pip install -e .
```

## 🏆 Best Practices Demonstrated

1. **Single Responsibility Principle** - Each class has one reason to change
2. **Open/Closed Principle** - Open for extension, closed for modification
3. **Liskov Substitution Principle** - Subtypes are substitutable for base types
4. **Interface Segregation Principle** - Clients depend only on methods they use
5. **Dependency Inversion Principle** - Depend on abstractions, not concretions

This architecture serves as a template for building extensible, maintainable game AI systems.