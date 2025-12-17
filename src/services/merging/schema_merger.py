"""Schema merging service with hierarchical identity and temporal management.

Provides intelligent merging of FormSchema objects using:
- Hierarchical field identity based on section path + field name + type
- jsonmerge library for configurable merge strategies
- Temporal retention policies (30-day default, min 3 versions)
- Merge metadata tracking
- Optional DEBUG logging to file for jsonmerge operations
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jsonmerge import Merger
from jsonmerge.strategies import Strategy
from pydantic import BaseModel

from src.lib.logging import (
    configure_jsonmerge_file_logging,
    remove_jsonmerge_file_logging,
)
from src.models.schema import FormField, FormSchema, FormSection
from src.models.timestamped import LEGACY_TIMESTAMP


class NewerTimestampStrategy(Strategy):
    """Custom jsonmerge strategy that keeps the value with the newer timestamp.

    This strategy is designed for TimestampedValue objects which have the structure:
        {"timestamp": "ISO8601 string", "value": <any>}

    When merging two timestamped values, the one with the more recent timestamp wins.
    ISO 8601 timestamps are lexicographically comparable.

    Special cases:
    - If either value is None/undefined, return the other
    - If neither is a proper timestamped dict, fall back to head (newer in sequence)
    - Legacy timestamps (1970-01-01T00:00:00.000Z) are always considered older
    """

    def merge(self, _walk, base, head, _schema, **_kwargs):
        """Merge two timestamped values, keeping the newer one.

        Args:
            _walk: WalkInstance for the current merge context (unused)
            base: JSONValue being merged into (older in merge sequence)
            head: JSONValue being merged (newer in merge sequence)
            _schema: Schema used for merging (unused)
            **_kwargs: Additional merge options (unused)

        Returns:
            The JSONValue with the more recent timestamp
        """
        # Handle undefined/None cases
        if base.is_undef():
            return head
        if head.is_undef():
            return base

        base_val = base.val
        head_val = head.val

        # If either is None, return the other
        if base_val is None:
            return head
        if head_val is None:
            return base

        # Both must be dicts with timestamp and value keys
        if not (isinstance(base_val, dict) and isinstance(head_val, dict)):
            return head  # Fall back to default behavior

        # Check for proper timestamped structure
        base_ts = base_val.get("timestamp")
        head_ts = head_val.get("timestamp")

        if base_ts is None or head_ts is None:
            return head  # Not timestamped values, use default

        # Legacy timestamps are always considered older
        if base_ts == LEGACY_TIMESTAMP and head_ts != LEGACY_TIMESTAMP:
            return head
        if head_ts == LEGACY_TIMESTAMP and base_ts != LEGACY_TIMESTAMP:
            return base

        # ISO 8601 timestamps are lexicographically comparable
        if head_ts > base_ts:
            return head
        return base

    def get_schema(self, _walk, schema, **_kwargs):
        """Return the schema for the merged document.

        For timestamped values, the schema structure remains the same.
        """
        return schema


class TimestampedListMergeStrategy(Strategy):
    """Merge lists of TimestampedValue objects, matching by value and keeping newer timestamps.

    This strategy is designed for lists where each item has the structure:
        {"timestamp": "ISO8601 string", "value": <any>}

    Merge behavior:
    - Items are matched by their 'value' field (not by timestamp or position)
    - For matching values: keep the entry with the newer timestamp
    - For new values in head: append to the result
    - Result is a deduplicated list where each unique value has the newest observed timestamp

    Example:
        Base: [{"timestamp": "2025-01-01", "value": "A"}, {"timestamp": "2025-01-01", "value": "B"}]
        Head: [{"timestamp": "2025-01-15", "value": "A"}, {"timestamp": "2025-01-10", "value": "C"}]
        Result: [
            {"timestamp": "2025-01-15", "value": "A"},  # Updated timestamp
            {"timestamp": "2025-01-01", "value": "B"},  # Unchanged
            {"timestamp": "2025-01-10", "value": "C"},  # Added
        ]
    """

    def merge(self, _walk, base, head, _schema, **_kwargs):
        """Merge two lists of timestamped values, deduplicating by value.

        Args:
            _walk: WalkInstance for the current merge context (unused)
            base: JSONValue containing the base list
            head: JSONValue containing the head list to merge in
            _schema: Schema used for merging (unused)
            **_kwargs: Additional merge options (unused)

        Returns:
            JSONValue containing the merged list
        """
        from jsonmerge.jsonvalue import JSONValue

        # Handle undefined/None cases
        if base.is_undef():
            return head
        if head.is_undef():
            return base

        base_list = base.val
        head_list = head.val

        # Handle None values
        if base_list is None:
            return head
        if head_list is None:
            return base

        # Ensure both are lists
        if not isinstance(base_list, list):
            base_list = []
        if not isinstance(head_list, list):
            head_list = []

        # Build a map of value -> best timestamped entry from base
        # Using the actual value as the key for deduplication
        value_map: dict[Any, dict[str, Any]] = {}

        for item in base_list:
            if isinstance(item, dict) and "value" in item:
                val = item.get("value")
                # Use a hashable key (convert to string for unhashable types)
                key = val if isinstance(val, (str, int, float, bool, type(None))) else str(val)
                value_map[key] = item

        # Process head list - update existing or add new
        for item in head_list:
            if isinstance(item, dict) and "value" in item:
                val = item.get("value")
                key = val if isinstance(val, (str, int, float, bool, type(None))) else str(val)

                if key in value_map:
                    # Compare timestamps and keep newer
                    existing = value_map[key]
                    existing_ts = existing.get("timestamp", LEGACY_TIMESTAMP)
                    new_ts = item.get("timestamp", LEGACY_TIMESTAMP)

                    # Legacy timestamps always lose
                    if existing_ts == LEGACY_TIMESTAMP and new_ts != LEGACY_TIMESTAMP:
                        value_map[key] = item
                    elif new_ts != LEGACY_TIMESTAMP and new_ts > existing_ts:
                        value_map[key] = item
                    # Otherwise keep existing (base wins on equal timestamps)
                else:
                    # New value - add to map
                    value_map[key] = item
            else:
                # Non-timestamped item - just add with a generated key
                # This handles edge cases but shouldn't normally occur
                value_map[id(item)] = item

        # Convert back to list, preserving insertion order (Python 3.7+)
        result = list(value_map.values())

        return JSONValue(result, base.ref)

    def get_schema(self, _walk, schema, **_kwargs):
        """Return the schema for the merged document.

        For timestamped lists, the schema structure remains the same.
        """
        return schema


@dataclass
class SchemaVersion:
    """Container for a versioned schema with timestamp metadata.

    Attributes:
        schema: The FormSchema as a dictionary
        timestamp: When this schema version was created
        version_id: Unique identifier for this version
        sequence_number: Optional quartet sequence number
        metadata: Additional metadata about this version
    """

    schema: dict[str, Any]
    timestamp: datetime
    version_id: str
    sequence_number: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class HierarchicalIdentityComputer:
    """Computes stable field identities based on hierarchical section paths.

    Fields are uniquely identified by their position in the section hierarchy,
    their name, and their type. This ensures that 'Applicant.firstName' and
    'Spouse.firstName' are treated as different fields.

    Example:
        Section path: "Applicant.PersonalInfo"
        Field: {"name": "email", "type": "email"}
        Identity: hash("Applicant.PersonalInfo::email::email")
    """

    def compute_section_path(
        self, section: FormSection | dict[str, Any], parent_path: str = ""
    ) -> str:
        """Build full hierarchical path for a section.

        Args:
            section: FormSection object or dict with 'name' key
            parent_path: Path of parent section (empty for top-level)

        Returns:
            Full section path like "Applicant.PersonalInfo.Contact"
        """
        if isinstance(section, FormSection):
            section_name = section.name.value
        else:
            # Dict format - could be timestamped or plain
            name_value = section["name"]
            section_name = name_value["value"] if isinstance(name_value, dict) and "value" in name_value else name_value

        if parent_path:
            return f"{parent_path}.{section_name}"
        return section_name

    def compute_field_id(
        self, field: FormField | dict[str, Any], section_path: str
    ) -> str:
        """Compute stable ID for a field based on hierarchical position.

        Args:
            field: FormField object or dict with 'name' and 'type' keys
            section_path: Full path of containing section

        Returns:
            16-character hex hash of "section_path::field_name::field_type"
        """
        if isinstance(field, FormField):
            field_name = field.name.value
            field_type = field.type.value
        else:
            # Dict format - could be timestamped or plain
            name_value = field.get("name", "")
            type_value = field.get("type", "")
            field_name = name_value["value"] if isinstance(name_value, dict) and "value" in name_value else name_value
            field_type = type_value["value"] if isinstance(type_value, dict) and "value" in type_value else type_value

        # Create stable identity string
        identity_components = [section_path, field_name, field_type]
        identity_str = "::".join(c for c in identity_components if c)

        # Hash for compact representation
        hash_digest = hashlib.sha256(identity_str.encode("utf-8")).hexdigest()
        return hash_digest[:16]

    def enrich_section_with_ids(
        self, section: dict[str, Any], parent_path: str = ""
    ) -> dict[str, Any]:
        """Recursively add IDs to all fields in a section and its subsections.

        Args:
            section: Section dictionary to enrich
            parent_path: Path of parent section

        Returns:
            Enriched section dictionary with IDs added to all fields
        """
        enriched = section.copy()
        section_path = self.compute_section_path(enriched, parent_path)

        # Add ID to section itself
        if "id" not in enriched:
            section_id_str = f"section::{section_path}"
            enriched["id"] = hashlib.sha256(section_id_str.encode()).hexdigest()[:16]

        # Add IDs to fields
        if "fields" in enriched and isinstance(enriched["fields"], list):
            enriched["fields"] = [
                {**field, "id": self.compute_field_id(field, section_path)}
                if "id" not in field
                else field
                for field in enriched["fields"]
            ]

        # Recursively process subsections
        if "subsections" in enriched and isinstance(enriched["subsections"], list):
            enriched["subsections"] = [
                self.enrich_section_with_ids(subsection, section_path)
                for subsection in enriched["subsections"]
            ]

        return enriched

    def enrich_schema_with_ids(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Add hierarchical IDs to all sections and fields in a schema.

        Args:
            schema: FormSchema dictionary

        Returns:
            Enriched schema with IDs added to all sections and fields
        """
        enriched = schema.copy()

        if "sections" in enriched and isinstance(enriched["sections"], list):
            enriched["sections"] = [
                self.enrich_section_with_ids(section) for section in enriched["sections"]
            ]

        return enriched


class SchemaMerger:
    """Intelligent schema merger with hierarchical identity and temporal management.

    Combines multiple FormSchema versions using:
    - Hierarchical field matching (section path + name + type)
    - Configurable merge strategies via jsonmerge
    - Temporal retention policies
    - Merge metadata generation

    Two merge modes are supported:
    - SESSION_MERGE_CONFIG: For merging schemas within a single session (newer overwrites older)
    - MASTER_MERGE_CONFIG: For merging session schemas into a master schema (accumulative)

    Example:
        merger = SchemaMerger(retention_days=30)

        schemas = [
            SchemaVersion(schema=schema1_dict, timestamp=dt1, version_id="v1"),
            SchemaVersion(schema=schema2_dict, timestamp=dt2, version_id="v2"),
        ]

        merged = merger.merge_schemas(schemas)
    """

    # Session merge configuration: newer values overwrite older ones within a session.
    # Used when merging multiple captures from the same browsing session.
    # Newer information is considered more accurate as it reflects the latest page state.
    SESSION_MERGE_CONFIG: dict[str, Any] = {
        "mergeStrategy": "objectMerge",
        "properties": {
            # Top-level TimestampedValue fields
            "page_identifier": {
                "mergeStrategy": "objectMerge",
                "properties": {
                    "timestamp": {"mergeStrategy": "overwrite"},
                    "value": {"mergeStrategy": "overwrite"},
                },
            },
            "form_name": {
                "mergeStrategy": "objectMerge",
                "properties": {
                    "timestamp": {"mergeStrategy": "overwrite"},
                    "value": {"mergeStrategy": "overwrite"},
                },
            },
            "description": {
                "mergeStrategy": "objectMerge",
                "properties": {
                    "timestamp": {"mergeStrategy": "overwrite"},
                    "value": {"mergeStrategy": "overwrite"},
                },
            },
            # PageIdentification - all properties now use TimestampedValue wrappers
            # For session merging, we use overwrite for nullable scalar properties
            # to handle None -> TimestampedValue transitions gracefully
            "page_identification": {
                "mergeStrategy": "objectMerge",
                "properties": {
                    # Nullable scalar TimestampedValue properties - use overwrite
                    # to handle None values (objectMerge fails on None -> object)
                    "url": {"mergeStrategy": "overwrite"},
                    # List properties - use timestampedListMerge for deduplication by value
                    "page_headings": {"mergeStrategy": "timestampedListMerge"},
                    "form_headings": {"mergeStrategy": "timestampedListMerge"},
                    "visual_sections": {"mergeStrategy": "timestampedListMerge"},
                    "navigation_buttons": {"mergeStrategy": "timestampedListMerge"},
                    # Nullable scalar TimestampedValue properties - use overwrite
                    "progress_indicator": {"mergeStrategy": "overwrite"},
                    "page_number": {"mergeStrategy": "overwrite"},
                },
            },
            # Sections array with full nested structure
            "sections": {
                "mergeStrategy": "arrayMergeById",
                "mergeOptions": {"idRef": "id"},
                "items": {
                    "mergeStrategy": "objectMerge",
                    "properties": {
                        # ID for matching (added by enrichment)
                        "id": {"mergeStrategy": "overwrite"},
                        # Required TimestampedValue fields
                        "name": {
                            "mergeStrategy": "objectMerge",
                            "properties": {
                                "timestamp": {"mergeStrategy": "overwrite"},
                                "value": {"mergeStrategy": "overwrite"},
                            },
                        },
                        "description": {
                            "mergeStrategy": "objectMerge",
                            "properties": {
                                "timestamp": {"mergeStrategy": "overwrite"},
                                "value": {"mergeStrategy": "overwrite"},
                            },
                        },
                        # Optional TimestampedValue fields - use overwrite to handle None
                        "required": {"mergeStrategy": "overwrite"},
                        # Section visibility rules
                        "visibility_rules": {
                            "mergeStrategy": "arrayMergeById",
                            "mergeOptions": {"idRef": "field"},
                            "items": {
                                "mergeStrategy": "objectMerge",
                                "properties": {
                                    "timestamp": {"mergeStrategy": "overwrite"},
                                    "field": {"mergeStrategy": "overwrite"},
                                    "operator": {"mergeStrategy": "overwrite"},
                                    "value": {"mergeStrategy": "overwrite"},
                                },
                            },
                        },
                        # Fields array with complete field definitions
                        "fields": {
                            "mergeStrategy": "arrayMergeById",
                            "mergeOptions": {"idRef": "id"},
                            "items": {
                                "mergeStrategy": "objectMerge",
                                "properties": {
                                    # ID for matching (added by enrichment)
                                    "id": {"mergeStrategy": "overwrite"},
                                    # Required TimestampedValue fields
                                    "name": {
                                        "mergeStrategy": "objectMerge",
                                        "properties": {
                                            "timestamp": {"mergeStrategy": "overwrite"},
                                            "value": {"mergeStrategy": "overwrite"},
                                        },
                                    },
                                    "type": {
                                        "mergeStrategy": "objectMerge",
                                        "properties": {
                                            "timestamp": {"mergeStrategy": "overwrite"},
                                            "value": {"mergeStrategy": "overwrite"},
                                        },
                                    },
                                    "description": {
                                        "mergeStrategy": "objectMerge",
                                        "properties": {
                                            "timestamp": {"mergeStrategy": "overwrite"},
                                            "value": {"mergeStrategy": "overwrite"},
                                        },
                                    },
                                    # Optional TimestampedValue fields - use overwrite to handle None
                                    "required": {"mergeStrategy": "overwrite"},
                                    "label": {"mergeStrategy": "overwrite"},
                                    "placeholder": {"mergeStrategy": "overwrite"},
                                    "default_value": {"mergeStrategy": "overwrite"},
                                    "sensitive": {"mergeStrategy": "overwrite"},
                                    "input_format": {"mergeStrategy": "overwrite"},
                                    # Lists with embedded timestamps
                                    "constraints": {
                                        "mergeStrategy": "arrayMergeById",
                                        "mergeOptions": {"idRef": "type"},
                                        "items": {
                                            "mergeStrategy": "objectMerge",
                                            "properties": {
                                                "timestamp": {"mergeStrategy": "overwrite"},
                                                "type": {"mergeStrategy": "overwrite"},
                                                "value": {"mergeStrategy": "overwrite"},
                                                "message": {"mergeStrategy": "overwrite"},
                                            },
                                        },
                                    },
                                    # options is list[TimestampedValue[str]] | None - use overwrite
                                    "options": {"mergeStrategy": "overwrite"},
                                    "visibility_rules": {
                                        "mergeStrategy": "arrayMergeById",
                                        "mergeOptions": {"idRef": "field"},
                                        "items": {
                                            "mergeStrategy": "objectMerge",
                                            "properties": {
                                                "timestamp": {"mergeStrategy": "overwrite"},
                                                "field": {"mergeStrategy": "overwrite"},
                                                "operator": {"mergeStrategy": "overwrite"},
                                                "value": {"mergeStrategy": "overwrite"},
                                            },
                                        },
                                    },
                                    # Optional object types - use overwrite to handle None
                                    "table_config": {"mergeStrategy": "overwrite"},
                                    "array_config": {"mergeStrategy": "overwrite"},
                                },
                            },
                        },
                        # Subsections - recursive structure (uses same pattern as sections)
                        "subsections": {
                            "mergeStrategy": "arrayMergeById",
                            "mergeOptions": {"idRef": "id"},
                        },
                    },
                },
            },
        },
    }

    # Master merge configuration: accumulative merge for building master schemas.
    # Used when merging session schemas into a master schema across multiple sessions.
    # Uses newerTimestamp strategy to keep the value with the most recent timestamp.
    MASTER_MERGE_CONFIG: dict[str, Any] = {
        "mergeStrategy": "objectMerge",
        "properties": {
            # Top-level TimestampedValue fields - use newerTimestamp
            "page_identifier": {"mergeStrategy": "newerTimestamp"},
            "form_name": {"mergeStrategy": "newerTimestamp"},
            "description": {"mergeStrategy": "newerTimestamp"},
            # PageIdentification - all properties now use TimestampedValue wrappers
            "page_identification": {
                "mergeStrategy": "objectMerge",
                "properties": {
                    # Scalar TimestampedValue properties - use newerTimestamp
                    "url": {"mergeStrategy": "newerTimestamp"},
                    # List properties - use timestampedListMerge for deduplication by value
                    "page_headings": {"mergeStrategy": "timestampedListMerge"},
                    "form_headings": {"mergeStrategy": "timestampedListMerge"},
                    "visual_sections": {"mergeStrategy": "timestampedListMerge"},
                    "navigation_buttons": {"mergeStrategy": "timestampedListMerge"},
                    # Scalar TimestampedValue properties - use newerTimestamp
                    "progress_indicator": {"mergeStrategy": "newerTimestamp"},
                    "page_number": {"mergeStrategy": "newerTimestamp"},
                },
            },
            # Sections array with full nested structure
            "sections": {
                "mergeStrategy": "arrayMergeById",
                "mergeOptions": {"idRef": "id"},
                "items": {
                    "mergeStrategy": "objectMerge",
                    "properties": {
                        # ID for matching (added by enrichment)
                        "id": {"mergeStrategy": "overwrite"},
                        # Required TimestampedValue fields - use newerTimestamp
                        "name": {"mergeStrategy": "newerTimestamp"},
                        "description": {"mergeStrategy": "newerTimestamp"},
                        # Optional TimestampedValue fields - use newerTimestamp
                        "required": {"mergeStrategy": "newerTimestamp"},
                        # Section visibility rules
                        "visibility_rules": {
                            "mergeStrategy": "arrayMergeById",
                            "mergeOptions": {"idRef": "field"},
                            "items": {
                                "mergeStrategy": "objectMerge",
                                "properties": {
                                    "timestamp": {"mergeStrategy": "overwrite"},
                                    "field": {"mergeStrategy": "overwrite"},
                                    "operator": {"mergeStrategy": "overwrite"},
                                    "value": {"mergeStrategy": "overwrite"},
                                },
                            },
                        },
                        # Fields array with complete field definitions
                        "fields": {
                            "mergeStrategy": "arrayMergeById",
                            "mergeOptions": {"idRef": "id"},
                            "items": {
                                "mergeStrategy": "objectMerge",
                                "properties": {
                                    # ID for matching (added by enrichment)
                                    "id": {"mergeStrategy": "overwrite"},
                                    # Required TimestampedValue fields - use newerTimestamp
                                    "name": {"mergeStrategy": "newerTimestamp"},
                                    "type": {"mergeStrategy": "newerTimestamp"},
                                    "description": {"mergeStrategy": "newerTimestamp"},
                                    # Optional TimestampedValue fields - use newerTimestamp
                                    "required": {"mergeStrategy": "newerTimestamp"},
                                    "label": {"mergeStrategy": "newerTimestamp"},
                                    "placeholder": {"mergeStrategy": "newerTimestamp"},
                                    "default_value": {"mergeStrategy": "newerTimestamp"},
                                    "sensitive": {"mergeStrategy": "newerTimestamp"},
                                    "input_format": {"mergeStrategy": "newerTimestamp"},
                                    # Lists with embedded timestamps
                                    "constraints": {
                                        "mergeStrategy": "arrayMergeById",
                                        "mergeOptions": {"idRef": "type"},
                                        "items": {
                                            "mergeStrategy": "objectMerge",
                                            "properties": {
                                                "timestamp": {"mergeStrategy": "overwrite"},
                                                "type": {"mergeStrategy": "overwrite"},
                                                "value": {"mergeStrategy": "overwrite"},
                                                "message": {"mergeStrategy": "overwrite"},
                                            },
                                        },
                                    },
                                    # options is list[TimestampedValue[str]] | None - use overwrite
                                    "options": {"mergeStrategy": "overwrite"},
                                    "visibility_rules": {
                                        "mergeStrategy": "arrayMergeById",
                                        "mergeOptions": {"idRef": "field"},
                                        "items": {
                                            "mergeStrategy": "objectMerge",
                                            "properties": {
                                                "timestamp": {"mergeStrategy": "overwrite"},
                                                "field": {"mergeStrategy": "overwrite"},
                                                "operator": {"mergeStrategy": "overwrite"},
                                                "value": {"mergeStrategy": "overwrite"},
                                            },
                                        },
                                    },
                                    # Optional object types - use overwrite to handle None
                                    "table_config": {"mergeStrategy": "overwrite"},
                                    "array_config": {"mergeStrategy": "overwrite"},
                                },
                            },
                        },
                        # Subsections - recursive structure (uses same pattern as sections)
                        "subsections": {
                            "mergeStrategy": "arrayMergeById",
                            "mergeOptions": {"idRef": "id"},
                        },
                    },
                },
            },
        },
    }

    # Default to session merge config for backward compatibility
    DEFAULT_MERGE_CONFIG = SESSION_MERGE_CONFIG

    def __init__(
        self,
        retention_days: int = 30,
        min_versions: int = 3,
        max_versions: int = 100,
        merge_config: dict[str, Any] | None = None,
        debug_dir: Path | str | None = None,
    ):
        """Initialize schema merger.

        Args:
            retention_days: Days to retain old schema versions (default 30)
            min_versions: Minimum versions to keep regardless of age (default 3)
            max_versions: Maximum versions to prevent unbounded growth (default 100)
            merge_config: Custom jsonmerge configuration (uses DEFAULT_MERGE_CONFIG if None)
            debug_dir: Directory for jsonmerge DEBUG logs. If provided, enables file logging.
        """
        self.retention_days = retention_days
        self.min_versions = min_versions
        self.max_versions = max_versions
        self.merge_config = merge_config or self.DEFAULT_MERGE_CONFIG
        # Register custom strategies with jsonmerge
        self.merger = Merger(
            self.merge_config,
            strategies={
                "newerTimestamp": NewerTimestampStrategy(),
                "timestampedListMerge": TimestampedListMergeStrategy(),
            },
        )
        self.identity_computer = HierarchicalIdentityComputer()

        # Configure jsonmerge file logging if debug_dir provided
        self._jsonmerge_handler: logging.FileHandler | None = None
        if debug_dir:
            log_file = Path(debug_dir) / "jsonmerge.log"
            self._jsonmerge_handler = configure_jsonmerge_file_logging(log_file)

    def close(self) -> None:
        """Clean up resources, including jsonmerge file handler."""
        if self._jsonmerge_handler:
            remove_jsonmerge_file_logging(self._jsonmerge_handler)
            self._jsonmerge_handler = None

    def filter_by_retention_policy(
        self, schemas: list[SchemaVersion]
    ) -> tuple[list[SchemaVersion], list[SchemaVersion]]:
        """Apply retention policy to schemas.

        Keeps schemas that are:
        - Within the last N most recent versions (min_versions), OR
        - Within the retention period (retention_days)

        Enforces maximum version limit.

        Args:
            schemas: List of schema versions to filter

        Returns:
            Tuple of (active_schemas, retired_schemas)
        """
        # Sort by timestamp (newest first)
        sorted_schemas = sorted(schemas, key=lambda s: s.timestamp, reverse=True)

        # Enforce maximum versions
        if len(sorted_schemas) > self.max_versions:
            kept = sorted_schemas[: self.max_versions]
            retired = sorted_schemas[self.max_versions :]
            return kept, retired

        # Always keep minimum versions
        if len(sorted_schemas) <= self.min_versions:
            return sorted_schemas, []

        # Calculate cutoff date
        cutoff = datetime.now() - timedelta(days=self.retention_days)

        active = []
        retired = []

        for i, schema in enumerate(sorted_schemas):
            # Keep if within min_versions OR within retention period
            if i < self.min_versions or schema.timestamp >= cutoff:
                active.append(schema)
            else:
                retired.append(schema)

        return active, retired

    def merge_schemas(
        self,
        schemas: list[SchemaVersion],
        include_metadata: bool = True,
    ) -> dict[str, Any]:
        """Merge multiple schema versions into a single master schema.

        Process:
        1. Apply retention policy
        2. Sort by timestamp (oldest first for sequential merging)
        3. Enrich with hierarchical IDs
        4. Sequential merge using jsonmerge
        5. Add merge metadata

        Args:
            schemas: List of schema versions to merge
            include_metadata: Whether to include merge metadata in result

        Returns:
            Merged schema dictionary

        Raises:
            ValueError: If no schemas provided or no active schemas after filtering
        """
        if not schemas:
            raise ValueError("No schemas provided for merging")

        # Step 1: Apply retention policy
        active_schemas, retired_schemas = self.filter_by_retention_policy(schemas)

        if not active_schemas:
            raise ValueError("No active schemas after applying retention policy")

        # Step 2: Sort by timestamp (oldest first for sequential merging)
        sorted_schemas = sorted(active_schemas, key=lambda s: s.timestamp)

        # Step 3: Enrich with hierarchical IDs
        enriched_schemas = [
            self.identity_computer.enrich_schema_with_ids(s.schema) for s in sorted_schemas
        ]

        # Step 4: Sequential merge
        result = enriched_schemas[0].copy()

        for schema in enriched_schemas[1:]:
            result = self.merger.merge(result, schema)

        # Step 5: Add merge metadata
        if include_metadata:
            result["_merge_metadata"] = {
                "merged_at": datetime.now().isoformat(),
                "source_count": len(active_schemas),
                "retired_count": len(retired_schemas),
                "version_ids": [s.version_id for s in sorted_schemas],
                "sequence_numbers": [
                    s.sequence_number for s in sorted_schemas if s.sequence_number is not None
                ],
                "oldest_timestamp": sorted_schemas[0].timestamp.isoformat(),
                "newest_timestamp": sorted_schemas[-1].timestamp.isoformat(),
                "retention_days": self.retention_days,
                "min_versions": self.min_versions,
            }

        return result

    def merge_pydantic_models(
        self,
        models: list[tuple[FormSchema, datetime, str]],
    ) -> FormSchema:
        """Merge Pydantic FormSchema model instances.

        Convenience method that converts Pydantic models to SchemaVersion objects,
        merges them, and validates the result.

        Args:
            models: List of tuples (FormSchema, timestamp, version_id)

        Returns:
            Merged FormSchema validated as Pydantic model

        Example:
            models = [
                (schema1, datetime(2024, 1, 1), "v1"),
                (schema2, datetime(2024, 1, 15), "v2"),
            ]
            merged = merger.merge_pydantic_models(models)
        """
        # Convert to SchemaVersion objects
        schema_versions = [
            SchemaVersion(
                schema=model.model_dump(mode="json"),
                timestamp=timestamp,
                version_id=version_id,
                metadata={"form_name": model.form_name.value},
            )
            for model, timestamp, version_id in models
        ]

        # Merge
        merged_dict = self.merge_schemas(schema_versions)

        # Validate and return as Pydantic model
        return FormSchema.model_validate(merged_dict)
