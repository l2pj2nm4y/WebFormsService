# Redis Contracts

**Feature**: Browser Extension File Processing System
**Date**: 2025-01-06
**Purpose**: Define Redis operations for session queue and distributed locking

## Overview

Redis provides two critical coordination mechanisms:
1. **Session Queue**: FIFO queue for exclusive session selection (FR-022, FR-023)
2. **Master Locks**: Distributed locking for master folder writes (FR-024, FR-025)

**Requirements**:
- Zero code changes between local (Docker) and production (managed service) (FR-026)
- Atomic operations to prevent race conditions
- Lock TTL to prevent deadlocks from crashed processes
- Observable operations for monitoring

## Redis Connection Contract

### Configuration

```python
from pydantic import BaseModel, Field
import redis.asyncio as redis

class RedisConfig(BaseModel):
    """Redis configuration"""
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: str | None = Field(None, description="Redis password (optional)")
    ssl: bool = Field(default=False, description="Use SSL/TLS")

    # Connection pool settings
    max_connections: int = Field(default=10, description="Max connection pool size")
    socket_timeout: int = Field(default=5, description="Socket timeout in seconds")
    socket_connect_timeout: int = Field(default=5, description="Connect timeout in seconds")

    # Lock settings
    default_lock_ttl: int = Field(default=300, description="Default lock TTL in seconds (5 minutes)")
    lock_retry_delay: float = Field(default=0.1, description="Lock retry delay in seconds")
    max_lock_retries: int = Field(default=50, description="Max lock acquisition retries")

    def create_url(self) -> str:
        """Create Redis connection URL"""
        protocol = "rediss" if self.ssl else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{protocol}://{auth}{self.host}:{self.port}/{self.db}"
```

### Connection Management

```python
class RedisConnection:
    """Redis connection manager with automatic reconnection"""

    def __init__(self, config: RedisConfig):
        self.config = config
        self.client: redis.Redis | None = None

    async def connect(self) -> None:
        """Establish Redis connection"""
        self.client = await redis.from_url(
            self.config.create_url(),
            max_connections=self.config.max_connections,
            socket_timeout=self.config.socket_timeout,
            socket_connect_timeout=self.config.socket_connect_timeout,
            decode_responses=False  # We handle encoding
        )

    async def disconnect(self) -> None:
        """Close Redis connection"""
        if self.client:
            await self.client.close()

    async def ping(self) -> bool:
        """Health check"""
        try:
            return await self.client.ping()
        except Exception:
            return False
```

## Session Queue Contract (FR-022, FR-023)

**Purpose**: FIFO queue for exclusive session selection by backend processes

**Implementation**: Redis Sorted Set with upload timestamp as score

### Data Structure

```
Key: "session_queue"
Type: Sorted Set (ZSET)
Score: Upload timestamp (float, Unix timestamp)
Value: Session GUID (string)

Example:
    session_queue:
        1704545400.123 → "550e8400-e29b-41d4-a716-446655440000"
        1704545401.456 → "660e8400-e29b-41d4-a716-446655440001"
        1704545402.789 → "770e8400-e29b-41d4-a716-446655440002"
```

### Operations

#### 1. Add Session to Queue

```python
async def enqueue_session(session_id: UUID, upload_timestamp: float) -> bool:
    """
    Add session to FIFO queue.

    Args:
        session_id: Session GUID
        upload_timestamp: Unix timestamp for FIFO ordering

    Returns:
        True if added, False if already exists

    Redis Operation:
        ZADD session_queue NX <timestamp> <session_id>

    Notes:
        - NX flag prevents duplicate entries
        - Earlier timestamps = processed first
    """
    result = await redis_client.zadd(
        "session_queue",
        {str(session_id): upload_timestamp},
        nx=True  # Only add if doesn't exist
    )

    # Log operation
    logger.info(
        "session_queue_add",
        session_id=str(session_id),
        timestamp=upload_timestamp,
        added=result > 0
    )

    return result > 0
```

#### 2. Claim Next Session (Atomic)

```python
async def claim_next_session() -> UUID | None:
    """
    Atomically claim next session from FIFO queue.

    Returns:
        Session GUID if claimed, None if queue empty

    Redis Operation:
        ZPOPMIN session_queue 1

    Notes:
        - ZPOPMIN is atomic (prevents duplicate claims)
        - Returns lowest score (earliest timestamp) = FIFO
        - Removes session from queue in same operation
    """
    result = await redis_client.zpopmin("session_queue", count=1)

    if not result:
        return None

    # result is list of tuples: [(member, score)]
    session_id_bytes, timestamp = result[0]
    session_id = UUID(session_id_bytes.decode('utf-8'))

    # Log operation
    logger.info(
        "session_queue_claim",
        session_id=str(session_id),
        timestamp=timestamp,
        queue_size=await get_queue_size()
    )

    return session_id
```

#### 3. Peek Next Session (Non-Consuming)

```python
async def peek_next_session() -> tuple[UUID, float] | None:
    """
    View next session without claiming.

    Returns:
        (session_id, timestamp) tuple or None if queue empty

    Redis Operation:
        ZRANGE session_queue 0 0 WITHSCORES
    """
    result = await redis_client.zrange(
        "session_queue",
        0, 0,
        withscores=True
    )

    if not result:
        return None

    session_id_bytes, timestamp = result[0]
    return UUID(session_id_bytes.decode('utf-8')), timestamp
```

#### 4. Get Queue Size

```python
async def get_queue_size() -> int:
    """
    Get number of sessions in queue.

    Returns:
        Queue size

    Redis Operation:
        ZCARD session_queue
    """
    return await redis_client.zcard("session_queue")
```

#### 5. Get Queue Position

```python
async def get_queue_position(session_id: UUID) -> int | None:
    """
    Get session's position in queue (0-indexed).

    Args:
        session_id: Session GUID

    Returns:
        Queue position or None if not in queue

    Redis Operation:
        ZRANK session_queue <session_id>
    """
    rank = await redis_client.zrank("session_queue", str(session_id))
    return rank
```

### Test Contract

```python
async def test_session_queue_fifo():
    """Contract test: Session queue maintains FIFO order"""
    # Add 3 sessions with increasing timestamps
    await enqueue_session(UUID("00000000-0000-0000-0000-000000000001"), 1000.0)
    await enqueue_session(UUID("00000000-0000-0000-0000-000000000002"), 2000.0)
    await enqueue_session(UUID("00000000-0000-0000-0000-000000000003"), 3000.0)

    # Claim should return in FIFO order
    session1 = await claim_next_session()
    assert session1 == UUID("00000000-0000-0000-0000-000000000001")

    session2 = await claim_next_session()
    assert session2 == UUID("00000000-0000-0000-0000-000000000002")

    session3 = await claim_next_session()
    assert session3 == UUID("00000000-0000-0000-0000-000000000003")

    # Queue should be empty
    assert await claim_next_session() is None

async def test_session_queue_no_duplicates():
    """Contract test: Duplicate sessions are not added to queue"""
    session_id = UUID("00000000-0000-0000-0000-000000000001")

    # First add should succeed
    added1 = await enqueue_session(session_id, 1000.0)
    assert added1 is True

    # Second add should fail (duplicate)
    added2 = await enqueue_session(session_id, 2000.0)
    assert added2 is False

    # Queue size should be 1
    assert await get_queue_size() == 1
```

## Master Lock Contract (FR-024, FR-025)

**Purpose**: Distributed lock to prevent concurrent master folder updates

**Implementation**: Redis SET with NX (not exists) and EX (expiration) flags

### Data Structure

```
Key: "lock:master:<website_id>"
Value: <worker_id>
TTL: <configurable, default 300 seconds>

Example:
    lock:master:uscis.gov = "worker-123" (TTL: 300s)
    lock:master:canada.ca = "worker-456" (TTL: 300s)
```

### Operations

#### 1. Acquire Lock

```python
import socket

async def acquire_master_lock(
    website_id: str,
    ttl: int | None = None,
    retry: bool = True
) -> bool:
    """
    Acquire distributed lock on master folder.

    Args:
        website_id: Website identifier to lock
        ttl: Lock timeout in seconds (default from config)
        retry: Whether to retry if lock is held

    Returns:
        True if lock acquired, False if already held

    Redis Operation:
        SET lock:master:<website_id> <worker_id> NX EX <ttl>

    Notes:
        - NX ensures atomic "test and set" operation
        - EX prevents deadlocks if process crashes
        - Worker ID includes hostname and process ID
    """
    if ttl is None:
        ttl = redis_config.default_lock_ttl

    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    lock_key = f"lock:master:{website_id}"

    # Try to acquire lock
    acquired = await redis_client.set(
        lock_key,
        worker_id,
        nx=True,  # Only set if key doesn't exist
        ex=ttl    # Expiration time
    )

    if acquired:
        logger.info(
            "master_lock_acquired",
            website_id=website_id,
            worker_id=worker_id,
            ttl=ttl
        )
        return True

    if not retry:
        return False

    # Retry with backoff
    for attempt in range(redis_config.max_lock_retries):
        await asyncio.sleep(redis_config.lock_retry_delay)

        acquired = await redis_client.set(lock_key, worker_id, nx=True, ex=ttl)
        if acquired:
            logger.info(
                "master_lock_acquired_retry",
                website_id=website_id,
                worker_id=worker_id,
                attempt=attempt + 1
            )
            return True

    logger.warning(
        "master_lock_acquisition_failed",
        website_id=website_id,
        worker_id=worker_id,
        max_retries=redis_config.max_lock_retries
    )

    return False
```

#### 2. Release Lock

```python
async def release_master_lock(website_id: str) -> bool:
    """
    Release distributed lock on master folder.

    Args:
        website_id: Website identifier to unlock

    Returns:
        True if lock released, False if not held by us

    Redis Operation:
        Lua script to atomically check owner and delete

    Notes:
        - Must verify we own the lock before deleting
        - Prevents accidental release of another worker's lock
    """
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    lock_key = f"lock:master:{website_id}"

    # Lua script for atomic check-and-delete
    lua_script = """
    local lock_key = KEYS[1]
    local worker_id = ARGV[1]
    local current_owner = redis.call('GET', lock_key)

    if current_owner == worker_id then
        redis.call('DEL', lock_key)
        return 1
    else
        return 0
    end
    """

    result = await redis_client.eval(lua_script, 1, lock_key, worker_id)

    if result == 1:
        logger.info(
            "master_lock_released",
            website_id=website_id,
            worker_id=worker_id
        )
        return True
    else:
        logger.warning(
            "master_lock_release_failed",
            website_id=website_id,
            worker_id=worker_id,
            reason="not_owner"
        )
        return False
```

#### 3. Check Lock Status

```python
async def is_master_locked(website_id: str) -> bool:
    """
    Check if master folder is currently locked.

    Args:
        website_id: Website identifier

    Returns:
        True if locked by any worker

    Redis Operation:
        EXISTS lock:master:<website_id>
    """
    lock_key = f"lock:master:{website_id}"
    return await redis_client.exists(lock_key) > 0


async def is_master_locked_by_us(website_id: str) -> bool:
    """
    Check if we hold the master folder lock.

    Args:
        website_id: Website identifier

    Returns:
        True if locked by this worker

    Redis Operation:
        GET lock:master:<website_id>
    """
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    lock_key = f"lock:master:{website_id}"

    current_owner = await redis_client.get(lock_key)
    return current_owner and current_owner.decode('utf-8') == worker_id
```

#### 4. Extend Lock

```python
async def extend_master_lock(website_id: str, additional_ttl: int) -> bool:
    """
    Extend lock TTL if we own it.

    Args:
        website_id: Website identifier
        additional_ttl: Additional seconds to add

    Returns:
        True if extended, False if not owned by us

    Redis Operation:
        EXPIRE lock:master:<website_id> <new_ttl>

    Notes:
        - Used for long-running operations
        - Only works if we own the lock
    """
    if not await is_master_locked_by_us(website_id):
        return False

    lock_key = f"lock:master:{website_id}"
    await redis_client.expire(lock_key, additional_ttl)

    logger.info(
        "master_lock_extended",
        website_id=website_id,
        additional_ttl=additional_ttl
    )

    return True
```

#### 5. Force Release (Admin Only)

```python
async def force_release_master_lock(website_id: str) -> bool:
    """
    Force release a lock regardless of owner.

    Args:
        website_id: Website identifier

    Returns:
        True if lock was deleted

    WARNING: Only use for orphaned locks (crashed workers)
             Check lock TTL and age before forcing

    Redis Operation:
        DEL lock:master:<website_id>
    """
    lock_key = f"lock:master:{website_id}"
    result = await redis_client.delete(lock_key)

    logger.warning(
        "master_lock_force_released",
        website_id=website_id,
        deleted=result > 0
    )

    return result > 0
```

### Lock Context Manager

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def master_lock_context(website_id: str, ttl: int | None = None):
    """
    Context manager for automatic lock acquisition and release.

    Usage:
        async with master_lock_context("uscis.gov"):
            # Do master folder operations
            await write_embeddings_index(...)
            await write_merged_prompt(...)

    Ensures lock is released even if exception occurs.
    """
    acquired = await acquire_master_lock(website_id, ttl=ttl)

    if not acquired:
        raise LockAcquisitionError(f"Could not acquire lock for {website_id}")

    try:
        yield
    finally:
        await release_master_lock(website_id)
```

### Test Contract

```python
async def test_master_lock_exclusive():
    """Contract test: Only one worker can hold lock"""
    website_id = "test.com"

    # First worker acquires lock
    acquired1 = await acquire_master_lock(website_id, retry=False)
    assert acquired1 is True

    # Second worker cannot acquire (retry=False)
    acquired2 = await acquire_master_lock(website_id, retry=False)
    assert acquired2 is False

    # First worker releases
    released = await release_master_lock(website_id)
    assert released is True

    # Now second worker can acquire
    acquired3 = await acquire_master_lock(website_id, retry=False)
    assert acquired3 is True


async def test_master_lock_ttl_expiration():
    """Contract test: Lock expires after TTL"""
    website_id = "test.com"

    # Acquire with 1 second TTL
    acquired = await acquire_master_lock(website_id, ttl=1)
    assert acquired is True

    # Lock should exist
    assert await is_master_locked(website_id) is True

    # Wait for expiration
    await asyncio.sleep(1.5)

    # Lock should be gone
    assert await is_master_locked(website_id) is False
```

## Error Handling

### Custom Exceptions

```python
class RedisError(Exception):
    """Base Redis error"""
    pass

class LockAcquisitionError(RedisError):
    """Failed to acquire lock"""
    pass

class LockNotHeldError(RedisError):
    """Operation requires lock but not held"""
    pass

class RedisConnectionError(RedisError):
    """Redis connection failed"""
    pass
```

### Connection Resilience

```python
async def with_retry(operation, max_retries: int = 3):
    """Retry Redis operations on transient failures"""
    for attempt in range(max_retries):
        try:
            return await operation()
        except redis.ConnectionError as e:
            if attempt == max_retries - 1:
                raise RedisConnectionError(f"Redis connection failed after {max_retries} attempts") from e
            logger.warning("redis_connection_retry", attempt=attempt + 1, error=str(e))
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

## Monitoring

### Metrics

```python
class RedisMetrics(BaseModel):
    """Redis operation metrics"""
    operation: str  # "queue_add", "queue_claim", "lock_acquire", "lock_release"
    success: bool
    duration_ms: int
    website_id: str | None = None
    session_id: str | None = None
    timestamp: datetime
```

### Health Check

```python
async def redis_health_check() -> Dict[str, Any]:
    """
    Check Redis connection health.

    Returns:
        Health status dictionary
    """
    try:
        start = datetime.utcnow()
        await redis_client.ping()
        latency_ms = (datetime.utcnow() - start).total_seconds() * 1000

        queue_size = await get_queue_size()

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "queue_size": queue_size,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
```

## Configuration Summary

**Local Development** (Docker Redis):
```yaml
REDIS_HOST: localhost
REDIS_PORT: 6379
REDIS_DB: 0
REDIS_PASSWORD: null
REDIS_SSL: false
```

**Production** (Managed Redis):
```yaml
REDIS_HOST: prod.cache.amazonaws.com
REDIS_PORT: 6379
REDIS_DB: 0
REDIS_PASSWORD: <from secrets manager>
REDIS_SSL: true
```

**Zero Code Changes** (FR-026): Configuration loaded from environment, same code runs in both environments.

## Next Steps

1. Implement Redis connection management
2. Implement session queue operations
3. Implement master lock operations with context manager
4. Write contract tests for all operations
5. Set up Docker Redis for local development
6. Configure production Redis connection
7. Implement metrics collection and health checks
