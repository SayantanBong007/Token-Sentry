"""
config.py — Central configuration for Token-Sentry.

Reads all settings from environment variables (your .env file).
Every other module imports from here — never read env vars directly elsewhere.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    All settings are loaded from environment variables.
    Pydantic validates types and raises clear errors if something is missing.
    """

    # ── Groq AI ────────────────────────────────────────────────────────────────
    groq_api_key: str = Field(..., description="Groq API key from console.groq.com")
    groq_main_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Model used for main user conversations",
    )
    groq_summarizer_model: str = Field(
        default="llama-3.1-8b-instant",
        description="Fast model used for cheap internal summarization",
    )

    # ── Routing ────────────────────────────────────────────────────────────────
    enable_intent_routing: bool = Field(
        default=True,
        description="Route simple queries to the cheap summarizer model to save costs",
    )

    # ── Token Watermarks ───────────────────────────────────────────────────────
    token_high_watermark: int = Field(
        default=4000,
        description="Token count that triggers compression",
    )
    hot_buffer_turns: int = Field(
        default=3,
        description="Number of most-recent turns to keep raw (uncompressed)",
    )

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )

    # ── Google Cloud ───────────────────────────────────────────────────────────
    gcp_project_id: str = Field(default="", description="GCP project ID")
    gcp_region: str = Field(default="asia-south1", description="GCP region")

    # ── App ────────────────────────────────────────────────────────────────────
    env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    port: int = Field(default=8000)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Single shared instance — import this everywhere
settings = Settings()
