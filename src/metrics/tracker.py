"""
metrics/tracker.py — Lightweight Redis Analytics Engine
"""
import logging
from src.config import settings
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Initialize Redis client for metrics
_redis_client = redis.from_url(settings.redis_url, decode_responses=True)

async def increment_metric(key: str, amount: int = 1):
    """Increment a metric counter."""
    try:
        await _redis_client.incrby(f"metrics:{key}", amount)
    except Exception as e:
        logger.error(f"Failed to increment metric {key}: {e}")

async def get_all_metrics() -> dict:
    """Retrieve all metrics for the dashboard."""
    try:
        keys = await _redis_client.keys("metrics:*")
        if not keys:
            return {
                "tokens_saved": 0,
                "requests_served": 0,
                "fallback_events": 0,
                "cost_saved_usd": 0.0
            }
        
        values = await _redis_client.mget(keys)
        metrics = {k.replace("metrics:", ""): int(v) for k, v in zip(keys, values) if v}
        
        # Calculate approximate cost saved based on tokens
        # E.g., Llama 70B output tokens are ~$0.79 / 1M tokens
        tokens_saved = metrics.get("tokens_saved", 0)
        metrics["cost_saved_usd"] = round((tokens_saved / 1_000_000) * 0.79, 4)
        
        return metrics
    except Exception as e:
        logger.error(f"Failed to retrieve metrics: {e}")
        return {}
