"""
proxy/transformer.py — Model name mapping for Token-Sentry (Groq edition).

WHY THIS EXISTS:
  Clients (apps, scripts) may send OpenAI model names like "gpt-4o".
  We need to map those to the actual Groq model names we want to use.

  IMPORTANT: Unlike the old Gemini version, there is NO message format
  conversion needed here. Groq uses the EXACT SAME format as OpenAI:
    - role: "user" / "assistant" / "system"  (same names!)
    - content: "..."                          (same field!)
  
  So this file is now just about model name mapping + response formatting.
"""

import logging
import time
import uuid
from src.config import settings

logger = logging.getLogger(__name__)

# Map OpenAI model names → Groq model names
# Clients using "gpt-4o" or "gpt-3.5-turbo" get routed to equivalent Groq models
MODEL_MAP: dict[str, str] = {
    # OpenAI names → Groq equivalents
    "gpt-4o":              "llama-3.3-70b-versatile",
    "gpt-4o-mini":         "llama-3.1-8b-instant",
    "gpt-4":               "llama-3.3-70b-versatile",
    "gpt-3.5-turbo":       "llama-3.1-8b-instant",
    # Pass Groq model names through unchanged
    "llama-3.3-70b-versatile":  "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile":  "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant":     "llama-3.1-8b-instant",
    "mixtral-8x7b-32768":       "mixtral-8x7b-32768",
    "gemma2-9b-it":             "gemma2-9b-it",
}


def resolve_model(requested_model: str) -> str:
    """
    Map a requested model name to the actual Groq model to use.

    If the client requests "gpt-4o", we return "llama-3.3-70b-versatile".
    If the model isn't in our map, we fall back to the configured default.
    """
    resolved = MODEL_MAP.get(requested_model, settings.groq_main_model)

    if resolved != requested_model:
        logger.info(f"Model mapped: '{requested_model}' → '{resolved}'")

    return resolved


def build_openai_chunk(content: str, model: str, finish_reason: str | None = None) -> dict:
    """
    Build an OpenAI-compatible streaming chunk (SSE delta format).

    This is what we send BACK to the client — formatted exactly like
    OpenAI's streaming response.

    OpenAI streaming format:
    {
      "id": "chatcmpl-...",
      "object": "chat.completion.chunk",
      "choices": [{
        "delta": {"content": "Hello"},
        "finish_reason": null,
        "index": 0
      }]
    }
    """
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }


def build_openai_response(
    content: str, model: str, input_tokens: int, output_tokens: int
) -> dict:
    """
    Build a complete (non-streaming) OpenAI-compatible response.

    Used when stream=False is requested.
    """
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }
