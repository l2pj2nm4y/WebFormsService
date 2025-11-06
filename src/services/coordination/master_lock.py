"""Redis-based distributed locking for master folders.

Implements distributed locks using Redis SET NX EX pattern to prevent
concurrent writes to master folders from multiple backend processes.
"""

import os
import socket
from typing import Any

from src.lib.config import get_config
from src.services.coordination.redis_connection import get_redis_client


class LockAcquisitionError(Exception):
    """Raised when lock cannot be acquired."""

    pass


class MasterLock:
    """Distributed lock for master folder write operations."""

    def __init__(self, website_id: str, ttl: int | None = None) -> None:
        """Initialize master lock.

        Args:
            website_id: Website identifier
            ttl: Lock TTL in seconds (defaults to config value)
        """
        self.website_id = website_id
        self.lock_key = f"lock:master:{website_id}"

        # Generate unique worker ID
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}"

        config = get_config()
        self.ttl = ttl if ttl is not None else config.redis.default_lock_ttl

        self.locked = False

    async def acquire(self, timeout: float = 0) -> bool:
        """Acquire distributed lock using SET NX EX.

        Args:
            timeout: How long to wait for lock (0 = no wait)

        Returns:
            bool: True if lock acquired, False otherwise

        Raises:
            ConnectionError: If Redis connection fails
        """
        client = await get_redis_client()

        # SET NX EX: set if not exists with expiration
        result = await client.set(
            self.lock_key, self.worker_id, nx=True, ex=self.ttl
        )

        self.locked = bool(result)
        return self.locked

    async def release(self) -> bool:
        """Release distributed lock (only if we own it).

        Returns:
            bool: True if lock was released, False if we don't own it

        Raises:
            ConnectionError: If Redis connection fails
        """
        if not self.locked:
            return False

        client = await get_redis_client()

        # Lua script for atomic check-and-delete
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        result = await client.eval(lua_script, 1, self.lock_key, self.worker_id)
        released = bool(result)

        if released:
            self.locked = False

        return released

    async def extend(self, additional_ttl: int | None = None) -> bool:
        """Extend lock TTL (only if we own it).

        Args:
            additional_ttl: Additional seconds to add (defaults to original TTL)

        Returns:
            bool: True if extended, False if we don't own the lock

        Raises:
            ConnectionError: If Redis connection fails
        """
        if not self.locked:
            return False

        client = await get_redis_client()
        ttl_to_add = additional_ttl if additional_ttl is not None else self.ttl

        # Lua script for atomic check-and-extend
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """

        result = await client.eval(
            lua_script, 1, self.lock_key, self.worker_id, ttl_to_add
        )

        return bool(result)

    async def is_locked(self) -> bool:
        """Check if lock exists (may be owned by another worker).

        Returns:
            bool: True if lock exists

        Raises:
            ConnectionError: If Redis connection fails
        """
        client = await get_redis_client()
        return await client.exists(self.lock_key) > 0

    async def get_lock_owner(self) -> str | None:
        """Get worker ID of lock owner.

        Returns:
            str | None: Worker ID if lock exists, None otherwise

        Raises:
            ConnectionError: If Redis connection fails
        """
        client = await get_redis_client()
        owner = await client.get(self.lock_key)

        if owner:
            return owner.decode("utf-8")

        return None

    async def force_release(self) -> bool:
        """Force release lock (admin operation, use with extreme caution).

        Returns:
            bool: True if lock was released

        Raises:
            ConnectionError: If Redis connection fails
        """
        client = await get_redis_client()
        result = await client.delete(self.lock_key)

        if result:
            self.locked = False

        return bool(result)

    async def __aenter__(self) -> "MasterLock":
        """Async context manager entry."""
        acquired = await self.acquire()

        if not acquired:
            raise LockAcquisitionError(
                f"Could not acquire lock for {self.website_id}"
            )

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.release()
