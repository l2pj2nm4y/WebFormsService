"""Integration tests for session-level schema merging pipeline stage."""

import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from src.models.page_identification import PageIdentification
from src.models.schema import FormField, FormSchema, FormSection
from src.services.pipeline.session_merger import merge_session_schemas


class TestSessionMergerIntegration:
    """Integration tests for session merger pipeline stage."""

    @pytest.fixture
    def test_session_with_schemas(
        self, test_storage_dir: Path
    ) -> tuple[UUID, Path]:
        """Create a test session with multiple schemas for the same page."""
        session_id = uuid4()
        session_dir = test_storage_dir / "sessions" / str(session_id)
        session_dir.mkdir(parents=True)

        # Create test schemas for the same page
        schema1 = FormSchema(
            page_identifier="application-form",
            form_name="Application",
            description="Test application form",
            sections=[
                FormSection(
                    name="Personal",
                    description="Personal info",
                    fields=[
                        FormField(
                            name="first_name",
                            type="string",
                            description="First name",
                            constraints=[],
                        )
                    ],
                    subsections=[],
                )
            ],
            page_identification=PageIdentification(
                url="https://example.gov/application",
                timestamp=None,
                page_headings=["Application Form"],
            ),
        )

        schema2 = FormSchema(
            page_identifier="application-form-2",
            form_name="Application",
            description="Test application form",
            sections=[
                FormSection(
                    name="Personal",
                    description="Personal info",
                    fields=[
                        FormField(
                            name="last_name",
                            type="string",
                            description="Last name",
                            constraints=[],
                        )
                    ],
                    subsections=[],
                )
            ],
            page_identification=PageIdentification(
                url="https://example.gov/application",
                timestamp=None,
                page_headings=["Application Form"],
            ),
        )

        # Save schemas to session directory
        with open(session_dir / "form1_schema.json", "w") as f:
            json.dump(schema1.model_dump(mode="json"), f, indent=2)

        with open(session_dir / "form2_schema.json", "w") as f:
            json.dump(schema2.model_dump(mode="json"), f, indent=2)

        return session_id, test_storage_dir

    @pytest.mark.asyncio
    async def test_merge_session_schemas_creates_merged_directory(
        self, test_session_with_schemas: tuple[UUID, Path]
    ) -> None:
        """Test that merge creates merged/ subdirectory."""
        session_id, base_path = test_session_with_schemas

        # Run merge
        result = await merge_session_schemas(
            session_id=session_id, similarity_threshold=0.5
        )

        # Verify result
        assert result.success is True
        assert result.operation == "session_merge"

        # Verify merged directory exists
        merged_dir = base_path / "sessions" / str(session_id) / "merged"
        assert merged_dir.exists()
        assert merged_dir.is_dir()

    @pytest.mark.asyncio
    async def test_merge_session_schemas_merges_matching_pages(
        self, test_session_with_schemas: tuple[UUID, Path]
    ) -> None:
        """Test that matching pages are merged into single schema."""
        session_id, base_path = test_session_with_schemas

        # Run merge
        result = await merge_session_schemas(
            session_id=session_id, similarity_threshold=0.5
        )

        # Verify result metadata
        assert result.success is True
        assert result.metadata is not None
        assert result.metadata["source_schema_count"] == 2
        assert result.metadata["page_groups_count"] == 1  # Should merge into 1 group
        assert result.metadata["merged_schemas_saved"] == 1

        # Verify merged file exists
        merged_dir = base_path / "sessions" / str(session_id) / "merged"
        merged_files = list(merged_dir.glob("*_merged.json"))
        assert len(merged_files) == 1

        # Load and verify merged schema
        with open(merged_files[0]) as f:
            merged_data = json.load(f)

        # Should have both fields from both schemas
        assert merged_data["form_name"] == "Application"
        assert len(merged_data["sections"]) == 1
        assert len(merged_data["sections"][0]["fields"]) == 2

        field_names = {f["name"] for f in merged_data["sections"][0]["fields"]}
        assert "first_name" in field_names
        assert "last_name" in field_names

    @pytest.mark.asyncio
    async def test_merge_session_schemas_no_schemas_returns_success(
        self, test_storage_dir: Path
    ) -> None:
        """Test that empty session returns success with no schemas."""
        session_id = uuid4()
        session_dir = test_storage_dir / "sessions" / str(session_id)
        session_dir.mkdir(parents=True)

        # Run merge on empty session
        result = await merge_session_schemas(session_id=session_id)

        # Verify result
        assert result.success is True
        assert result.metadata is not None
        assert result.metadata["schema_count"] == 0
        assert result.metadata["message"] == "No schemas to merge"

    @pytest.mark.asyncio
    async def test_merge_session_schemas_includes_duration(
        self, test_session_with_schemas: tuple[UUID, Path]
    ) -> None:
        """Test that result includes duration_ms."""
        session_id, _ = test_session_with_schemas

        # Run merge
        result = await merge_session_schemas(session_id=session_id)

        # Verify duration
        assert result.duration_ms > 0
        assert isinstance(result.duration_ms, float)
