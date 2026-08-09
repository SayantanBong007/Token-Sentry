"""
proxy/router.py — The main API endpoint: POST /v1/chat/completions

WHY THIS EXISTS:
  This is the front door of Token-Sentry.
  It exposes an OpenAI-compatible endpoint so any existing app
  just needs to change its base_url to point here.

  TWO OPERATING MODES:
  ─────────────────────────────────────────────────────────────
  MODE 1: STATEFUL (Chat Apps)
    Triggered by: X-Session-ID header present
    Token-Sentry manages the full conversation history in Redis.
    Every turn is stored, retrieved, and compressed when needed.

    Flow:
      1. Load history from Redis for this session_id
      2. Append incoming messages to history
      3. Count tokens on full history
      4. If RED → compress (summarize cold + keep hot buffer)
      5. Forward to Groq
      6. Append assistant reply to history
      7. Save updated history back to Redis

  MODE 2: PASSTHROUGH (Agentic Systems — LangGraph, CrewAI, AutoGen)
    Triggered by: No X-Session-ID header
    The agent framework (LangGraph etc.) manages its OWN state.
    Token-Sentry just compresses the incoming payload if needed.

    Flow:
      1. Use messages from the request as-is (agent sent full context)
      2. Count tokens
      3. If RED → compress (same algorithm, but don't store anything)
      4. Forward to Groq
      5. Return response (agent handles its own state update)

  WHY TWO MODES MATTER:
  ─────────────────────
  A LangGraph agent maintains its own state graph. If Token-Sentry
  also tried to maintain history for it, we'd have two conflicting
  memory systems. So in passthrough mode, we only compress — never store.
"""

import logging
import uuid
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from src.proxy.transformer import resolve_model, build_openai_response
from src.proxy.streaming import stream_provider_response, call_provider_blocking
from src.token_engine.counter import count_tokens_in_messages
from src.token_engine.watermark import check_watermark, WatermarkStatus
from src.memory.session_store import load_session, save_session
from src.memory.compressor import compress_history
from src.memory.vector_store import recall_from_cold_memory
from src.routing.intent_classifier import classify_intent
from src.metrics.tracker import increment_metric
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ──────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="llama-3.3-70b-versatile")
    messages: list[Message]
    stream: bool = Field(default=False)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None)


# ── Main Endpoint ──────────────────────────────────────────────────────────────

@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint.

    Accepts the exact same JSON format as OpenAI's API.
    Returns the exact same format — either streaming SSE or a JSON object.

    Headers:
        X-Session-ID: (optional)
            If provided → STATEFUL mode: Token-Sentry manages memory in Redis.
            If absent   → PASSTHROUGH mode: agent manages its own state.

    Example curl (chat app — stateful):
        curl -X POST http://localhost:8000/v1/chat/completions \\
          -H "Content-Type: application/json" \\
          -H "X-Session-ID: my-chat-123" \\
          -d '{"model": "llama-3.3-70b-versatile",
               "messages": [{"role": "user", "content": "Hello!"}]}'

    Example curl (agent — passthrough):
        curl -X POST http://localhost:8000/v1/chat/completions \\
          -H "Content-Type: application/json" \\
          -d '{"model": "llama-3.3-70b-versatile",
               "messages": [FULL_LANGGRAPH_STATE_HERE]}'
    """
    # ── Detect mode ────────────────────────────────────────────────────────────
    session_id = request.headers.get("X-Session-ID")
    is_stateful = session_id is not None

    # In passthrough mode, generate a temporary trace ID just for logging
    trace_id = session_id or f"pass-{uuid.uuid4().hex[:8]}"

    await increment_metric("requests_served")

    logger.info(
        "Incoming request",
        extra={
            "session_id": trace_id,
            "mode": "stateful" if is_stateful else "passthrough",
            "requested_model": body.model,
            "message_count": len(body.messages),
            "stream": body.stream,
        },
    )

    # ── Convert incoming messages to plain dicts ───────────────────────────────
    incoming_messages = [{"role": m.role, "content": m.content} for m in body.messages]

    # ── Build the working message list ─────────────────────────────────────────
    if is_stateful:
        # STATEFUL: load history, append new messages
        history = await load_session(session_id)
        history.extend(incoming_messages)
        working_messages = history

        logger.info(
            "Session loaded",
            extra={
                "session_id": session_id,
                "history_turns": len(history),
            },
        )
    else:
        # PASSTHROUGH: use the agent's own messages as-is
        working_messages = incoming_messages

    # ── Recall Cold Memory ────────────────────────────────────────────────────
    if is_stateful and len(incoming_messages) > 0:
        last_msg = incoming_messages[-1].get("content", "")
        if last_msg:
            cold_context = await recall_from_cold_memory(session_id, last_msg)
            if cold_context:
                working_messages.insert(0, {
                    "role": "system",
                    "content": f"🧠 Retained Context from Past Interactions:\n{cold_context}"
                })

    # ── Count tokens ──────────────────────────────────────────────────────────
    input_token_count = count_tokens_in_messages(working_messages)

    logger.info(
        "Token count measured",
        extra={
            "session_id": trace_id,
            "input_tokens": input_token_count,
            "turns": len(working_messages),
        },
    )

    # ── Check watermark and compress if needed ────────────────────────────────
    watermark_status = check_watermark(input_token_count, trace_id)
    compressed = False

    if watermark_status == WatermarkStatus.RED:
        logger.warning(
            "🔴 Watermark breached — compressing history",
            extra={"session_id": trace_id, "tokens": input_token_count},
        )
        working_messages = await compress_history(trace_id, working_messages)
        input_token_count = count_tokens_in_messages(working_messages)
        compressed = True

        logger.info(
            "Compression applied",
            extra={
                "session_id": trace_id,
                "tokens_after": input_token_count,
                "turns_after": len(working_messages),
            },
        )

    # ── Intent Routing ────────────────────────────────────────────────────────
    intent = "COMPLEX"
    if settings.enable_intent_routing:
        intent = await classify_intent(working_messages)
        if intent == "SIMPLE":
            await increment_metric("simple_intents_routed")
            logger.info(
                "Routing simple query to cheap model",
                extra={"session_id": trace_id, "original_model": body.model}
            )
            body.model = settings.primary_summarizer_model

    # ── Resolve model name ────────────────────────────────────────────────────
    resolved_model = resolve_model(body.model)

    # ── Forward to Provider ───────────────────────────────────────────────────
    if body.stream and not is_stateful:
        # PASSTHROUGH + STREAMING: full streaming, no state management needed
        return StreamingResponse(
            stream_provider_response(
                messages=working_messages,
                model_name=resolved_model,
                session_id=trace_id,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            ),
            media_type="text/event-stream",
            headers={
                "X-Session-ID": trace_id,
                "X-Input-Tokens": str(input_token_count),
                "X-Mode": "passthrough",
                "X-Compressed": str(compressed).lower(),
                "X-Intent": intent.lower(),
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    else:
        # STATEFUL or BLOCKING: use blocking call so we can capture + save the response
        # Note: stateful streaming is always blocking internally to ensure we can
        # persist the assistant's reply to Redis before the session is lost.
        response_text, output_tokens = await call_provider_blocking(
            messages=working_messages,
            model_name=resolved_model,
            session_id=trace_id,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )

        # ── Save updated history to Redis (stateful mode only) ────────────────
        if is_stateful:
            # After compression, working_messages is the compressed history.
            # We save THAT as the new baseline, then append the assistant reply.
            updated_history = working_messages + [
                {"role": "assistant", "content": response_text}
            ]
            await save_session(session_id, updated_history)

            logger.info(
                "Session saved",
                extra={
                    "session_id": session_id,
                    "total_turns": len(updated_history),
                },
            )

        logger.info(
            f"Request completed (Intent: {intent})",
            extra={
                "session_id": trace_id,
                "mode": "stateful" if is_stateful else "passthrough",
                "input_tokens": input_token_count,
                "output_tokens": output_tokens,
                "total_tokens": input_token_count + output_tokens,
                "compressed": compressed,
                "intent": intent,
            },
        )

        response_headers = {
            "X-Session-ID": trace_id,
            "X-Mode": "stateful" if is_stateful else "passthrough",
            "X-Compressed": str(compressed).lower(),
            "X-Intent": intent.lower(),
        }

        return JSONResponse(
            content=build_openai_response(
                content=response_text,
                model=resolved_model,
                input_tokens=input_token_count,
                output_tokens=output_tokens,
            ),
            headers=response_headers,
        )
