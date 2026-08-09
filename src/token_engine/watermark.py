"""
token_engine/watermark.py — High-watermark threshold detection.

WHY THIS EXISTS:
  After counting tokens, we need to decide: "Is this conversation too heavy?"
  This module answers that question and returns a clear action to take.

  Think of it like a fuel gauge:
    GREEN  (below LOW watermark)  → send normally, no action needed
    YELLOW (between LOW and HIGH) → log a warning, monitor closely
    RED    (above HIGH watermark) → MUST compress before sending
"""

import logging
from src.config import settings

logger = logging.getLogger(__name__)

# Watermark levels
HIGH_WATERMARK = settings.token_high_watermark        # e.g. 4000 tokens
LOW_WATERMARK = int(HIGH_WATERMARK * 0.75)            # e.g. 3000 tokens (75%)


class WatermarkStatus:
    """Simple result object returned by check_watermark()."""
    GREEN  = "green"    # Safe — send as-is
    YELLOW = "yellow"   # Warning — approaching limit
    RED    = "red"      # MUST compress before sending


def check_watermark(token_count: int, session_id: str) -> str:
    """
    Check if the token count has crossed any threshold.

    Args:
        token_count: Total tokens in the current conversation payload
        session_id:  Used for logging — to trace which session triggered this

    Returns:
        WatermarkStatus.GREEN / YELLOW / RED

    Example:
        status = check_watermark(5200, "session_abc123")
        if status == WatermarkStatus.RED:
            # trigger compression before sending to Gemini
    """
    if token_count >= HIGH_WATERMARK:
        logger.warning(
            "🔴 HIGH WATERMARK BREACHED — compression required",
            extra={
                "session_id": session_id,
                "token_count": token_count,
                "high_watermark": HIGH_WATERMARK,
                "overage": token_count - HIGH_WATERMARK,
                "action": "COMPRESS_NOW",
            },
        )
        return WatermarkStatus.RED

    elif token_count >= LOW_WATERMARK:
        logger.info(
            "🟡 LOW WATERMARK — approaching compression threshold",
            extra={
                "session_id": session_id,
                "token_count": token_count,
                "high_watermark": HIGH_WATERMARK,
                "remaining": HIGH_WATERMARK - token_count,
                "action": "MONITOR",
            },
        )
        return WatermarkStatus.YELLOW

    else:
        logger.debug(
            "🟢 Token count healthy",
            extra={
                "session_id": session_id,
                "token_count": token_count,
                "high_watermark": HIGH_WATERMARK,
            },
        )
        return WatermarkStatus.GREEN
