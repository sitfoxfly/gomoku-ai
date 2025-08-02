#!/usr/bin/env python3
"""Convert JSON game logs to interactive HTML format."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any


class JSONToHTMLConverter:
    """Converts JSON game logs to interactive HTML format."""
    
    def __init__(self, board_size: int, show_llm_logs: bool = True):
        self.board_size = board_size
        self.show_llm_logs = show_llm_logs
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (str(text)
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#x27;'))
    
    def _generate_board_html(self, board: List[List[str]], highlights: List[Tuple[int, int]]) -> str:
        """Generate HTML table for the board."""
        html = '<table class="gomoku-board">'
        
        # Header row with column numbers
        html += '<tr><th></th>'
        for col in range(self.board_size):
            html += f'<th>{col}</th>'
        html += '</tr>'
        
        # Board rows
        for row in range(self.board_size):
            html += f'<tr><th>{row}</th>'
            for col in range(self.board_size):
                piece = board[row][col]
                cell_class = "cell"
                
                if (row, col) in highlights:
                    cell_class += " winning"
                
                if piece == "X":
                    cell_class += " black"
                elif piece == "O":
                    cell_class += " white"
                
                html += f'<td class="{cell_class}" data-row="{row}" data-col="{col}">'
                if piece != ".":
                    html += piece
                html += '</td>'
            html += '</tr>'
        
        html += '</table>'
        return html
    
    def _format_result_banner(self, result: dict) -> str:
        """Format the result banner text based on game outcome."""
        winner = result.get('winner')
        reason = result.get('reason', 'Game completed')
        result_code = result.get('result_code', '')
        
        if winner is None:
            # Draw game
            if result_code == 'DR':
                return f"Draw - {reason}"
            else:
                return f"Game Ended - {reason}"
        else:
            # Someone won
            return f"Winner: {winner} - {reason}"
    
    def generate_html(self, game_data: Dict[str, Any]) -> str:
        """Generate complete interactive HTML from game data."""
        metadata = game_data.get('game_metadata', {})
        result = game_data.get('game_result', {})
        
        agent1_name = metadata.get('agent1', 'Agent1')
        agent2_name = metadata.get('agent2', 'Agent2')
        board_size = metadata.get('board_size', self.board_size)
        
        moves = result.get('game_log', [])
        winning_sequence = result.get('winning_sequence', [])
        
        # Create move history with board states
        board_states = []
        current_board = [['.' for _ in range(board_size)] for _ in range(board_size)]
        board_states.append([row[:] for row in current_board])  # Initial empty board
        
        for move in moves:
            # Skip illegal moves - they don't change the board state
            if move.get('illegal', False):
                # Add current board state for illegal moves (no change)
                board_states.append([row[:] for row in current_board])
            else:
                row, col = move['position']
                piece = 'X' if 'Black' in move['player'] or move['move_number'] % 2 == 1 else 'O'
                current_board[row][col] = piece
                board_states.append([row[:] for row in current_board])
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Gomoku Game Log - {agent1_name} vs {agent2_name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5 !important;
            color: #212529 !important;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white !important;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            color: #212529 !important;
        }}
        .header {{
            text-align: center;
            margin-bottom: 20px;
            padding-bottom: 20px;
            border-bottom: 2px solid #ddd;
        }}
        .game-info {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .info-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }}
        .board-container {{
            display: flex;
            gap: 20px;
            align-items: flex-start;
        }}
        .board-section {{
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .history-section {{
            flex: 1;
        }}
        .gomoku-board {{
            border-collapse: collapse;
            background: #deb887;
            border: 3px solid #8b4513;
        }}
        .gomoku-board th {{
            background: #8b4513 !important;
            color: white !important;
            padding: 5px 8px;
            font-weight: bold;
            text-align: center;
        }}
        .gomoku-board td {{
            width: 30px;
            height: 30px;
            border: 1px solid #8b4513;
            text-align: center;
            vertical-align: middle;
            font-weight: bold;
            font-size: 16px;
            cursor: default;
            position: relative;
            box-sizing: border-box;
        }}
        .cell.black {{
            background: #333 !important;
            color: white !important;
        }}
        .cell.white {{
            background: #fff !important;
            color: black !important;
        }}
        .cell.winning {{
            background: #f44336 !important;
            color: white !important;
            animation: pulse 1s infinite;
        }}
        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
            100% {{ opacity: 1; }}
        }}
        .controls {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .controls button {{
            background: #007bff !important;
            color: white !important;
            border: none;
            padding: 10px 20px;
            margin: 5px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }}
        .controls button:hover {{
            background: #0056b3 !important;
        }}
        .controls button:disabled {{
            background: #ccc !important;
            color: #666 !important;
            cursor: not-allowed;
        }}
        .move-info {{
            margin-top: 10px;
            padding: 15px;
            background: #e9ecef;
            border-radius: 5px;
        }}
        .move-list {{
            max-height: 600px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px;
            background: white;
        }}
        .move-item {{
            padding: 5px;
            cursor: pointer;
            border-radius: 3px;
        }}
        .move-item:hover {{
            background: #f0f0f0;
        }}
        .move-item.current {{
            background: #007bff !important;
            color: white !important;
        }}
        .move-item.illegal {{
            background: #f8d7da !important;
            border-left: 4px solid #dc3545;
            color: #721c24 !important;
        }}
        .move-item.illegal:hover {{
            background: #f1b0b7 !important;
        }}
        .move-item.illegal.current {{
            background: #dc3545 !important;
            color: white !important;
        }}
        .move-item.current .llm-conversation {{
            background: #f8f9fa !important;
            color: #212529 !important;
        }}
        .move-item.current .llm-input {{
            background: #e3f2fd !important;
            color: #212529 !important;
        }}
        .move-item.current .llm-output {{
            background: #f3e5f5 !important;
            color: #212529 !important;
        }}
        .move-item.current .llm-role {{
            color: #495057 !important;
        }}
        .result-banner {{
            background: #28a745 !important;
            color: white !important;
            padding: 15px;
            text-align: center;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 18px;
            font-weight: bold;
        }}
        .llm-conversation {{
            background: #f8f9fa !important;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            margin-top: 10px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
            color: #212529 !important;
        }}
        .llm-input {{
            background: #e3f2fd !important;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 10px;
            border-left: 4px solid #2196f3;
            color: #212529 !important;
        }}
        .llm-output {{
            background: #f3e5f5 !important;
            padding: 10px;
            border-radius: 5px;
            border-left: 4px solid #9c27b0;
            color: #212529 !important;
        }}
        .llm-role {{
            font-weight: bold;
            color: #495057 !important;
            margin-bottom: 5px;
        }}
        .llm-content {{
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .llm-toggle {{
            background: #6c757d;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 11px;
            margin-top: 5px;
        }}
        .llm-toggle:hover {{
            background: #5a6268;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Gomoku Game Log</h1>
            <h2>{agent1_name} vs {agent2_name}</h2>
        </div>
        
        <div class="result-banner">
            🏆 {self._format_result_banner(result)}
        </div>
        
        <div class="game-info">
            <div class="info-card">
                <h3>Game Details</h3>
                <p><strong>Total Moves:</strong> {result.get('moves', 0)}</p>
                <p><strong>Board Size:</strong> {board_size}x{board_size}</p>
                <p><strong>Total Time:</strong> {result.get('total_time', 0):.2f}s</p>
            </div>
            <div class="info-card">
                <h3>Players</h3>
                <p><strong>Black (X):</strong> {agent1_name}</p>
                <p><strong>White (O):</strong> {agent2_name}</p>
            </div>
        </div>
        
        <div class="board-container">
            <div class="board-section">
                <div id="board-display">
                    {self._generate_board_html(board_states[0] if board_states else [], [])}
                </div>
                
                <div class="controls">
                    <button id="play-btn" onclick="toggleAutoPlay()">▶️ Play</button>
                    <button id="first-btn" onclick="goToMove(0)">⏮ First</button>
                    <button id="prev-btn" onclick="previousMove()">⏪ Previous</button>
                    <button id="next-btn" onclick="nextMove()">Next ⏩</button>
                    <button id="last-btn" onclick="goToMove({len(board_states) - 1})">Last ⏭</button>
                    
                    <div class="move-info">
                        <div id="move-display">Move: 0 / {len(board_states) - 1}</div>
                        <div id="current-player">Current Position: Game Start</div>
                    </div>
                </div>
            </div>
            
            <div class="history-section">
                <h3>Move History</h3>
                <div class="move-list" id="move-list">
                    <div class="move-item current" onclick="goToMove(0)">
                        <strong>Game Start</strong><br>
                        Empty board
                    </div>
"""
        
        # Add move history
        for i, move in enumerate(moves):
            player_symbol = 'X' if 'Black' in move['player'] or (i + 1) % 2 == 1 else 'O'
            illegal_class = " illegal" if move.get('illegal', False) else ""
            
            if move.get('illegal', False):
                # Handle illegal moves
                if move['position'] is None:
                    # Timeout case
                    position_text = f"TIMEOUT - {move.get('reason', 'Unknown error')}"
                else:
                    # Invalid position case
                    position_text = f"ILLEGAL MOVE: ({move['position'][0]}, {move['position'][1]}) - {move.get('reason', 'Invalid position')}"
                    
                move_html = f"""
                    <div class="move-item{illegal_class}" onclick="goToMove({i + 1})">
                        <strong>Move {i + 1}: {player_symbol} ❌</strong><br>
                        {move['player']}<br>
                        {position_text}<br>
                        Time: {move['time']:.2f}s"""
            else:
                # Handle legal moves
                move_html = f"""
                    <div class="move-item{illegal_class}" onclick="goToMove({i + 1})">
                        <strong>Move {i + 1}: {player_symbol}</strong><br>
                        {move['player']}<br>
                        Position: ({move['position'][0]}, {move['position'][1]})<br>
                        Time: {move['time']:.2f}s"""
            
            # Add LLM conversations if available and enabled
            llm_conversations = move.get('llm_conversations', [])
            if llm_conversations and self.show_llm_logs:
                conversation_count = len(llm_conversations)
                move_html += f"""
                        <button class="llm-toggle" onclick="event.stopPropagation(); toggleLLMConversation('llm-{i}')">
                            🤖 LLM Log ({conversation_count})
                        </button>
                        <div id="llm-{i}" class="llm-conversation" style="display: none;">"""
                
                # Display each conversation
                for conv_idx, llm_data in enumerate(llm_conversations):
                    move_html += f"""
                            <div style="margin-bottom: 15px; border-bottom: 1px solid #ddd; padding-bottom: 10px;">
                                <div class="llm-role" style="color: #6c757d; font-size: 11px;">
                                    Call #{conv_idx + 1} - Model: {llm_data.get('model', 'Unknown')}
                                </div>
                                <div class="llm-input">"""
                    
                    # Format input messages
                    if isinstance(llm_data.get('input'), list):
                        for msg in llm_data['input']:
                            role = msg.get('role', 'unknown')
                            content = msg.get('content', '')
                            move_html += f"""
                                    <div class="llm-role">{role.title()}:</div>
                                    <div class="llm-content">{self._escape_html(content)}</div>"""
                    else:
                        move_html += f"""
                                    <div class="llm-role">Input:</div>
                                    <div class="llm-content">{self._escape_html(str(llm_data.get('input', '')))}</div>"""
                    
                    move_html += f"""
                                </div>
                                <div class="llm-output">
                                    <div class="llm-role">Response:</div>
                                    <div class="llm-content">{self._escape_html(llm_data.get('output', ''))}</div>
                                </div>
                            </div>"""
                
                move_html += "</div>"
            
            move_html += "</div>"
            html += move_html
        
        html += f"""
                </div>
            </div>
        </div>"""
        
        html += f"""
    </div>
    
    <script>
        const boardStates = {json.dumps(board_states)};
        const moves = {json.dumps(moves)};
        const winningSequence = {json.dumps(winning_sequence)};
        let currentMove = 0;
        let isPlaying = false;
        let playInterval = null;
        
        function updateBoard() {{
            const board = boardStates[currentMove];
            const highlights = currentMove === boardStates.length - 1 ? winningSequence : [];
            
            let html = '<table class="gomoku-board">';
            html += '<tr><th></th>';
            for (let col = 0; col < {board_size}; col++) {{
                html += '<th>' + col + '</th>';
            }}
            html += '</tr>';
            
            for (let row = 0; row < {board_size}; row++) {{
                html += '<tr><th>' + row + '</th>';
                for (let col = 0; col < {board_size}; col++) {{
                    const piece = board[row][col];
                    let cellClass = "cell";
                    
                    const isWinning = highlights.some(pos => pos[0] === row && pos[1] === col);
                    if (isWinning) {{
                        cellClass += " winning";
                    }}
                    
                    if (piece === "X") {{
                        cellClass += " black";
                    }} else if (piece === "O") {{
                        cellClass += " white";
                    }}
                    
                    html += '<td class="' + cellClass + '" data-row="' + row + '" data-col="' + col + '">';
                    if (piece !== ".") {{
                        html += piece;
                    }}
                    html += '</td>';
                }}
                html += '</tr>';
            }}
            html += '</table>';
            
            document.getElementById('board-display').innerHTML = html;
            
            // Update move info
            document.getElementById('move-display').textContent = 'Move: ' + currentMove + ' / ' + (boardStates.length - 1);
            
            let currentPlayerText = "Game Start";
            if (currentMove > 0) {{
                const move = moves[currentMove - 1];
                if (move.illegal) {{
                    if (move.position === null) {{
                        currentPlayerText = `${{move.player}} - TIMEOUT (${{move.reason || 'Unknown error'}})`;
                    }} else {{
                        const row = move.position[0];
                        const col = move.position[1];
                        currentPlayerText = `${{move.player}} - ILLEGAL MOVE (${{row}}, ${{col}}) - ${{move.reason || 'Invalid position'}}`;
                    }}
                }} else {{
                    const row = move.position && move.position[0] !== undefined ? move.position[0] : 'unknown';
                    const col = move.position && move.position[1] !== undefined ? move.position[1] : 'unknown';
                    currentPlayerText = `${{move.player}} played (${{row}}, ${{col}})`;
                }}
            }}
            document.getElementById('current-player').textContent = currentPlayerText;
            
            // Update button states
            document.getElementById('first-btn').disabled = currentMove === 0 || isPlaying;
            document.getElementById('prev-btn').disabled = currentMove === 0 || isPlaying;
            document.getElementById('next-btn').disabled = currentMove === boardStates.length - 1 || isPlaying;
            document.getElementById('last-btn').disabled = currentMove === boardStates.length - 1 || isPlaying;
            
            // Update move list
            const moveItems = document.querySelectorAll('.move-item');
            moveItems.forEach((item, index) => {{
                item.classList.toggle('current', index === currentMove);
            }});
        }}
        
        function goToMove(moveIndex) {{
            currentMove = Math.max(0, Math.min(boardStates.length - 1, moveIndex));
            updateBoard();
        }}
        
        function nextMove() {{
            if (currentMove < boardStates.length - 1) {{
                currentMove++;
                updateBoard();
            }}
        }}
        
        function previousMove() {{
            if (currentMove > 0) {{
                currentMove--;
                updateBoard();
            }}
        }}
        
        function toggleAutoPlay() {{
            if (isPlaying) {{
                stopAutoPlay();
            }} else {{
                startAutoPlay();
            }}
        }}
        
        function startAutoPlay() {{
            if (currentMove >= boardStates.length - 1) {{
                currentMove = 0; // Reset to beginning if at end
            }}
            
            isPlaying = true;
            document.getElementById('play-btn').textContent = '⏸️ Pause';
            updateBoard();
            
            playInterval = setInterval(() => {{
                if (currentMove < boardStates.length - 1) {{
                    currentMove++;
                    updateBoard();
                }} else {{
                    stopAutoPlay();
                }}
            }}, 1000); // 1 second between moves
        }}
        
        function stopAutoPlay() {{
            isPlaying = false;
            document.getElementById('play-btn').textContent = '▶️ Play';
            if (playInterval) {{
                clearInterval(playInterval);
                playInterval = null;
            }}
            updateBoard();
        }}
        
        function toggleLLMConversation(elementId) {{
            const element = document.getElementById(elementId);
            if (element.style.display === 'none') {{
                element.style.display = 'block';
            }} else {{
                element.style.display = 'none';
            }}
        }}
        
        // Keyboard navigation
        document.addEventListener('keydown', function(e) {{
            if (isPlaying && e.key !== ' ') return; // Only allow spacebar when playing
            
            switch(e.key) {{
                case 'ArrowLeft':
                    previousMove();
                    break;
                case 'ArrowRight':
                    nextMove();
                    break;
                case 'Home':
                    goToMove(0);
                    break;
                case 'End':
                    goToMove(boardStates.length - 1);
                    break;
                case ' ':
                    e.preventDefault();
                    toggleAutoPlay();
                    break;
            }}
        }});
        
        // Initialize
        updateBoard();
    </script>
</body>
</html>
"""
        return html


def main():
    """Main entry point for the JSON to HTML converter."""
    parser = argparse.ArgumentParser(description="Convert Gomoku JSON logs to interactive HTML")
    parser.add_argument("json_file", help="Path to JSON log file")
    parser.add_argument("-o", "--output", help="Output HTML file path (default: input.html)")
    parser.add_argument("--no-llm-logs", action="store_true", help="Hide LLM request-response logs")
    
    args = parser.parse_args()
    
    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"Error: JSON file not found: {json_path}", file=sys.stderr)
        sys.exit(1)
    
    # Determine output path
    if args.output:
        html_path = Path(args.output)
    else:
        html_path = json_path.with_suffix('.html')
    
    try:
        # Read JSON file
        with json_path.open('r', encoding='utf-8') as f:
            game_data = json.load(f)
        
        # Extract board size
        board_size = game_data.get('game_metadata', {}).get('board_size', 15)
        
        # Determine if LLM logs should be shown
        show_llm_logs = not args.no_llm_logs
        
        # Convert to HTML
        converter = JSONToHTMLConverter(board_size, show_llm_logs)
        html_content = converter.generate_html(game_data)
        
        # Write HTML file
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html_content, encoding='utf-8')
        
        print(f"HTML file generated: {html_path.absolute()}")
        print(f"Open in browser: file://{html_path.absolute()}")
        
    except Exception as e:
        print(f"Error converting JSON to HTML: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()