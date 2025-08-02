# Gomoku Game Result Coding Scheme

This document defines the standardized coding scheme for Gomoku game outcomes.

## Result Types and Codes

### Normal Game Endings

| Code | Result Type | Description | Winner | Conditions |
|------|-------------|-------------|---------|------------|
| **BW** | `BLACK_WIN` | Black player wins | Black (X) | Black gets 5 pieces in a row |
| **WW** | `WHITE_WIN` | White player wins | White (O) | White gets 5 pieces in a row |
| **DR** | `DRAW` | Game ends in draw | None | Board is completely filled, no winner |

### Illegal Move Endings

| Code | Result Type | Description | Winner | Conditions |
|------|-------------|-------------|---------|------------|
| **IM** | `INVALID_MOVE` | Invalid position attempted | Opponent | Player tries to place piece on occupied/invalid position |
| **TO** | `TIMEOUT` | Time limit exceeded | Opponent | Player exceeds time limit for move |

### Error Endings

| Code | Result Type | Description | Winner | Conditions |
|------|-------------|-------------|---------|------------|
| **EX** | `EXCEPTION` | Agent crashed | Opponent | Agent throws unhandled exception |
| **RS** | `RESIGNATION` | Agent resigned | Opponent | Agent explicitly resigns (future use) |

## Game Result Structure

Each game returns a result dictionary with the following fields:

```json
{
  "winner": "Agent1" | null,           // Winner agent ID, null for draws
  "loser": "Agent2" | null,            // Loser agent ID, null for draws  
  "result": "black_win",               // Full result enum value
  "result_code": "BW",                 // 2-letter standardized code
  "reason": "Five in a row",           // Human-readable reason
  "moves": 35,                         // Number of moves played
  "game_log": [...],                   // Detailed move-by-move log
  "final_board": [...],                // Final board state
  "move_history": "1. Black(X): ...", // Formatted move history
  "total_time": 0.5,                   // Total game duration in seconds
  "winning_sequence": [(0,0), ...]     // Winning positions (empty for non-wins)
}
```

## Game Log Structure

Each move in the `game_log` includes:

```json
{
  "move_number": 1,                    // Sequential move number
  "player": "Agent1",                  // Agent ID who made the move
  "position": [3, 4] | null,           // [row, col] position, null for timeouts
  "time": 0.15,                        // Time taken for this move in seconds
  "illegal": false | true,             // Whether this was an illegal move
  "reason": "Invalid position",        // Reason for illegal moves (optional)
  "llm_conversations": [...]           // LLM request/response logs (if applicable)
}
```

## Usage Examples

### Analyzing Results by Code

```python
from gomoku.core.models import GameResult

# Check if game ended normally
if result["result_code"] in ["BW", "WW", "DR"]:
    print("Normal game ending")

# Check for player errors
if result["result_code"] in ["IM", "TO", "EX"]:
    print(f"Game ended due to {result['loser']} error")

# Convert code back to enum
result_enum = GameResult.from_code(result["result_code"])
```

### Statistics Collection

```python
# Count outcomes by type
outcome_counts = {"BW": 0, "WW": 0, "DR": 0, "IM": 0, "TO": 0, "EX": 0}

for game in games:
    outcome_counts[game["result_code"]] += 1

print(f"Normal wins: {outcome_counts['BW'] + outcome_counts['WW']}")
print(f"Errors: {outcome_counts['IM'] + outcome_counts['TO'] + outcome_counts['EX']}")
```

### HTML Visualization

The JSON-to-HTML converter automatically handles all result types:
- **Legal moves**: Standard board position display
- **Illegal moves**: Red highlighting with ❌ icon and error reason
- **Timeouts**: Special "TIMEOUT" display with no position

## Backward Compatibility

- Existing code using `result` field continues to work
- New `result_code` field provides standardized 2-letter codes
- All illegal moves now include `illegal: true/false` field
- Game logs preserve all move information including failed attempts

## Code Integration

```python
# Using the new coding scheme
from gomoku.core.models import GameResult

# Get standardized code
code = GameResult.BLACK_WIN.get_code()  # Returns "BW"

# Convert code back to enum
result = GameResult.from_code("BW")     # Returns GameResult.BLACK_WIN

# Check game outcome types
is_normal_ending = result.result_code in ["BW", "WW", "DR"]
is_error_ending = result.result_code in ["IM", "TO", "EX"]
```