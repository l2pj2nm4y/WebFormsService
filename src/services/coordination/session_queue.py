"""Redis-based session queue with FIFO ordering.

Implements atomic session queue operations using Redis Sorted Sets with
upload timestamp as score for FIFO processing.
"""

from uuid import UUID

from src.services.coordination.redis_connection import get_redis_client

QUEUE_KEY = "session_queue"


async def enqueue_session(session_id: UUID, upload_timestamp: float) -> bool:
    """Add session to FIFO queue using ZADD with NX flag.

    Args:
        session_id: Session UUID
        upload_timestamp: Upload timestamp (UNIX timestamp for score)

    Returns:
        bool: True if session was added, False if already exists

    Raises:
        ConnectionError: If Redis connection fails
    """
    client = await get_redis_client()

    # ZADD with NX flag: only add if doesn't exist
    result = await client.zadd(
        QUEUE_KEY, {str(session_id): upload_timestamp}, nx=True
    )

    return result > 0


async def claim_next_session() -> UUID | None:
    """Atomically claim next session from queue using ZPOPMIN.

    Returns:
        UUID | None: Session ID if available, None if queue is empty

    Raises:
        ConnectionError: If Redis connection fails
    """
    client = await get_redis_client()

    # ZPOPMIN is atomic: pop member with lowest score (earliest timestamp)
    result = await client.zpopmin(QUEUE_KEY, count=1)

    if not result:
        return None

    # Result is list of (member, score) tuples
    session_id_bytes, _timestamp = result[0]

    return UUID(session_id_bytes.decode("utf-8"))


async def get_queue_size() -> int:
    """Get number of sessions in queue.

    Returns:
        int: Queue size

    Raises:
        ConnectionError: If Redis connection fails
    """
    client = await get_redis_client()
    return await client.zcard(QUEUE_KEY)


async def peek_next_sessions(count: int = 5) -> list[tuple[UUID, float]]:
    """Peek at next sessions without removing them.

    Args:
        count: Number of sessions to peek (default 5)

    Returns:
        list[tuple[UUID, float]]: List of (session_id, timestamp) tuples

    Raises:
        ConnectionError: If Redis connection fails
    """
    client = await get_redis_client()

    # ZRANGE with scores: get first N items without removing
    result = await client.zrange(QUEUE_KEY, 0, count - 1, withscores=True)

    if not result:
        return []

    return [
        (UUID(member.decode("utf-8")), score) for member, score in result
    ]


async def remove_session_from_queue(session_id: UUID) -> bool:
    """Remove specific session from queue (for cleanup/cancellation).

    Args:
        session_id: Session ID to remove

    Returns:
        bool: True if session was removed, False if not in queue

    Raises:
        ConnectionError: If Redis connection fails
    """
    client = await get_redis_client()

    result = await client.zrem(QUEUE_KEY, str(session_id))
    return result > 0


async def clear_queue() -> int:
    """Clear all sessions from queue (admin operation, use with caution).

    Returns:
        int: Number of sessions removed

    Raises:
        ConnectionError: If Redis connection fails
    """
    client = await get_redis_client()

    count = await client.zcard(QUEUE_KEY)
    await client.delete(QUEUE_KEY)

    return count
