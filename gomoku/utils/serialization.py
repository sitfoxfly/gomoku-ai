"""JSON serialization utilities for game data."""

import json
from typing import Any, TextIO
from ..core.models import GameResult, Player


def _serialize_value(value: Any) -> Any:
    """Convert individual values to JSON-serializable format."""
    if isinstance(value, GameResult):
        return value.value
    elif isinstance(value, Player):
        return value.value
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    else:
        return value


def safe_dumps(data: Any, **kwargs) -> str:
    """Safe JSON dumps that handles Player and GameResult enums."""
    serialized_data = _serialize_value(data)
    return json.dumps(serialized_data, **kwargs)


def safe_dump(data: Any, fp: TextIO, **kwargs) -> None:
    """Safe JSON dump that handles Player and GameResult enums."""
    serialized_data = _serialize_value(data)
    return json.dump(serialized_data, fp, **kwargs)
