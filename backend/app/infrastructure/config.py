"""Application configuration loaded from environment variables.

Uses pydantic-settings so all knobs are configurable via ``.env`` / environment
without touching code. All values have sensible zero-cost local defaults.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Provide values via a ``.env`` file (see ``.env.example``) or environment
    variables. Ollama may be unavailable at build/test time — settings are
    pure values and never connect to the network.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # --- Ollama LLM (model-agnostic) ------------------------------------- #
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        description="Base URL of the local Ollama server.",
    )
    OLLAMA_MODEL: str = Field(
        default="qwen2.5:7b-instruct-q4_k_m",
        description="Any Ollama model (qwen2.5, gemma2, deepseek-r1, llama3.1, ...).",
    )
    OLLAMA_TIMEOUT: float = Field(
        default=60.0,
        description="Request timeout in seconds for Ollama calls.",
    )

    # --- Task constraints -------------------------------------------------- #
    MAX_INPUT_LENGTH: int = Field(
        default=50_000,
        description="Maximum allowed input text length in characters.",
    )
    DEFAULT_MAX_RETRIES: int = Field(
        default=2,
        description="Bounded schema-repair retries for malformed model output.",
    )

    # --- Persistence ------------------------------------------------------- #
    DB_PATH: str = Field(
        default="data/extraction_copilot.db",
        description="SQLite database file path.",
    )

    # --- Default extraction schema ---------------------------------------- #
    # A general-purpose schema used when the client does not supply one.
    DEFAULT_SCHEMA: dict = Field(
        default={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "entities": {"type": "array", "items": {"type": "string"}},
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "negative", "neutral"],
                },
                "key_points": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary"],
        }
    )
