"""Main entry point for the Gomoku AI framework CLI."""

from .cli import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())