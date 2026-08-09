"""
main.py — Token-Sentry entry point (Groq edition).

This is the file you run to start the server:
    python -m uvicorn src.main:app --reload --port 8000

What this file does:
  1. Creates the FastAPI application
  2. Configures structured logging (terminal + file)
  3. Registers all routes (/v1/chat/completions endpoint)
  4. Adds health check endpoint (/health)
  5. Logs startup info (model, watermark settings, etc.)
"""

import logging
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import settings
from src.proxy.router import router as proxy_router


# ── Logging Setup ──────────────────────────────────────────────────────────────

def setup_logging():
    """
    Configure logging to TWO places at once:
      1. Terminal (stdout) — so you see it while the app runs
      2. logs/sentry.log  — so you can open it and review the full session

    The log FILE is cleared every time you restart the app.
    """
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "sentry.log"

    # Clear the log file from the previous session
    log_file.write_text("")

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    formatter = logging.Formatter(log_format)

    # Handler 1: Print to terminal
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Handler 2: Write to logs/sentry.log
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Reduce noise from httpx internals
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        f"📝 Logging to terminal + {log_file.resolve()}"
    )


setup_logging()
logger = logging.getLogger(__name__)


# ── App Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    # ── STARTUP ────────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("🛡️  Token-Sentry starting up")
    logger.info(f"   Environment  : {settings.env}")
    logger.info(f"   Backend      : Groq")
    logger.info(f"   Main model   : {settings.groq_main_model}")
    logger.info(f"   Summarizer   : {settings.groq_summarizer_model}")
    logger.info(f"   High watermark: {settings.token_high_watermark} tokens")
    logger.info(f"   Hot buffer   : {settings.hot_buffer_turns} turns")
    logger.info(f"   Listening on : http://0.0.0.0:{settings.port}")
    logger.info("=" * 60)

    yield  # Server runs here

    # ── SHUTDOWN ───────────────────────────────────────────────────────────────
    logger.info("🛡️  Token-Sentry shutting down. Goodbye.")


# ── FastAPI App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Token-Sentry",
    description=(
        "An intelligent LLM proxy gateway that compresses conversation history, "
        "routes intent, and reduces token costs — powered by Groq (Llama/Mixtral)."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ─────────────────────────────────────────────────────────────────────

app.include_router(proxy_router)


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    Returns current config so you can verify the right model/settings are active.
    """
    return JSONResponse({
        "status": "ok",
        "service": "token-sentry",
        "version": "0.2.0",
        "backend": "groq",
        "env": settings.env,
        "model": settings.groq_main_model,
        "watermark_tokens": settings.token_high_watermark,
    })


@app.get("/")
async def root():
    """Root endpoint — basic info for anyone who navigates to the URL."""
    return JSONResponse({
        "service": "Token-Sentry Proxy Gateway",
        "backend": "Groq (Llama / Mixtral)",
        "docs": "/docs",
        "health": "/health",
        "endpoint": "/v1/chat/completions",
        "compatible_with": "OpenAI Chat Completions API",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
    })
