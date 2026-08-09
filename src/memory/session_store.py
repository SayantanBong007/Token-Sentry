"""
memory/session_store.py — Redis-backed conversation history storage.

WHY THIS EXISTS:
  By default, each request to Groq is stateless — it has no memory of
  previous messages. To maintain a real conversation, we need to store
  the full message history somewhere and send it with every new request.

  We use Redis for this because:
  - It's extremely fast (in-memory database)
  - Data expires automatically (we set a TTL of 24 hours)
  - It survives server restarts (unlike storing in Python variables)

  HOW SESSION STORAGE WORKS:
  ─────────────────────────
  Each conversation session has a unique key in Redis:
    "session:<session_id>"  → stores a JSON list of messages

  Example:
    Key:   "session:chat-abc123"
    Value: [
      {"role": "user",      "content": "My name is Sayantan"},
      {"role": "assistant", "content": "Nice to meet you, Sayantan!"},
      {"role": "user",      "content": "What is my name?"},
      {"role": "assistant", "content": "Your name is Sayantan."}
    ]

  Every new turn is appended. When we compress, the old messages are
  replaced with a single summary card in the history.

  GRACEFUL DEGRADATION:
  If Redis is not running, all functions return empty/no-op results.
  The proxy will still work — just without memory (passthrough mode).
"""

import json
import logging
# pyrefly: ignore [missing-import]
import redis.asyncio as aioredis
from src.config import settings

logger = logging.getLogger(__name__)

# Session TTL: conversations expire after 24 hours of inactivity
SESSION_TTL_SECONDS = 60 * 60 * 24  # 24 hours

# Key prefix for all session keys in Redis
KEY_PREFIX = "session:"

# Single persistent client shared across all requests (same pattern as tracker.py)
_redis = aioredis.from_url(settings.redis_url, decode_responses=True)


def _make_key(session_id: str) -> str:
    """Build the Redis key for a session."""
    return f"{KEY_PREFIX}{session_id}"


async def load_session(session_id: str) -> list[dict]:
    """
    Load the full conversation history for a session from Redis.

    Args:
        session_id: The unique session identifier

    Returns:
        List of message dicts, or empty list if session doesn't exist / Redis is down.

    Example:
        history = await load_session("chat-abc123")
        # → [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]
    """
    try:
        key = _make_key(session_id)
        raw = await _redis.get(key)

        if raw is None:
            logger.debug(f"No session found for: {session_id} (new session)")
            return []

        messages = json.loads(raw)
        logger.debug(
            f"Loaded session",
            extra={"session_id": session_id, "turns": len(messages)},
        )
        return messages

    except Exception as e:
        logger.error(f"Failed to load session {session_id}: {e}")
        return []


async def save_session(session_id: str, messages: list[dict]) -> bool:
    """
    Save (overwrite) the full conversation history for a session.

    This is called after every request to persist the updated history.
    The TTL is refreshed on every save.

    Args:
        session_id: The unique session identifier
        messages:   The full conversation history to save

    Returns:
        True if saved successfully, False otherwise.
    """
    try:
        key = _make_key(session_id)
        await _redis.setex(key, SESSION_TTL_SECONDS, json.dumps(messages))

        logger.debug(
            f"Saved session",
            extra={"session_id": session_id, "turns": len(messages)},
        )
        return True

    except Exception as e:
        logger.error(f"Failed to save session {session_id}: {e}")
        return False


async def clear_session(session_id: str) -> bool:
    """
    Delete a session from Redis. Useful for testing or user logout.

    Args:
        session_id: The session to delete

    Returns:
        True if deleted, False if not found or error.
    """
    try:
        key = _make_key(session_id)
        result = await _redis.delete(key)
        return result > 0

    except Exception as e:
        logger.error(f"Failed to clear session {session_id}: {e}")
        return False
