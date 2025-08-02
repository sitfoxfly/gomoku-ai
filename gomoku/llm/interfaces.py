"""LLM-specific interfaces."""

import time
from abc import ABC, abstractmethod
from typing import List, Dict, Union, Any


class LLMClient(ABC):
    """Abstract interface for LLM clients."""

    @abstractmethod
    async def complete(self, messages: Union[str, List[Dict[str, str]]]) -> str:
        """
        Send messages to LLM and return response.

        Args:
            messages: Either a simple string prompt (legacy) or a list of message dicts
                     Each message dict should have 'role' and 'content' keys:
                     - role: 'system', 'user', or 'assistant'
                     - content: The message content

        Returns:
            str: The LLM response

        Examples:
            # Simple prompt (legacy)
            await client.complete("What's the weather?")

            # Messages format (recommended)
            await client.complete([
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What's the weather?"}
            ])
        """
        pass


class LLMLoggingProxy:
    """Proxy that wraps any LLM client and automatically logs conversations."""
    
    def __init__(self, wrapped_client: LLMClient):
        """
        Args:
            wrapped_client: Any LLMClient instance
        """
        self._wrapped_client = wrapped_client
        self.llm_logs = []
    
    async def complete(self, messages: Union[str, List[Dict[str, str]]]) -> str:
        """Intercept complete() calls and log them."""
        timestamp = time.time()
        
        # Call the actual client
        response = await self._wrapped_client.complete(messages)
        
        # Log the conversation
        self.llm_logs.append({
            "timestamp": timestamp,
            "input": messages,
            "output": response,
            "model": getattr(self._wrapped_client, 'model', 'unknown'),
            "client_type": type(self._wrapped_client).__name__
        })
        
        return response
    
    def __getattr__(self, name: str) -> Any:
        """Proxy all other attributes to the wrapped client."""
        return getattr(self._wrapped_client, name)
