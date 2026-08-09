"""
token_engine/counter.py — Token counting using tiktoken (local, no API call).

WHY THIS EXISTS:
  Before sending any payload to Groq, we need to know approximately how many
  tokens it contains. Unlike Google's approach, we use tiktoken — the same
  library OpenAI uses internally — which runs entirely LOCAL (no network call,
  no cost, instant).

  Groq uses Llama/Mixtral models which have their own tokenizers, but tiktoken
  with cl100k_base encoding gives a very close approximation (±5%) that is
  accurate enough for our watermark decisions.

  This lets us:
  1. Decide whether to trigger compression (if count > HIGH_WATERMARK)
  2. Log token usage accurately for every request
  3. Track savings after compression
"""

import logging
import tiktoken

logger = logging.getLogger(__name__)

# cl100k_base is used by GPT-4 / GPT-3.5 — it's a good approximation for
# Llama and Mixtral models too (all use similar BPE-style tokenizers)
_encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens_in_messages(messages: list[dict]) -> int:
    """
    Count the approximate number of tokens in an OpenAI-style messages array.

    Uses tiktoken locally — no network call, no API quota consumed.

    Args:
        messages: List of {"role": "user"/"assistant"/"system", "content": "..."}

    Returns:
        Approximate token count (±5% of actual Groq tokenizer).

    Example:
        messages = [
            {"role": "user", "content": "Hello, my name is Sayantan"},
            {"role": "assistant", "content": "Nice to meet you!"},
        ]
        count = count_tokens_in_messages(messages)
        # → ~15 tokens
    """
    try:
        total = 0
        for msg in messages:
            # Each message has a small overhead for role + formatting
            total += 4  # approx overhead per message (role token + separators)
            content = msg.get("content", "")
            total += len(_encoding.encode(str(content)))

        logger.debug(
            "Token count completed",
            extra={"message_count": len(messages), "total_tokens": total},
        )
        return total

    except Exception as e:
        logger.error(f"Token counting failed: {e}. Falling back to char estimate.")
        # Fallback: rough estimate (4 chars ≈ 1 token)
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4


def count_tokens_in_text(text: str) -> int:
    """
    Count tokens in a plain text string.

    Useful for counting a single message or a compressed summary card.
    """
    try:
        return len(_encoding.encode(text))
    except Exception as e:
        logger.error(f"Token counting failed for text: {e}. Using char estimate.")
        return len(text) // 4
