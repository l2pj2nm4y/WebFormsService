"""Redis connection management.

Provides centralized Redis client creation and health checking with support
for both local development and production environments.
"""

from typing import Any

from redis.asyncio import Redis

from src.lib.config import get_config

# Global Redis client
_redis_client: Redis | None = None


async def get_redis_client() -> Redis:
    """Get or create Redis client based on configuration.

    Returns:
        Redis: Configured Redis client

    Raises:
        ConnectionError: If Redis connection fails
    """
    global _redis_client

    if _redis_client is None:
        config = get_config()

        _redis_client = Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password if config.redis.password else None,
            ssl=config.redis.ssl,
            decode_responses=False,  # Use bytes for binary data
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )

        # Test connection
        try:
            await _redis_client.ping()
        except Exception as e:
            _redis_client = None
            raise ConnectionError(f"Failed to connect to Redis: {e}") from e

    return _redis_client


async def close_redis_client() -> None:
    """Close Redis client connection."""
    global _redis_client

    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None


async def redis_health_check() -> dict[str, Any]:
    """Check Redis connection health.

    Returns:
        dict: Health status with details
    """
    try:
        client = await get_redis_client()
        await client.ping()

        info = await client.info("server")

        return {
            "status": "healthy",
            "redis_version": info.get("redis_version", "unknown"),
            "connected_clients": info.get("connected_clients", 0),
            "uptime_seconds": info.get("uptime_in_seconds", 0),
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def reset_redis_client() -> None:
    """Reset global Redis client (useful for testing)."""
    global _redis_client
    _redis_client = None
