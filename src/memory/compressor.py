"""
memory/compressor.py — Conversation history compression engine.

WHY THIS EXISTS:
  When a conversation grows beyond the HIGH_WATERMARK (e.g. 4000 tokens),
  we can't just send all of it to Groq — it would be slow, expensive, and
  eventually hit Groq's context window limit.

  Solution: COMPRESS the old part of the conversation into a compact summary,
  then only send [summary + last few raw turns] to Groq.

  THE HOT BUFFER CONCEPT:
  ──────────────────────
  We NEVER compress the most recent messages. Those are the "hot buffer" —
  the part of the conversation the user is actively working in.

  Example with HOT_BUFFER_TURNS = 3:

    Full history (10 turns):
    [t1][t2][t3][t4][t5][t6][t7] │ [t8][t9][t10]
    ──────────────────────────────  ──────────────
         COLD (compress this)           HOT (keep raw)

    After compression:
    [📋 SUMMARY CARD: t1-t7 condensed] │ [t8][t9][t10]

  THE SUMMARY CARD:
  ─────────────────
  The compressed history becomes a single system message:

    {"role": "system", "content":
      "📋 Conversation Summary (earlier context):
       - User introduced themselves as Sayantan, a developer in Kolkata
       - Discussed the Token-Sentry architecture
       - User chose Groq over Google Gemini due to quota issues
       - Confirmed the proxy is working correctly
       [Compression applied at 4000 tokens]"}

  The AI sees this summary as context and can answer questions about earlier
  parts of the conversation — it just doesn't have word-for-word accuracy.

  WHO DOES THE COMPRESSION:
  ──────────────────────────
  We call Groq's fast model (llama-3.1-8b-instant) to generate the summary.
  It's cheap, fast, and good at summarization. We use a different model than
  the main one to keep costs separate.
"""

import logging
from groq import Groq
from src.config import settings
from src.token_engine.counter import count_tokens_in_messages
from src.memory.vector_store import save_to_cold_memory

logger = logging.getLogger(__name__)

# Single Groq client for the summarizer (can be same or different from main)
_summarizer_client = Groq(api_key=settings.groq_api_key)

# The prompt that instructs Llama to summarize the conversation
COMPRESSION_PROMPT = """You are a conversation memory compressor.
Your job is to read a conversation and produce a compact, factual summary.

Rules:
- Keep ALL important facts, decisions, names, numbers, and context
- Be concise but complete — this summary replaces the full history
- Write in bullet points, not paragraphs
- Prefix each bullet with a relevant emoji
- Do NOT editorialize or add opinions
- End with: [Compressed from {n} messages]

Summarize this conversation:
"""


async def compress_history(session_id: str, messages: list[dict]) -> list[dict]:
    """
    Compress a conversation history into a [summary + hot buffer] structure.

    This is the MAIN function called by the router when watermark hits RED.

    Args:
        messages: Full conversation history (all turns)

    Returns:
        Compressed list: [summary_system_message] + [last N hot turns]

    Example:
        Input:  50 messages (8000 tokens)
        Output: 1 summary card + 3 raw turns (~500 tokens total)
    """
    hot_turns = settings.hot_buffer_turns

    # Need at least more messages than the hot buffer to compress anything
    if len(messages) <= hot_turns:
        logger.info("History too short to compress — returning as-is")
        return messages

    # Split: cold history (to compress) vs hot buffer (to keep raw)
    cold_messages = messages[:-hot_turns]
    hot_messages = messages[-hot_turns:]

    cold_token_count = count_tokens_in_messages(cold_messages)
    hot_token_count = count_tokens_in_messages(hot_messages)

    logger.info(
        "Starting compression",
        extra={
            "cold_turns": len(cold_messages),
            "hot_turns": len(hot_messages),
            "cold_tokens": cold_token_count,
            "hot_tokens": hot_token_count,
        },
    )

    # Save the cold history to Vector DB before it gets summarized
    await save_to_cold_memory(session_id, cold_messages)

    # Generate the summary of cold history
    summary_text = await _summarize(cold_messages)

    # Build the summary card (a system message at the top)
    summary_card = {
        "role": "system",
        "content": (
            f"📋 Conversation Summary (earlier context — {len(cold_messages)} messages compressed):\n"
            f"{summary_text}"
        ),
    }

    # Final compressed history: summary card + hot buffer
    compressed = [summary_card] + hot_messages

    new_token_count = count_tokens_in_messages(compressed)

    logger.info(
        "Compression complete",
        extra={
            "before_tokens": cold_token_count + hot_token_count,
            "after_tokens": new_token_count,
            "reduction_pct": round((1 - new_token_count / (cold_token_count + hot_token_count)) * 100),
            "turns_before": len(messages),
            "turns_after": len(compressed),
        },
    )

    return compressed


async def _summarize(messages: list[dict]) -> str:
    """
    Call Groq's summarizer model to condense a list of messages into a summary.

    Args:
        messages: The cold history messages to summarize

    Returns:
        Summary text as a string.
        Falls back to a simple join if the API call fails.
    """
    # Format the conversation for the summarizer
    formatted_conversation = "\n".join(
        f"{msg['role'].upper()}: {msg.get('content', '')}"
        for msg in messages
    )

    prompt = COMPRESSION_PROMPT.replace("{n}", str(len(messages)))

    try:
        response = _summarizer_client.chat.completions.create(
            model=settings.groq_summarizer_model,   # llama-3.1-8b-instant (fast + cheap)
            messages=[
                {
                    "role": "user",
                    "content": f"{prompt}\n\n{formatted_conversation}"
                }
            ],
            temperature=0.2,        # low temperature = more factual, less creative
            max_tokens=512,         # summaries shouldn't be long
        )

        summary = response.choices[0].message.content or ""

        logger.debug(
            "Summary generated",
            extra={
                "input_messages": len(messages),
                "summary_chars": len(summary),
            },
        )

        return summary.strip()

    except Exception as e:
        logger.error(f"Summarization failed: {e}. Using fallback.")
        # Fallback: concatenate the last few messages as plain text
        fallback = "\n".join(
            f"{m['role']}: {m.get('content', '')[:100]}..."
            for m in messages[-5:]
        )
        return f"[Summary unavailable — last messages shown]\n{fallback}"
        return f"[Summary unavailable — last messages shown]\n{fallback}"
