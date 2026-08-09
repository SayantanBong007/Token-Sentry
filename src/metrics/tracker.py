"""
metrics/tracker.py — Lightweight Redis Analytics Engine
"""
import logging
import time
from src.config import settings
# pyrefly: ignore [missing-import]
import redis.asyncio as redis

logger = logging.getLogger(__name__)

_redis_client = redis.from_url(settings.redis_url, decode_responses=True)

async def increment_metric(key: str, amount: int = 1):
    """Increment a metric counter and record a timestamped activity event."""
    try:
        pipe = _redis_client.pipeline()
        pipe.incrby(f"metrics:{key}", amount)
        # Keep a rolling log of recent activity (last 20 events)
        event = f"{int(time.time())}:{key}:{amount}"
        pipe.lpush("metrics:activity_log", event)
        pipe.ltrim("metrics:activity_log", 0, 19)
        await pipe.execute()
    except Exception as e:
        logger.error(f"Failed to increment metric {key}: {e}")


async def get_all_metrics() -> dict:
    """Retrieve all metrics for the dashboard."""
    try:
        keys = await _redis_client.keys("metrics:*")
        # Exclude the activity_log list from the numeric counters
        counter_keys = [k for k in keys if k != "metrics:activity_log"]

        if not counter_keys:
            base = {
                "tokens_saved": 0,
                "requests_served": 0,
                "fallback_events": 0,
                "simple_intents_routed": 0,
                "complex_intents_routed": 0,
                "compression_runs": 0,
                "cost_saved_usd": 0.0,
                "routing_efficiency_pct": 0,
                "activity_log": [],
            }
            return base

        values = await _redis_client.mget(counter_keys)
        metrics = {k.replace("metrics:", ""): int(v) for k, v in zip(counter_keys, values) if v}

        # Derived stats
        tokens_saved = metrics.get("tokens_saved", 0)
        requests = metrics.get("requests_served", 0)
        simple = metrics.get("simple_intents_routed", 0)
        complex_ = requests - simple

        metrics["complex_intents_routed"] = max(0, complex_)
        metrics["cost_saved_usd"] = round((tokens_saved / 1_000_000) * 0.79, 6)
        metrics["routing_efficiency_pct"] = round((simple / requests) * 100) if requests > 0 else 0

        # Fetch recent activity log
        raw_log = await _redis_client.lrange("metrics:activity_log", 0, 14)
        activity = []
        for entry in raw_log:
            parts = entry.split(":")
            if len(parts) == 3:
                ts, event_key, amount = parts
                activity.append({
                    "ts": int(ts),
                    "event": event_key,
                    "amount": int(amount),
                })
        metrics["activity_log"] = activity

        return metrics
    except Exception as e:
        logger.error(f"Failed to retrieve metrics: {e}")
        return {}
