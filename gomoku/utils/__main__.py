"""Entry point for gomoku.utils module commands."""

import sys
from pathlib import Path

def main():
    """Main entry point for utils module."""
    if len(sys.argv) < 2:
        print("Usage: python -m gomoku.utils <command> [args...]")
        print("Available commands:")
        print("  json_to_html <json_file> [-o output.html]  - Convert JSON to HTML")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "json_to_html":
        # Remove the command from sys.argv and run the converter
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from .json_to_html import main as json_main
        json_main()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()