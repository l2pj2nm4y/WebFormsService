"""Unit tests for schema merging service.

Tests hierarchical identity computation, temporal retention policies,
and merge operations for FormSchema objects.
"""

from datetime import datetime, timedelta

import pytest

from src.models.schema import FormField, FormSchema, FormSection
from src.models.timestamped import LEGACY_TIMESTAMP
from src.services.merging.schema_merger import (
    HierarchicalIdentityComputer,
    NewerTimestampStrategy,
    SchemaMerger,
    SchemaVersion,
)


class TestHierarchicalIdentityComputer:
    """Tests for hierarchical identity computation."""

    def test_compute_section_path_top_level(self) -> None:
        """Test section path for top-level section."""
        computer = HierarchicalIdentityComputer()
        section = {"name": "Applicant"}

        path = computer.compute_section_path(section)

        assert path == "Applicant"

    def test_compute_section_path_nested(self) -> None:
        """Test section path for nested section."""
        computer = HierarchicalIdentityComputer()
        section = {"name": "Contact"}
        parent_path = "Applicant.PersonalInfo"

        path = computer.compute_section_path(section, parent_path)

        assert path == "Applicant.PersonalInfo.Contact"

    def test_compute_field_id_unique_by_path(self) -> None:
        """Test that same field name in different sections gets different IDs."""
        computer = HierarchicalIdentityComputer()

        field = {"name": "firstName", "type": "string"}

        id1 = computer.compute_field_id(field, "Applicant")
        id2 = computer.compute_field_id(field, "Spouse")

        assert id1 != id2
        assert len(id1) == 16  # 16-character hex
        assert len(id2) == 16

    def test_compute_field_id_deterministic(self) -> None:
        """Test that field ID is deterministic (same inputs = same output)."""
        computer = HierarchicalIdentityComputer()

        field = {"name": "email", "type": "email"}
        section_path = "Applicant.Contact"

        id1 = computer.compute_field_id(field, section_path)
        id2 = computer.compute_field_id(field, section_path)

        assert id1 == id2

    def test_enrich_section_with_ids_simple(self) -> None:
        """Test enriching a simple section with field IDs."""
        computer = HierarchicalIdentityComputer()

        section = {
            "name": "PersonalInfo",
            "description": "Personal information",
            "fields": [
                {"name": "firstName", "type": "string"},
                {"name": "lastName", "type": "string"},
            ],
            "subsections": [],
        }

        enriched = computer.enrich_section_with_ids(section)

        assert "id" in enriched  # Section gets ID
        assert all("id" in field for field in enriched["fields"])
        assert enriched["fields"][0]["id"] != enriched["fields"][1]["id"]

    def test_enrich_section_with_ids_nested(self) -> None:
        """Test enriching nested sections with hierarchical IDs."""
        computer = HierarchicalIdentityComputer()

        section = {
            "name": "Applicant",
            "description": "Applicant info",
            "fields": [{"name": "applicantId", "type": "string"}],
            "subsections": [
                {
                    "name": "Contact",
                    "description": "Contact details",
                    "fields": [
                        {"name": "email", "type": "email"},
                        {"name": "phone", "type": "tel"},
                    ],
                    "subsections": [],
                }
            ],
        }

        enriched = computer.enrich_section_with_ids(section)

        # Check section IDs
        assert "id" in enriched
        assert "id" in enriched["subsections"][0]

        # Check field IDs
        assert "id" in enriched["fields"][0]
        assert "id" in enriched["subsections"][0]["fields"][0]
        assert "id" in enriched["subsections"][0]["fields"][1]

        # Verify different IDs for different hierarchical positions
        applicant_field_id = enriched["fields"][0]["id"]
        contact_email_id = enriched["subsections"][0]["fields"][0]["id"]
        assert applicant_field_id != contact_email_id

    def test_enrich_section_preserves_existing_ids(self) -> None:
        """Test that existing IDs are preserved."""
        computer = HierarchicalIdentityComputer()

        existing_id = "custom_id_12345"
        section = {
            "name": "Test",
            "description": "Test section",
            "fields": [{"name": "test", "type": "string", "id": existing_id}],
            "subsections": [],
        }

        enriched = computer.enrich_section_with_ids(section)

        assert enriched["fields"][0]["id"] == existing_id

    def test_enrich_schema_with_ids(self) -> None:
        """Test enriching entire schema with IDs."""
        computer = HierarchicalIdentityComputer()

        schema = {
            "form_name": "Test Form",
            "description": "Test",
            "sections": [
                {
                    "name": "Section1",
                    "description": "First section",
                    "fields": [{"name": "field1", "type": "string"}],
                    "subsections": [],
                },
                {
                    "name": "Section2",
                    "description": "Second section",
                    "fields": [{"name": "field2", "type": "number"}],
                    "subsections": [],
                },
            ],
        }

        enriched = computer.enrich_schema_with_ids(schema)

        assert "sections" in enriched
        assert all("id" in section for section in enriched["sections"])
        assert all(
            "id" in field
            for section in enriched["sections"]
            for field in section["fields"]
        )


class TestSchemaMergerRetentionPolicy:
    """Tests for temporal retention policy."""

    def test_filter_keeps_all_within_retention(self) -> None:
        """Test that all schemas within retention period are kept."""
        merger = SchemaMerger(retention_days=30)

        schemas = [
            SchemaVersion(
                schema={"form_name": "test"},
                timestamp=datetime.now() - timedelta(days=5),
                version_id="v1",
            ),
            SchemaVersion(
                schema={"form_name": "test"},
                timestamp=datetime.now() - timedelta(days=15),
                version_id="v2",
            ),
        ]

        active, retired = merger.filter_by_retention_policy(schemas)

        assert len(active) == 2
        assert len(retired) == 0

    def test_filter_retires_old_schemas(self) -> None:
        """Test that schemas beyond retention period are retired."""
        merger = SchemaMerger(retention_days=30, min_versions=2)

        schemas = [
            SchemaVersion(
                schema={"form_name": "test"},
                timestamp=datetime.now() - timedelta(days=5),
                version_id="v1",
            ),
            SchemaVersion(
                schema={"form_name": "test"},
                timestamp=datetime.now() - timedelta(days=15),
                version_id="v2",
            ),
            SchemaVersion(
                schema={"form_name": "test"},
                timestamp=datetime.now() - timedelta(days=45),  # Beyond retention
                version_id="v3",
            ),
        ]

        active, retired = merger.filter_by_retention_policy(schemas)

        assert len(active) == 2
        assert len(retired) == 1
        assert retired[0].version_id == "v3"

    def test_filter_honors_min_versions(self) -> None:
        """Test that minimum version count is honored even if all are old."""
        merger = SchemaMerger(retention_days=10, min_versions=3)

        schemas = [
            SchemaVersion(
                schema={"form_name": "test"},
                timestamp=datetime.now() - timedelta(days=20),
                version_id="v1",
            ),
            SchemaVersion(
                schema={"form_name": "test"},
                timestamp=datetime.now() - timedelta(days=25),
                version_id="v2",
            ),
            SchemaVersion(
                schema={"form_name": "test"},
                timestamp=datetime.now() - timedelta(days=30),
                version_id="v3",
            ),
        ]

        active, retired = merger.filter_by_retention_policy(schemas)

        assert len(active) == 3  # All kept due to min_versions
        assert len(retired) == 0

    def test_filter_enforces_max_versions(self) -> None:
        """Test that maximum version limit is enforced."""
        merger = SchemaMerger(retention_days=365, min_versions=3, max_versions=5)

        schemas = [
            SchemaVersion(
                schema={"form_name": "test"},
                timestamp=datetime.now() - timedelta(days=i),
                version_id=f"v{i}",
            )
            for i in range(10)  # 10 schemas
        ]

        active, retired = merger.filter_by_retention_policy(schemas)

        assert len(active) == 5  # Max 5
        assert len(retired) == 5

    def test_filter_with_empty_list(self) -> None:
        """Test filtering with empty schema list."""
        merger = SchemaMerger()

        active, retired = merger.filter_by_retention_policy([])

        assert len(active) == 0
        assert len(retired) == 0


class TestSchemaMergerMergeOperations:
    """Tests for schema merging operations."""

    def test_merge_raises_on_empty_list(self) -> None:
        """Test that merging empty list raises ValueError."""
        merger = SchemaMerger()

        with pytest.raises(ValueError, match="No schemas provided"):
            merger.merge_schemas([])

    def test_merge_single_schema(self) -> None:
        """Test merging single schema returns enriched schema."""
        merger = SchemaMerger()

        schema = {
            "form_name": "Test Form",
            "description": "Test",
            "sections": [
                {
                    "name": "Section1",
                    "description": "Test section",
                    "fields": [{"name": "field1", "type": "string"}],
                    "subsections": [],
                }
            ],
        }

        schemas = [
            SchemaVersion(
                schema=schema,
                timestamp=datetime.now(),
                version_id="v1",
            )
        ]

        result = merger.merge_schemas(schemas)

        assert result["form_name"] == "Test Form"
        assert "sections" in result
        assert "id" in result["sections"][0]  # Enriched with ID
        assert "id" in result["sections"][0]["fields"][0]  # Field enriched

    def test_merge_two_schemas_combines_fields(self) -> None:
        """Test merging two schemas combines fields from both."""
        merger = SchemaMerger()

        ts1 = "2025-01-01T00:00:00Z"
        ts2 = "2025-01-02T00:00:00Z"

        schema1 = {
            "form_name": {"timestamp": ts1, "value": "Form"},
            "description": {"timestamp": ts1, "value": "Test"},
            "page_identifier": {"timestamp": ts1, "value": "test-page"},
            "sections": [
                {
                    "name": {"timestamp": ts1, "value": "Section1"},
                    "description": {"timestamp": ts1, "value": "Test"},
                    "fields": [
                        {
                            "name": {"timestamp": ts1, "value": "field1"},
                            "type": {"timestamp": ts1, "value": "string"},
                            "description": {"timestamp": ts1, "value": "Field 1"},
                        }
                    ],
                    "subsections": [],
                }
            ],
        }

        schema2 = {
            "form_name": {"timestamp": ts2, "value": "Form"},
            "description": {"timestamp": ts2, "value": "Test"},
            "page_identifier": {"timestamp": ts2, "value": "test-page"},
            "sections": [
                {
                    "name": {"timestamp": ts2, "value": "Section1"},
                    "description": {"timestamp": ts2, "value": "Test"},
                    "fields": [
                        {
                            "name": {"timestamp": ts2, "value": "field2"},
                            "type": {"timestamp": ts2, "value": "number"},
                            "description": {"timestamp": ts2, "value": "Field 2"},
                        }
                    ],
                    "subsections": [],
                }
            ],
        }

        schemas = [
            SchemaVersion(schema=schema1, timestamp=datetime.now(), version_id="v1"),
            SchemaVersion(
                schema=schema2,
                timestamp=datetime.now() + timedelta(hours=1),
                version_id="v2",
            ),
        ]

        result = merger.merge_schemas(schemas)

        # Should have both fields - access .value for TimestampedValue fields
        section_fields = result["sections"][0]["fields"]
        field_names = [f["name"]["value"] for f in section_fields]
        assert "field1" in field_names
        assert "field2" in field_names

    def test_merge_updates_existing_fields(self) -> None:
        """Test that merging updates field properties."""
        merger = SchemaMerger()

        ts1 = "2025-01-01T00:00:00Z"
        ts2 = "2025-01-02T00:00:00Z"

        schema1 = {
            "form_name": {"timestamp": ts1, "value": "Form"},
            "description": {"timestamp": ts1, "value": "Test"},
            "page_identifier": {"timestamp": ts1, "value": "test-page"},
            "sections": [
                {
                    "name": {"timestamp": ts1, "value": "Section1"},
                    "description": {"timestamp": ts1, "value": "Test"},
                    "fields": [
                        {
                            "name": {"timestamp": ts1, "value": "email"},
                            "type": {"timestamp": ts1, "value": "email"},
                            "description": {"timestamp": ts1, "value": "User email"},
                            "required": {"timestamp": ts1, "value": False},
                            "label": {"timestamp": ts1, "value": "Email"},
                        }
                    ],
                    "subsections": [],
                }
            ],
        }

        schema2 = {
            "form_name": {"timestamp": ts2, "value": "Form"},
            "description": {"timestamp": ts2, "value": "Test"},
            "page_identifier": {"timestamp": ts2, "value": "test-page"},
            "sections": [
                {
                    "name": {"timestamp": ts2, "value": "Section1"},
                    "description": {"timestamp": ts2, "value": "Test"},
                    "fields": [
                        {
                            "name": {"timestamp": ts2, "value": "email"},
                            "type": {"timestamp": ts2, "value": "email"},
                            "description": {"timestamp": ts2, "value": "User email"},
                            "required": {"timestamp": ts2, "value": True},  # Changed
                            "label": {"timestamp": ts2, "value": "Email Address"},  # Changed
                        }
                    ],
                    "subsections": [],
                }
            ],
        }

        schemas = [
            SchemaVersion(
                schema=schema1,
                timestamp=datetime.now() - timedelta(hours=1),
                version_id="v1",
            ),
            SchemaVersion(schema=schema2, timestamp=datetime.now(), version_id="v2"),
        ]

        result = merger.merge_schemas(schemas)

        # Should use values from newer schema - access .value for TimestampedValue
        email_field = result["sections"][0]["fields"][0]
        assert email_field["required"]["value"] is True
        assert email_field["label"]["value"] == "Email Address"

    def test_merge_includes_metadata(self) -> None:
        """Test that merge metadata is included in result."""
        merger = SchemaMerger()

        ts1 = "2024-01-01T00:00:00Z"
        ts2 = "2024-01-15T00:00:00Z"

        schemas = [
            SchemaVersion(
                schema={
                    "form_name": {"timestamp": ts1, "value": "test"},
                    "description": {"timestamp": ts1, "value": "Test"},
                    "page_identifier": {"timestamp": ts1, "value": "test-page"},
                    "sections": [],
                },
                timestamp=datetime(2024, 1, 1),
                version_id="v1",
            ),
            SchemaVersion(
                schema={
                    "form_name": {"timestamp": ts2, "value": "test"},
                    "description": {"timestamp": ts2, "value": "Test"},
                    "page_identifier": {"timestamp": ts2, "value": "test-page"},
                    "sections": [],
                },
                timestamp=datetime(2024, 1, 15),
                version_id="v2",
            ),
        ]

        result = merger.merge_schemas(schemas, include_metadata=True)

        assert "_merge_metadata" in result
        metadata = result["_merge_metadata"]
        assert metadata["source_count"] == 2
        assert metadata["version_ids"] == ["v1", "v2"]
        assert metadata["retention_days"] == 30

    def test_merge_without_metadata(self) -> None:
        """Test that metadata can be excluded."""
        merger = SchemaMerger()

        schemas = [
            SchemaVersion(
                schema={"form_name": "test", "sections": []},
                timestamp=datetime.now(),
                version_id="v1",
            )
        ]

        result = merger.merge_schemas(schemas, include_metadata=False)

        assert "_merge_metadata" not in result

    def test_merge_respects_hierarchical_identity(self) -> None:
        """Test that fields in different sections remain separate."""
        merger = SchemaMerger()

        schema = {
            "form_name": "Form",
            "description": "Test",
            "sections": [
                {
                    "name": "Applicant",
                    "description": "Applicant info",
                    "fields": [{"name": "firstName", "type": "string"}],
                    "subsections": [],
                },
                {
                    "name": "Spouse",
                    "description": "Spouse info",
                    "fields": [{"name": "firstName", "type": "string"}],
                    "subsections": [],
                },
            ],
        }

        schemas = [
            SchemaVersion(schema=schema, timestamp=datetime.now(), version_id="v1")
        ]

        result = merger.merge_schemas(schemas)

        # Should have 2 sections, each with their own firstName field
        assert len(result["sections"]) == 2
        assert result["sections"][0]["fields"][0]["name"] == "firstName"
        assert result["sections"][1]["fields"][0]["name"] == "firstName"

        # IDs should be different
        id1 = result["sections"][0]["fields"][0]["id"]
        id2 = result["sections"][1]["fields"][0]["id"]
        assert id1 != id2


class TestSchemaMergerPydanticIntegration:
    """Tests for Pydantic model integration."""

    def test_merge_pydantic_models(self) -> None:
        """Test merging Pydantic FormSchema models."""
        merger = SchemaMerger()

        schema1 = FormSchema(
            page_identifier="test-form-page-1",
            form_name="Test Form",
            description="Test",
            sections=[
                FormSection(
                    name="Section1",
                    description="Test section",
                    fields=[
                        FormField(
                            name="field1",
                            type="string",
                            description="Field 1",
                            constraints=[],
                        )
                    ],
                    subsections=[],
                )
            ],
        )

        schema2 = FormSchema(
            page_identifier="test-form-page-1",
            form_name="Test Form",
            description="Test",
            sections=[
                FormSection(
                    name="Section1",
                    description="Test section",
                    fields=[
                        FormField(
                            name="field2",
                            type="number",
                            description="Field 2",
                            constraints=[],
                        )
                    ],
                    subsections=[],
                )
            ],
        )

        models = [
            (schema1, datetime.now(), "v1"),
            (schema2, datetime.now() + timedelta(hours=1), "v2"),
        ]

        result = merger.merge_pydantic_models(models)

        # Result should be valid FormSchema
        assert isinstance(result, FormSchema)
        assert result.form_name.value == "Test Form"
        assert len(result.sections) == 1

        # Should have both fields - access .value for TimestampedValue properties
        field_names = [f.name.value for f in result.sections[0].fields]
        assert "field1" in field_names
        assert "field2" in field_names


class TestNewerTimestampStrategy:
    """Tests for the NewerTimestampStrategy custom jsonmerge strategy."""

    def test_newer_timestamp_wins(self) -> None:
        """Test that the value with newer timestamp is kept."""
        merger = SchemaMerger(merge_config=SchemaMerger.MASTER_MERGE_CONFIG)

        ts_old = "2025-01-01T00:00:00Z"
        ts_new = "2025-01-15T00:00:00Z"

        schema1 = {
            "form_name": {"timestamp": ts_new, "value": "Newer Form Name"},
            "description": {"timestamp": ts_old, "value": "Old Description"},
            "page_identifier": {"timestamp": ts_old, "value": "page-1"},
            "sections": [],
        }

        schema2 = {
            "form_name": {"timestamp": ts_old, "value": "Older Form Name"},
            "description": {"timestamp": ts_new, "value": "Newer Description"},
            "page_identifier": {"timestamp": ts_new, "value": "page-1"},
            "sections": [],
        }

        # Merge in order: schema1 first, then schema2
        schemas = [
            SchemaVersion(
                schema=schema1,
                timestamp=datetime(2025, 1, 1),
                version_id="v1",
            ),
            SchemaVersion(
                schema=schema2,
                timestamp=datetime(2025, 1, 2),
                version_id="v2",
            ),
        ]

        result = merger.merge_schemas(schemas)

        # form_name: schema1 has newer timestamp -> keep "Newer Form Name"
        assert result["form_name"]["value"] == "Newer Form Name"
        assert result["form_name"]["timestamp"] == ts_new

        # description: schema2 has newer timestamp -> keep "Newer Description"
        assert result["description"]["value"] == "Newer Description"
        assert result["description"]["timestamp"] == ts_new

    def test_legacy_timestamp_always_loses(self) -> None:
        """Test that legacy timestamps (epoch) always lose to real timestamps."""
        merger = SchemaMerger(merge_config=SchemaMerger.MASTER_MERGE_CONFIG)

        ts_real = "2025-01-01T00:00:00Z"

        schema1 = {
            "form_name": {"timestamp": LEGACY_TIMESTAMP, "value": "Legacy Name"},
            "description": {"timestamp": ts_real, "value": "Real Description"},
            "page_identifier": {"timestamp": ts_real, "value": "page-1"},
            "sections": [],
        }

        schema2 = {
            "form_name": {"timestamp": ts_real, "value": "Real Name"},
            "description": {"timestamp": LEGACY_TIMESTAMP, "value": "Legacy Description"},
            "page_identifier": {"timestamp": ts_real, "value": "page-1"},
            "sections": [],
        }

        schemas = [
            SchemaVersion(schema=schema1, timestamp=datetime(2025, 1, 1), version_id="v1"),
            SchemaVersion(schema=schema2, timestamp=datetime(2025, 1, 2), version_id="v2"),
        ]

        result = merger.merge_schemas(schemas)

        # Real timestamp beats legacy
        assert result["form_name"]["value"] == "Real Name"
        assert result["description"]["value"] == "Real Description"

    def test_nested_field_timestamp_comparison(self) -> None:
        """Test timestamp comparison works for nested fields in sections.

        Note: Sections and fields are matched by hierarchical identity (section path + name + type).
        The section 'name' property itself is part of the identity, so we test timestamp
        comparison on description and label fields instead.
        """
        merger = SchemaMerger(merge_config=SchemaMerger.MASTER_MERGE_CONFIG)

        ts_old = "2025-01-01T00:00:00Z"
        ts_new = "2025-01-15T00:00:00Z"

        # Both schemas have the same section name (for ID matching) but different
        # timestamps on the description and field properties
        schema1 = {
            "form_name": {"timestamp": ts_old, "value": "Form"},
            "description": {"timestamp": ts_old, "value": "Test"},
            "page_identifier": {"timestamp": ts_old, "value": "page-1"},
            "sections": [
                {
                    "name": {"timestamp": ts_old, "value": "Section1"},
                    "description": {"timestamp": ts_new, "value": "Newer Section Desc"},
                    "fields": [
                        {
                            "name": {"timestamp": ts_old, "value": "email"},
                            "type": {"timestamp": ts_old, "value": "email"},
                            "description": {"timestamp": ts_new, "value": "Newer Field Desc"},
                            "label": {"timestamp": ts_old, "value": "Old Label"},
                        }
                    ],
                    "subsections": [],
                }
            ],
        }

        schema2 = {
            "form_name": {"timestamp": ts_old, "value": "Form"},
            "description": {"timestamp": ts_old, "value": "Test"},
            "page_identifier": {"timestamp": ts_old, "value": "page-1"},
            "sections": [
                {
                    # Same section name so IDs match and sections get merged
                    "name": {"timestamp": ts_old, "value": "Section1"},
                    "description": {"timestamp": ts_old, "value": "Older Section Desc"},
                    "fields": [
                        {
                            # Same field name+type so IDs match and fields get merged
                            "name": {"timestamp": ts_old, "value": "email"},
                            "type": {"timestamp": ts_old, "value": "email"},
                            "description": {"timestamp": ts_old, "value": "Older Field Desc"},
                            "label": {"timestamp": ts_new, "value": "New Label"},
                        }
                    ],
                    "subsections": [],
                }
            ],
        }

        schemas = [
            SchemaVersion(schema=schema1, timestamp=datetime(2025, 1, 1), version_id="v1"),
            SchemaVersion(schema=schema2, timestamp=datetime(2025, 1, 2), version_id="v2"),
        ]

        result = merger.merge_schemas(schemas)

        section = result["sections"][0]
        field = section["fields"][0]

        # Section description: schema1 has newer timestamp -> keep "Newer Section Desc"
        assert section["description"]["value"] == "Newer Section Desc"
        # Field description: schema1 has newer timestamp -> keep "Newer Field Desc"
        assert field["description"]["value"] == "Newer Field Desc"
        # Field label: schema2 has newer timestamp -> keep "New Label"
        assert field["label"]["value"] == "New Label"

    def test_equal_timestamps_keeps_base(self) -> None:
        """Test that equal timestamps keep the base value (first merged)."""
        merger = SchemaMerger(merge_config=SchemaMerger.MASTER_MERGE_CONFIG)

        ts = "2025-01-01T00:00:00Z"

        schema1 = {
            "form_name": {"timestamp": ts, "value": "First Form"},
            "description": {"timestamp": ts, "value": "First Desc"},
            "page_identifier": {"timestamp": ts, "value": "page-1"},
            "sections": [],
        }

        schema2 = {
            "form_name": {"timestamp": ts, "value": "Second Form"},
            "description": {"timestamp": ts, "value": "Second Desc"},
            "page_identifier": {"timestamp": ts, "value": "page-1"},
            "sections": [],
        }

        schemas = [
            SchemaVersion(schema=schema1, timestamp=datetime(2025, 1, 1), version_id="v1"),
            SchemaVersion(schema=schema2, timestamp=datetime(2025, 1, 2), version_id="v2"),
        ]

        result = merger.merge_schemas(schemas)

        # Equal timestamps -> base (first) wins
        assert result["form_name"]["value"] == "First Form"
        assert result["description"]["value"] == "First Desc"

    def test_session_config_uses_overwrite(self) -> None:
        """Test that SESSION_MERGE_CONFIG uses overwrite (sequence order matters)."""
        merger = SchemaMerger(merge_config=SchemaMerger.SESSION_MERGE_CONFIG)

        ts_old = "2025-01-15T00:00:00Z"  # Newer timestamp but...
        ts_new = "2025-01-01T00:00:00Z"  # ...this appears later in merge sequence

        schema1 = {
            "form_name": {"timestamp": ts_old, "value": "First in Sequence"},
            "description": {"timestamp": ts_old, "value": "First Desc"},
            "page_identifier": {"timestamp": ts_old, "value": "page-1"},
            "sections": [],
        }

        schema2 = {
            "form_name": {"timestamp": ts_new, "value": "Second in Sequence"},
            "description": {"timestamp": ts_new, "value": "Second Desc"},
            "page_identifier": {"timestamp": ts_new, "value": "page-1"},
            "sections": [],
        }

        # schema1 merged first, then schema2 (which has OLDER timestamp)
        schemas = [
            SchemaVersion(schema=schema1, timestamp=datetime(2025, 1, 1), version_id="v1"),
            SchemaVersion(schema=schema2, timestamp=datetime(2025, 1, 2), version_id="v2"),
        ]

        result = merger.merge_schemas(schemas)

        # SESSION config uses overwrite: later in sequence wins regardless of timestamp
        assert result["form_name"]["value"] == "Second in Sequence"
        assert result["description"]["value"] == "Second Desc"


class TestTimestampedListMergeStrategy:
    """Tests for the TimestampedListMergeStrategy custom jsonmerge strategy."""

    def test_merges_by_value_keeps_newer_timestamp(self) -> None:
        """Test that lists are merged by value and newer timestamps are kept."""
        merger = SchemaMerger(merge_config=SchemaMerger.MASTER_MERGE_CONFIG)

        ts_old = "2025-01-01T00:00:00Z"
        ts_new = "2025-01-15T00:00:00Z"

        schema1 = {
            "form_name": {"timestamp": ts_old, "value": "Form"},
            "description": {"timestamp": ts_old, "value": "Test"},
            "page_identifier": {"timestamp": ts_old, "value": "page-1"},
            "page_identification": {
                "url": {"timestamp": ts_old, "value": "https://example.com"},
                "page_headings": [
                    {"timestamp": ts_old, "value": "Header A"},
                    {"timestamp": ts_old, "value": "Header B"},
                ],
                "form_headings": [],
                "visual_sections": [],
                "navigation_buttons": [],
            },
            "sections": [],
        }

        schema2 = {
            "form_name": {"timestamp": ts_old, "value": "Form"},
            "description": {"timestamp": ts_old, "value": "Test"},
            "page_identifier": {"timestamp": ts_old, "value": "page-1"},
            "page_identification": {
                "url": {"timestamp": ts_old, "value": "https://example.com"},
                "page_headings": [
                    {"timestamp": ts_new, "value": "Header A"},  # Same value, newer timestamp
                    {"timestamp": ts_new, "value": "Header C"},  # New value
                ],
                "form_headings": [],
                "visual_sections": [],
                "navigation_buttons": [],
            },
            "sections": [],
        }

        schemas = [
            SchemaVersion(schema=schema1, timestamp=datetime(2025, 1, 1), version_id="v1"),
            SchemaVersion(schema=schema2, timestamp=datetime(2025, 1, 2), version_id="v2"),
        ]

        result = merger.merge_schemas(schemas)
        page_headings = result["page_identification"]["page_headings"]

        # Should have 3 entries: A (updated timestamp), B (unchanged), C (added)
        assert len(page_headings) == 3

        values = {h["value"] for h in page_headings}
        assert values == {"Header A", "Header B", "Header C"}

        # Header A should have the newer timestamp
        header_a = next(h for h in page_headings if h["value"] == "Header A")
        assert header_a["timestamp"] == ts_new

        # Header B should keep old timestamp
        header_b = next(h for h in page_headings if h["value"] == "Header B")
        assert header_b["timestamp"] == ts_old

    def test_legacy_timestamp_always_loses(self) -> None:
        """Test that legacy timestamps always lose to real timestamps."""
        from src.models.timestamped import LEGACY_TIMESTAMP

        merger = SchemaMerger(merge_config=SchemaMerger.MASTER_MERGE_CONFIG)

        ts_new = "2025-01-15T00:00:00Z"

        schema1 = {
            "form_name": {"timestamp": ts_new, "value": "Form"},
            "description": {"timestamp": ts_new, "value": "Test"},
            "page_identifier": {"timestamp": ts_new, "value": "page-1"},
            "page_identification": {
                "page_headings": [
                    {"timestamp": LEGACY_TIMESTAMP, "value": "Legacy Header"},
                ],
                "form_headings": [],
                "visual_sections": [],
                "navigation_buttons": [],
            },
            "sections": [],
        }

        schema2 = {
            "form_name": {"timestamp": ts_new, "value": "Form"},
            "description": {"timestamp": ts_new, "value": "Test"},
            "page_identifier": {"timestamp": ts_new, "value": "page-1"},
            "page_identification": {
                "page_headings": [
                    {"timestamp": ts_new, "value": "Legacy Header"},  # Same value, real timestamp
                ],
                "form_headings": [],
                "visual_sections": [],
                "navigation_buttons": [],
            },
            "sections": [],
        }

        schemas = [
            SchemaVersion(schema=schema1, timestamp=datetime(2025, 1, 1), version_id="v1"),
            SchemaVersion(schema=schema2, timestamp=datetime(2025, 1, 2), version_id="v2"),
        ]

        result = merger.merge_schemas(schemas)
        page_headings = result["page_identification"]["page_headings"]

        # Should have 1 entry with the newer (non-legacy) timestamp
        assert len(page_headings) == 1
        assert page_headings[0]["value"] == "Legacy Header"
        assert page_headings[0]["timestamp"] == ts_new

    def test_session_config_deduplicates_by_value(self) -> None:
        """Test that SESSION_MERGE_CONFIG also deduplicates lists by value."""
        merger = SchemaMerger(merge_config=SchemaMerger.SESSION_MERGE_CONFIG)

        ts1 = "2025-01-01T00:00:00Z"
        ts2 = "2025-01-15T00:00:00Z"

        schema1 = {
            "form_name": {"timestamp": ts1, "value": "Form"},
            "description": {"timestamp": ts1, "value": "Test"},
            "page_identifier": {"timestamp": ts1, "value": "page-1"},
            "page_identification": {
                "navigation_buttons": [
                    {"timestamp": ts1, "value": "Next"},
                    {"timestamp": ts1, "value": "Save"},
                ],
                "page_headings": [],
                "form_headings": [],
                "visual_sections": [],
            },
            "sections": [],
        }

        schema2 = {
            "form_name": {"timestamp": ts2, "value": "Form"},
            "description": {"timestamp": ts2, "value": "Test"},
            "page_identifier": {"timestamp": ts2, "value": "page-1"},
            "page_identification": {
                "navigation_buttons": [
                    {"timestamp": ts2, "value": "Next"},  # Duplicate
                    {"timestamp": ts2, "value": "Submit"},  # New
                ],
                "page_headings": [],
                "form_headings": [],
                "visual_sections": [],
            },
            "sections": [],
        }

        schemas = [
            SchemaVersion(schema=schema1, timestamp=datetime(2025, 1, 1), version_id="v1"),
            SchemaVersion(schema=schema2, timestamp=datetime(2025, 1, 2), version_id="v2"),
        ]

        result = merger.merge_schemas(schemas)
        nav_buttons = result["page_identification"]["navigation_buttons"]

        # Should have 3 unique buttons
        assert len(nav_buttons) == 3
        values = {b["value"] for b in nav_buttons}
        assert values == {"Next", "Save", "Submit"}
