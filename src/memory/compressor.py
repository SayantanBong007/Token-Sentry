"""
memory/compressor.py — Summarizes old chat history into a dense JSON card.

WHY THIS EXISTS:
  As a conversation grows, passing 10,000+ tokens back and forth costs a lot
  of money and eventually hits the model's context limit. 
  
  This compressor takes the "cold" part of the conversation (older messages)
  and asks the AI to summarize them into a dense JSON state object:
  {
    "established_facts": [...],
    "active_goals": [...],
    "resolved_answers": {...}
  }

  This JSON is extremely token-efficient. We inject this summary back into
  the system prompt. The model retains all context without needing the actual
  parts of the conversation — it just doesn't have word-for-word accuracy.

  WHO DOES THE COMPRESSION:
  ──────────────────────────
  We call Groq's fast model (llama-3.1-8b-instant) to generate the summary.
  It's cheap, fast, and good at summarization. We use a different model than
  the main one to keep costs separate.
"""

import logging
from openai import AsyncOpenAI
from src.config import settings
from src.token_engine.counter import count_tokens_in_messages
from src.memory.vector_store import save_to_cold_memory
from src.metrics.tracker import increment_metric

logger = logging.getLogger(__name__)

# Single client for the summarizer
_summarizer_client = AsyncOpenAI(
    base_url=settings.primary_provider_url,
    api_key=settings.primary_api_key
)

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

Output format:
Respond ONLY with the text of the summary. Do not include introductory text.
"""

async def compress_history(session_id: str, messages: list[dict]) -> list[dict]:
    """
    Compresses an old conversation history to save tokens.
    
    1. Keeps the last N turns "hot" (uncompressed, verbatim).
    2. Takes everything older ("cold") and summarizes it into a single system message.
    3. Saves the original "cold" messages to the local Vector Database (Chroma) for future retrieval.
    4. Returns [Summary System Message, ...Hot Messages].
    """
    hot_turns = settings.hot_buffer_turns * 2  # *2 because 1 turn = 1 user msg + 1 assistant msg

    # If the history isn't long enough to compress, do nothing
    if len(messages) <= hot_turns + 2:
        return messages

    # Split into cold (to be summarized) and hot (to be kept raw)
    cold_messages = messages[:-hot_turns]
    hot_messages = messages[-hot_turns:]

    # We need to know token counts before and after to log savings
    cold_token_count = count_tokens_in_messages(cold_messages)
    hot_token_count = count_tokens_in_messages(hot_messages)

    logger.info(
        "Starting compression",
        extra={
            "session_id": session_id,
            "cold_messages": len(cold_messages),
            "hot_messages": len(hot_messages),
        },
    )

    # Save exact cold messages to VectorDB before they are lost to the summary
    await save_to_cold_memory(session_id, cold_messages)

    # Generate the dense summary
    summary_text = await _summarize(cold_messages)

    # Wrap the summary in a system message
    summary_card = {
        "role": "system",
        "content": (
            "SYSTEM MEMORY CARD (Compressed History):\n"
            f"{summary_text}\n"
            "(Note: Prior verbatim messages have been removed to save context space. "
            "Rely on this memory card for past context.)"
        )
    }

    # Final compressed history: summary card + hot buffer
    compressed = [summary_card] + hot_messages

    new_token_count = count_tokens_in_messages(compressed)
    tokens_saved = (cold_token_count + hot_token_count) - new_token_count
    
    if tokens_saved > 0:
        await increment_metric("tokens_saved", tokens_saved)
        await increment_metric("compression_runs")

    logger.info(
        "Compression complete",
        extra={
            "session_id": session_id,
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
        response = await _summarizer_client.chat.completions.create(
            model=settings.primary_summarizer_model,   # fast + cheap model
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
        return f"[Fallback Summary due to error]\n{fallback}"
