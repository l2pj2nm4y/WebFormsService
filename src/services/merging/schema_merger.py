"""Schema merging service with hierarchical identity and temporal management.

Provides intelligent merging of FormSchema objects using:
- Hierarchical field identity based on section path + field name + type
- jsonmerge library for configurable merge strategies
- Temporal retention policies (30-day default, min 3 versions)
- Merge metadata tracking
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from jsonmerge import Merger
from pydantic import BaseModel

from src.models.schema import FormField, FormSchema, FormSection


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
        section_name = section.name if isinstance(section, FormSection) else section["name"]

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
            field_name = field.name
            field_type = field.type
        else:
            field_name = field.get("name", "")
            field_type = field.get("type", "")

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

    Example:
        merger = SchemaMerger(retention_days=30)

        schemas = [
            SchemaVersion(schema=schema1_dict, timestamp=dt1, version_id="v1"),
            SchemaVersion(schema=schema2_dict, timestamp=dt2, version_id="v2"),
        ]

        merged = merger.merge_schemas(schemas)
    """

    # Default merge configuration for FormSchema structure
    DEFAULT_MERGE_CONFIG = {
        "mergeStrategy": "objectMerge",
        "properties": {
            "form_name": {"mergeStrategy": "overwrite"},
            "description": {"mergeStrategy": "overwrite"},
            "page_identification": {
                "mergeStrategy": "objectMerge",
                "properties": {
                    "url": {"mergeStrategy": "overwrite"},
                    "timestamp": {"mergeStrategy": "overwrite"},
                    "page_headings": {
                        "mergeStrategy": "append",
                        "mergeOptions": {"unique": True},
                    },
                    "form_headings": {
                        "mergeStrategy": "append",
                        "mergeOptions": {"unique": True},
                    },
                    "visual_sections": {
                        "mergeStrategy": "append",
                        "mergeOptions": {"unique": True},
                    },
                    "navigation_buttons": {
                        "mergeStrategy": "append",
                        "mergeOptions": {"unique": True},
                    },
                    "progress_indicator": {"mergeStrategy": "overwrite"},
                    "page_number": {"mergeStrategy": "overwrite"},
                },
            },
            "sections": {
                "mergeStrategy": "arrayMergeById",
                "mergeOptions": {"idRef": "id"},
                "items": {
                    "mergeStrategy": "objectMerge",
                    "properties": {
                        "name": {"mergeStrategy": "overwrite"},
                        "description": {"mergeStrategy": "overwrite"},
                        "fields": {
                            "mergeStrategy": "arrayMergeById",
                            "mergeOptions": {"idRef": "id"},
                            "items": {
                                "mergeStrategy": "objectMerge",
                                "properties": {
                                    "name": {"mergeStrategy": "overwrite"},
                                    "type": {"mergeStrategy": "overwrite"},
                                    "label": {"mergeStrategy": "overwrite"},
                                    "description": {"mergeStrategy": "overwrite"},
                                    "required": {"mergeStrategy": "overwrite"},
                                    "constraints": {
                                        "mergeStrategy": "append",
                                        "mergeOptions": {"unique": True},
                                    },
                                },
                            },
                        },
                        "subsections": {
                            "mergeStrategy": "arrayMergeById",
                            "mergeOptions": {"idRef": "id"},
                        },
                    },
                },
            },
        },
    }

    def __init__(
        self,
        retention_days: int = 30,
        min_versions: int = 3,
        max_versions: int = 100,
        merge_config: dict[str, Any] | None = None,
    ):
        """Initialize schema merger.

        Args:
            retention_days: Days to retain old schema versions (default 30)
            min_versions: Minimum versions to keep regardless of age (default 3)
            max_versions: Maximum versions to prevent unbounded growth (default 100)
            merge_config: Custom jsonmerge configuration (uses DEFAULT_MERGE_CONFIG if None)
        """
        self.retention_days = retention_days
        self.min_versions = min_versions
        self.max_versions = max_versions
        self.merge_config = merge_config or self.DEFAULT_MERGE_CONFIG
        self.merger = Merger(self.merge_config)
        self.identity_computer = HierarchicalIdentityComputer()

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
                metadata={"form_name": model.form_name},
            )
            for model, timestamp, version_id in models
        ]

        # Merge
        merged_dict = self.merge_schemas(schema_versions)

        # Validate and return as Pydantic model
        return FormSchema.model_validate(merged_dict)
