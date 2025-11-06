"""Redis coordination layer for distributed operations.

Provides session queue management and distributed locking for master folders
to enable concurrent backend processing without conflicts.
"""

from src.services.coordination.master_lock import LockAcquisitionError, MasterLock
from src.services.coordination.redis_connection import (
    close_redis_client,
    get_redis_client,
    redis_health_check,
    reset_redis_client,
)
from src.services.coordination.session_queue import (
    claim_next_session,
    clear_queue,
    enqueue_session,
    get_queue_size,
    peek_next_sessions,
    remove_session_from_queue,
)

__all__ = [
    # Redis connection
    "get_redis_client",
    "close_redis_client",
    "redis_health_check",
    "reset_redis_client",
    # Session queue
    "enqueue_session",
    "claim_next_session",
    "get_queue_size",
    "peek_next_sessions",
    "remove_session_from_queue",
    "clear_queue",
    # Master locks
    "MasterLock",
    "LockAcquisitionError",
]
