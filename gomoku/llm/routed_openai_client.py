"""Model-routed OpenAI client that auto-configures based on model names."""

import os
import json
from pathlib import Path
from typing import Union, List, Dict, Optional
from openai import AsyncOpenAI
from openai import RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log, retry_if_exception_type
import logging
from .interfaces import LLMClient


class LLMRoutedClient(LLMClient):
    """
    OpenAI client that automatically configures endpoints, API keys, and model IDs
    based on the model name provided.

    Models in the default config:
    - OpenAI: gpt-4o, gpt-4o-mini, gpt-4, gpt-4-turbo, gpt-3.5-turbo, o1-preview, o1-mini

    Additional models can be added via external configuration files or programmatically.
    """

    # Default model configurations (can be overridden by external config)
    _DEFAULT_MODEL_CONFIGS = {
        # OpenAI models
        "gpt-4o": {
            "base_url": None,
            "api_key_env": "OPENAI_API_KEY",
            "model_id": "gpt-4o",
        },
        "gpt-4o-mini": {
            "base_url": None,
            "api_key_env": "OPENAI_API_KEY",
            "model_id": "gpt-4o-mini",
        },
        "gpt-4": {
            "base_url": None,
            "api_key_env": "OPENAI_API_KEY",
            "model_id": "gpt-4",
        },
        "gpt-4-turbo": {
            "base_url": None,
            "api_key_env": "OPENAI_API_KEY",
            "model_id": "gpt-4-turbo",
        },
        "gpt-3.5-turbo": {
            "base_url": None,
            "api_key_env": "OPENAI_API_KEY",
            "model_id": "gpt-3.5-turbo",
        },
        "o1-preview": {
            "base_url": None,
            "api_key_env": "OPENAI_API_KEY",
            "model_id": "o1-preview",
        },
        "o1-mini": {
            "base_url": None,
            "api_key_env": "OPENAI_API_KEY",
            "model_id": "o1-mini",
        },
    }

    # Actual model configurations (initialized from defaults, can be overridden)
    MODEL_CONFIGS = _DEFAULT_MODEL_CONFIGS.copy()

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 150,
        top_p: float = 1.0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        timeout: int = 30,
        **kwargs,
    ):
        """
        Initialize LLM Routed client.

        Args:
            model: Model name that determines configuration (see class docstring for supported models)
            api_key: Override API key (otherwise uses auto-detected env var)
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter (0.0-1.0)
            frequency_penalty: Frequency penalty (-2.0 to 2.0)
            presence_penalty: Presence penalty (-2.0 to 2.0)
            timeout: Request timeout in seconds
            **kwargs: Additional parameters for chat completion
        """
        self.original_model = model

        # Load instance-specific model configurations
        self.model_configs = self._load_instance_configs()

        # Auto-configure based on model name
        config = self._get_model_config(model)
        self.base_url = config.get("base_url")
        self.api_key_env = config.get("api_key_env")
        self.api_key = api_key or config.get("api_key") or (self.api_key_env and os.getenv(self.api_key_env))
        self.model = config.get("model_id") or model

        # Initialize OpenAI client
        client_kwargs = {}

        if self.api_key:
            client_kwargs["api_key"] = self.api_key

        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = AsyncOpenAI(**client_kwargs)

        # Generation parameters
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.timeout = timeout
        self.extra_kwargs = kwargs

    def _load_instance_configs(self) -> Dict[str, Dict[str, str]]:
        """
        Load model configurations for this instance from environment variable or defaults.

        Returns:
            Dict with model configurations for this instance
        """
        # Start with default configurations
        configs = self._DEFAULT_MODEL_CONFIGS.copy()

        # Check for custom config file path in environment
        config_path = os.getenv("GOMOKU_MODEL_ROUTING_CONFIG")
        if config_path:
            try:
                config_file = Path(config_path)
                if config_file.exists():
                    with config_file.open("r", encoding="utf-8") as f:
                        external_config = json.load(f)

                    # Use external config instead of defaults
                    configs = external_config
                else:
                    raise FileNotFoundError(f"Configuration file not found: {config_path}")
            except Exception as e:
                raise ValueError(f"Error loading configuration from {config_path}: {e}")

        return configs

    def _get_model_config(self, model: str) -> Dict[str, str]:
        """
        Determine provider configuration based on model name.

        Returns:
            Dict with base_url, api_key_env, and model_id
        """
        # Check if model is in our instance configurations
        if model in self.model_configs:
            return self.model_configs[model]

        # If model not found, raise an error instead of defaulting
        supported_models = list(self.model_configs.keys())
        raise ValueError(f"Unsupported model: '{model}'. Available models: {supported_models}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=1, max=10),
        retry=retry_if_exception_type((RateLimitError,)),
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.INFO),
        reraise=True,
    )
    async def _make_api_call(self, openai_messages: List[Dict[str, str]]) -> str:
        """Make the actual API call with retry logic for rate limits."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            timeout=self.timeout,
            **self.extra_kwargs,
        )
        return response.choices[0].message.content

    async def complete(self, messages: Union[str, List[Dict[str, str]]]) -> str:
        """Send messages to LLM and return response."""
        try:
            # Convert input to OpenAI messages format
            if isinstance(messages, str):
                # Legacy string prompt - add default system message
                openai_messages = [
                    {
                        "role": "system",
                        "content": "You are an expert Gomoku player. Always respond with valid JSON containing your move and reasoning.",
                    },
                    {"role": "user", "content": messages},
                ]
            else:
                # Use messages directly - user has full control
                openai_messages = messages

            content = await self._make_api_call(openai_messages)

            return content

        except Exception as e:
            raise Exception(f"LLM Routed API error: {e}")

    def get_config_info(self) -> Dict[str, str]:
        """Return configuration information for debugging."""
        return {
            "original_model": self.original_model,
            "actual_model": self.model,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
        }

    def list_supported_models(self) -> List[str]:
        """Return all supported model names for this instance."""
        return list(self.model_configs.keys())

    @classmethod
    def list_default_models(cls) -> List[str]:
        """Return all default model names (class-level)."""
        return list(cls._DEFAULT_MODEL_CONFIGS.keys())

    def is_supported_model(self, model: str) -> bool:
        """Check if a model is supported by this instance."""
        return model in self.model_configs

    @classmethod
    def is_default_model(cls, model: str) -> bool:
        """Check if a model is in the default configurations."""
        return model in cls._DEFAULT_MODEL_CONFIGS

    @classmethod
    def create_config_template(cls, config_path: str) -> None:
        """
        Create a template configuration file with default models.

        Args:
            config_path: Path where to save the template configuration file
        """
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with config_file.open("w", encoding="utf-8") as f:
            json.dump(cls._DEFAULT_MODEL_CONFIGS, f, indent=2, ensure_ascii=False)
