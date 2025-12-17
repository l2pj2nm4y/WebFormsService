"""
Timestamped value wrapper for property-level temporal tracking.

This module provides a generic wrapper type that pairs any value with an ISO 8601
timestamp, enabling:
- Tracking when each property was observed/captured
- Merge decisions based on recency (newer wins)
- Expiration of stale properties
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")

# Sentinel timestamp indicating legacy/unknown capture time
LEGACY_TIMESTAMP = "1970-01-01T00:00:00.000Z"


class TimestampedValue(BaseModel, Generic[T]):
    """Wrapper that pairs any value with a timestamp.

    Used for property-level temporal tracking in schema models.
    When merging schemas, the timestamp determines which value is newer.

    Example:
        >>> name = TimestampedValue[str](timestamp="2025-11-26T10:41:58.968Z", value="firstName")
        >>> name.value
        'firstName'
        >>> name.timestamp
        '2025-11-26T10:41:58.968Z'
    """

    timestamp: str = Field(
        ..., description="ISO 8601 timestamp when this value was observed"
    )
    value: T = Field(..., description="The actual value")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy(cls, data: Any) -> dict[str, Any]:
        """Accept legacy non-timestamped values for backward compatibility.

        When loading old schemas without timestamps, this validator wraps
        the raw value with an epoch timestamp to indicate "unknown age".
        This ensures older schemas can still be loaded while new schemas
        have proper timestamps.

        Args:
            data: Either a dict with timestamp/value keys (new format)
                  or a raw value (legacy format)

        Returns:
            Dict in the new timestamped format
        """
        # Already in new format
        if isinstance(data, dict) and "timestamp" in data and "value" in data:
            return data

        # Legacy format - wrap with epoch timestamp
        return {"timestamp": LEGACY_TIMESTAMP, "value": data}

    def is_legacy(self) -> bool:
        """Check if this value has a legacy/unknown timestamp.

        Returns:
            True if the timestamp is the epoch sentinel value
        """
        return self.timestamp == LEGACY_TIMESTAMP

    def is_newer_than(self, other: TimestampedValue[T]) -> bool:
        """Compare timestamps to determine which value is newer.

        ISO 8601 timestamps are lexicographically comparable.

        Args:
            other: Another timestamped value to compare against

        Returns:
            True if this value's timestamp is more recent than other's
        """
        return self.timestamp > other.timestamp
