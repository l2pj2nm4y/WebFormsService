"""Unit tests for schema merging service.

Tests hierarchical identity computation, temporal retention policies,
and merge operations for FormSchema objects.
"""

from datetime import datetime, timedelta

import pytest

from src.models.schema import FormField, FormSchema, FormSection
from src.services.merging.schema_merger import (
    HierarchicalIdentityComputer,
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

        schema1 = {
            "form_name": "Form",
            "description": "Test",
            "sections": [
                {
                    "name": "Section1",
                    "description": "Test",
                    "fields": [{"name": "field1", "type": "string"}],
                    "subsections": [],
                }
            ],
        }

        schema2 = {
            "form_name": "Form",
            "description": "Test",
            "sections": [
                {
                    "name": "Section1",
                    "description": "Test",
                    "fields": [{"name": "field2", "type": "number"}],
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

        # Should have both fields
        section_fields = result["sections"][0]["fields"]
        field_names = [f["name"] for f in section_fields]
        assert "field1" in field_names
        assert "field2" in field_names

    def test_merge_updates_existing_fields(self) -> None:
        """Test that merging updates field properties."""
        merger = SchemaMerger()

        schema1 = {
            "form_name": "Form",
            "description": "Test",
            "sections": [
                {
                    "name": "Section1",
                    "description": "Test",
                    "fields": [
                        {
                            "name": "email",
                            "type": "email",
                            "required": False,
                            "label": "Email",
                        }
                    ],
                    "subsections": [],
                }
            ],
        }

        schema2 = {
            "form_name": "Form",
            "description": "Test",
            "sections": [
                {
                    "name": "Section1",
                    "description": "Test",
                    "fields": [
                        {
                            "name": "email",
                            "type": "email",
                            "required": True,  # Changed
                            "label": "Email Address",  # Changed
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

        # Should use values from newer schema
        email_field = result["sections"][0]["fields"][0]
        assert email_field["required"] is True
        assert email_field["label"] == "Email Address"

    def test_merge_includes_metadata(self) -> None:
        """Test that merge metadata is included in result."""
        merger = SchemaMerger()

        schemas = [
            SchemaVersion(
                schema={"form_name": "test", "sections": []},
                timestamp=datetime(2024, 1, 1),
                version_id="v1",
            ),
            SchemaVersion(
                schema={"form_name": "test", "sections": []},
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
        assert result.form_name == "Test Form"
        assert len(result.sections) == 1

        # Should have both fields
        field_names = [f.name for f in result.sections[0].fields]
        assert "field1" in field_names
        assert "field2" in field_names
