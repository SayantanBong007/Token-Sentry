"""
proxy/streaming.py — Stream responses back to the client in OpenAI SSE format.

WHY THIS EXISTS:
  Streaming means the user sees words appearing one-by-one as the model generates them.
  We use the official `openai` SDK here because it allows us to override the `base_url`.
  This means we can route traffic to ANY OpenAI-compatible provider (Groq, OpenRouter, NVIDIA, etc).

  We also implement Provider Fallbacks here:
  If the primary provider throws an error (e.g. 429 Rate Limit), we seamlessly
  catch it and retry with the fallback provider.
"""

import json
import logging
from openai import AsyncOpenAI
from src.config import settings
from src.proxy.transformer import build_openai_chunk, build_openai_response
from src.token_engine.counter import count_tokens_in_text
from src.metrics.tracker import increment_metric

logger = logging.getLogger(__name__)

# Clients for our providers
_primary_client = AsyncOpenAI(
    base_url=settings.primary_provider_url,
    api_key=settings.primary_api_key
)

_fallback_client = AsyncOpenAI(
    base_url=settings.fallback_provider_url,
    api_key=settings.fallback_api_key
)

async def stream_provider_response(
    messages: list[dict],
    model_name: str,
    session_id: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
):
    """
    Stream a response back in OpenAI SSE format, with automatic fallbacks.
    """
    output_text_buffer = []
    chunk_count = 0

    logger.info(
        "Starting stream with primary provider",
        extra={"session_id": session_id, "model": model_name},
    )

    try:
        stream = await _primary_client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
    except Exception as e:
        logger.warning(
            f"Primary provider failed ({e}). Falling back to secondary provider.",
            extra={"session_id": session_id}
        )
        try:
            # Fallback
            await increment_metric("fallback_events")
            fallback_model = settings.fallback_main_model
            stream = await _fallback_client.chat.completions.create(
                model=fallback_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            model_name = fallback_model
        except Exception as fallback_e:
            logger.error(f"Fallback provider also failed: {fallback_e}")
            error_payload = {"error": {"message": "All upstream providers failed.", "type": "upstream_error"}}
            yield f"data: {json.dumps(error_payload)}\n\n"
            return

    try:
        async for chunk in stream:
            # Safely handle empty chunks
            if not chunk.choices or not chunk.choices[0].delta:
                continue
                
            chunk_text = chunk.choices[0].delta.content or ""

            if chunk_text:
                output_text_buffer.append(chunk_text)
                chunk_count += 1

                sse_chunk = build_openai_chunk(content=chunk_text, model=model_name)
                yield f"data: {json.dumps(sse_chunk)}\n\n"

        done_chunk = build_openai_chunk(content="", model=model_name, finish_reason="stop")
        yield f"data: {json.dumps(done_chunk)}\n\n"
        yield "data: [DONE]\n\n"

        full_output = "".join(output_text_buffer)
        output_tokens = count_tokens_in_text(full_output)

        logger.info(
            "Stream completed",
            extra={
                "session_id": session_id,
                "model": model_name,
                "chunks_sent": chunk_count,
                "output_tokens": output_tokens,
            },
        )

    except Exception as e:
        logger.error(f"Streaming error: {e}")
        error_payload = {"error": {"message": str(e), "type": "stream_error"}}
        yield f"data: {json.dumps(error_payload)}\n\n"


async def call_provider_blocking(
    messages: list[dict],
    model_name: str,
    session_id: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> tuple[str, int]:
    """
    Non-streaming call with automatic fallbacks.
    Returns: (response_text, output_token_count)
    """
    logger.info("Calling provider (blocking)", extra={"session_id": session_id})

    try:
        response = await _primary_client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
    except Exception as e:
        logger.warning(f"Primary failed ({e}), falling back.", extra={"session_id": session_id})
        await increment_metric("fallback_events")
        response = await _fallback_client.chat.completions.create(
            model=settings.fallback_main_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

    response_text = response.choices[0].message.content or ""
    output_tokens = response.usage.completion_tokens if response.usage else count_tokens_in_text(response_text)

    return response_text, output_tokens
