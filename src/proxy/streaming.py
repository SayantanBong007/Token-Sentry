"""
proxy/streaming.py — Stream Groq responses back to the client in OpenAI SSE format.

WHY THIS EXISTS:
  Streaming means the user sees words appearing one-by-one as the model generates them,
  rather than waiting for the entire response to finish.

  Groq's SDK is fully OpenAI-compatible, so streaming works the same way:
  1. Call groq.chat.completions.create(..., stream=True)
  2. Receive chunks as they arrive
  3. Forward each chunk to the client as an SSE event
  4. Send data: [DONE] to signal end of stream

  The protocol used is SSE (Server-Sent Events):
      data: {"choices":[{"delta":{"content":"Hello"},...}]}
      data: {"choices":[{"delta":{"content":" there"},...}]}
      data: [DONE]
"""

import json
import logging
from groq import Groq
from src.config import settings
from src.proxy.transformer import build_openai_chunk, build_openai_response
from src.token_engine.counter import count_tokens_in_text

logger = logging.getLogger(__name__)

# Single shared Groq client — reused for all requests
_groq_client = Groq(api_key=settings.groq_api_key)


async def stream_groq_response(
    messages: list[dict],
    model_name: str,
    session_id: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
):
    """
    Stream a Groq response back in OpenAI SSE format.

    This is an ASYNC GENERATOR — it yields one SSE line at a time.
    FastAPI's StreamingResponse consumes this generator and sends
    each chunk to the client as soon as it arrives.

    Args:
        messages:    The conversation history (OpenAI format — no conversion needed!)
        model_name:  Resolved Groq model name
        session_id:  For logging/tracing
        temperature: Sampling temperature (0=deterministic, 1=creative)
        max_tokens:  Optional max output token limit

    Yields:
        Strings in SSE format: "data: {...json...}\\n\\n"
    """
    output_text_buffer = []
    chunk_count = 0

    logger.info(
        "Starting Groq stream",
        extra={
            "session_id": session_id,
            "model": model_name,
            "input_turns": len(messages),
        },
    )

    try:
        # Call Groq with streaming enabled
        # Groq uses the exact same API shape as OpenAI — messages pass through unchanged
        stream = _groq_client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        for chunk in stream:
            # Extract the text delta from this chunk
            delta = chunk.choices[0].delta
            chunk_text = delta.content or ""

            if chunk_text:
                output_text_buffer.append(chunk_text)
                chunk_count += 1

                # Wrap in OpenAI SSE format and yield to client immediately
                sse_chunk = build_openai_chunk(content=chunk_text, model=model_name)
                yield f"data: {json.dumps(sse_chunk)}\n\n"

        # Send the final [DONE] chunk (OpenAI protocol requires this)
        done_chunk = build_openai_chunk(content="", model=model_name, finish_reason="stop")
        yield f"data: {json.dumps(done_chunk)}\n\n"
        yield "data: [DONE]\n\n"

        # Count output tokens for logging
        full_output = "".join(output_text_buffer)
        output_tokens = count_tokens_in_text(full_output)

        logger.info(
            "Groq stream completed",
            extra={
                "session_id": session_id,
                "model": model_name,
                "chunks_sent": chunk_count,
                "output_tokens": output_tokens,
                "output_chars": len(full_output),
            },
        )

    except Exception as e:
        logger.error(
            f"Groq streaming error: {e}",
            extra={"session_id": session_id},
            exc_info=True,
        )
        error_payload = {
            "error": {
                "message": f"Upstream Groq error: {str(e)}",
                "type": "upstream_error",
            }
        }
        yield f"data: {json.dumps(error_payload)}\n\n"


async def call_groq_blocking(
    messages: list[dict],
    model_name: str,
    session_id: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> tuple[str, int]:
    """
    Non-streaming Groq call. Returns the full response text + output token count.

    Used when the client sends stream=False.

    Returns:
        (response_text, output_token_count)
    """
    logger.info(
        "Calling Groq (blocking)",
        extra={"session_id": session_id, "model": model_name},
    )

    response = _groq_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )

    response_text = response.choices[0].message.content or ""

    # Use reported usage if available, else count with tiktoken
    if response.usage:
        output_tokens = response.usage.completion_tokens
    else:
        output_tokens = count_tokens_in_text(response_text)

    logger.info(
        "Groq blocking call completed",
        extra={
            "session_id": session_id,
            "output_tokens": output_tokens,
        },
    )

    return response_text, output_tokens
