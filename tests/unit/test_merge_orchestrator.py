"""Unit tests for merge orchestration service.

Tests complete workflow including:
- Schema loading from sessions
- Page grouping and merging
- File output and metadata generation
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.models.page_identification import PageIdentification
from src.models.schema import FormField, FormSchema, FormSection
from src.services.merging.merge_orchestrator import MergeOrchestrator


class TestMergeOrchestrator:
    """Tests for merge orchestrator."""

    @pytest.fixture
    def temp_session_dir(self, tmp_path: Path) -> Path:
        """Create temporary session directory with test schemas."""
        # Create session directories
        session1 = tmp_path / "session1"
        session2 = tmp_path / "session2"
        session1.mkdir()
        session2.mkdir()

        # Create test schemas
        schema1 = FormSchema(
            page_identifier="page-1",
            form_name="Application",
            description="Test form",
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
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application Form"],
                form_headings=["Personal Details"],  # Same form_headings for matching
            ),
        )

        schema2 = FormSchema(
            page_identifier="page-2",
            form_name="Application",
            description="Test form",
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
            page_identification=PageIdentification(
                url="https://example.gov/form",
                timestamp=None,
                page_headings=["Application Form"],
                form_headings=["Personal Details"],  # Same form_headings for matching
            ),
        )

        # Save schemas to files
        with open(session1 / "form1_schema.json", "w") as f:
            json.dump(schema1.model_dump(mode="json"), f)

        with open(session2 / "form2_schema.json", "w") as f:
            json.dump(schema2.model_dump(mode="json"), f)

        return tmp_path

    def test_orchestrator_initialization(self, tmp_path: Path) -> None:
        """Test orchestrator initializes correctly."""
        orchestrator = MergeOrchestrator(
            base_path=tmp_path,
            output_subdir="merged",
            form_similarity_threshold=0.8,
            page_similarity_threshold=0.5,
            retention_days=30,
        )

        assert orchestrator.base_path == tmp_path
        assert orchestrator.output_dir == tmp_path / "merged"
        assert orchestrator.output_dir.exists()
        assert orchestrator.page_matcher.form_similarity_threshold == 0.8
        assert orchestrator.page_matcher.page_similarity_threshold == 0.5
        assert orchestrator.schema_merger.retention_days == 30

    def test_load_schemas_from_sessions(self, temp_session_dir: Path) -> None:
        """Test loading schemas from session directories."""
        orchestrator = MergeOrchestrator(base_path=temp_session_dir)

        schemas = orchestrator.load_schemas_from_sessions()

        assert len(schemas) == 2
        # Verify each tuple has (schema, timestamp, version_id)
        for schema, timestamp, version_id in schemas:
            assert isinstance(schema, FormSchema)
            assert isinstance(timestamp, datetime)
            assert isinstance(version_id, str)
            assert "_schema" in version_id

    def test_load_schemas_from_specific_sessions(self, temp_session_dir: Path) -> None:
        """Test loading schemas from specific session directories."""
        orchestrator = MergeOrchestrator(base_path=temp_session_dir)

        session1 = temp_session_dir / "session1"
        schemas = orchestrator.load_schemas_from_sessions([session1])

        assert len(schemas) == 1
        schema, timestamp, version_id = schemas[0]
        assert "form1_schema" in version_id

    def test_group_and_merge_schemas(self, temp_session_dir: Path) -> None:
        """Test grouping and merging schemas by page."""
        orchestrator = MergeOrchestrator(
            base_path=temp_session_dir,
            form_similarity_threshold=0.5,
            page_similarity_threshold=0.5,
        )

        schemas = orchestrator.load_schemas_from_sessions()
        merged = orchestrator.group_and_merge_schemas(schemas)

        # Should merge into single group (same URL and headings)
        assert len(merged) == 1
        page_id = list(merged.keys())[0]
        merged_schema = merged[page_id]

        # Should have both fields from both schemas - access .value for TimestampedValue
        field_names = [f.name.value for f in merged_schema.sections[0].fields]
        assert "field1" in field_names
        assert "field2" in field_names

    def test_group_and_merge_empty_schemas(self, tmp_path: Path) -> None:
        """Test grouping and merging with no schemas."""
        orchestrator = MergeOrchestrator(base_path=tmp_path)

        merged = orchestrator.group_and_merge_schemas([])

        assert merged == {}

    def test_save_merged_schemas(self, temp_session_dir: Path) -> None:
        """Test saving merged schemas to files."""
        orchestrator = MergeOrchestrator(
            base_path=temp_session_dir,
            form_similarity_threshold=0.5,
            page_similarity_threshold=0.5,
        )

        schemas = orchestrator.load_schemas_from_sessions()
        merged = orchestrator.group_and_merge_schemas(schemas)

        metadata = {"test": "metadata"}
        saved_files = orchestrator.save_merged_schemas(merged, metadata)

        assert len(saved_files) == 1
        page_id = list(saved_files.keys())[0]
        file_path = saved_files[page_id]

        # Verify file exists and has correct content
        assert file_path.exists()
        assert file_path.name == f"{page_id}_merged.json"

        with open(file_path) as f:
            saved_data = json.load(f)

        assert saved_data["_merge_metadata"] == metadata
        # form_name is now a TimestampedValue - access the value
        form_name_data = saved_data["form_name"]
        form_name = form_name_data["value"] if isinstance(form_name_data, dict) else form_name_data
        assert form_name == "Application"

    def test_generate_merge_metadata(self, temp_session_dir: Path) -> None:
        """Test metadata generation."""
        orchestrator = MergeOrchestrator(
            base_path=temp_session_dir,
            form_similarity_threshold=0.5,
            page_similarity_threshold=0.5,
            retention_days=30,
        )

        schemas = orchestrator.load_schemas_from_sessions()
        merged = orchestrator.group_and_merge_schemas(schemas)

        metadata = orchestrator.generate_merge_metadata(schemas, merged)

        assert metadata["source_count"] == 2
        assert metadata["page_groups_count"] == 1
        assert metadata["retention_days"] == 30
        assert metadata["form_similarity_threshold"] == 0.5
        assert metadata["page_similarity_threshold"] == 0.5
        assert "merge_timestamp" in metadata
        assert str(temp_session_dir) in metadata["base_path"]

    def test_merge_all_sessions_complete_workflow(
        self, temp_session_dir: Path
    ) -> None:
        """Test complete merge workflow."""
        orchestrator = MergeOrchestrator(
            base_path=temp_session_dir,
            form_similarity_threshold=0.5,
            page_similarity_threshold=0.5,
        )

        results = orchestrator.merge_all_sessions()

        # Verify results structure
        assert "merged_schemas" in results
        assert "saved_files" in results
        assert "metadata" in results
        assert "statistics" in results

        # Verify merged schemas
        merged_schemas = results["merged_schemas"]
        assert len(merged_schemas) == 1

        # Verify saved files
        saved_files = results["saved_files"]
        assert len(saved_files) == 1
        for file_path in saved_files.values():
            assert file_path.exists()

        # Verify metadata
        metadata = results["metadata"]
        assert metadata["source_count"] == 2
        assert metadata["page_groups_count"] == 1

        # Verify statistics
        stats = results["statistics"]
        assert stats["source_count"] == 2
        assert stats["page_groups_count"] == 1

    def test_merge_all_sessions_without_metadata(
        self, temp_session_dir: Path
    ) -> None:
        """Test merge workflow without metadata."""
        orchestrator = MergeOrchestrator(base_path=temp_session_dir)

        results = orchestrator.merge_all_sessions(include_metadata=False)

        assert results["metadata"] is None

        # Verify saved files don't have metadata
        saved_files = results["saved_files"]
        for file_path in saved_files.values():
            with open(file_path) as f:
                data = json.load(f)
            assert "_merge_metadata" not in data

    def test_merge_all_sessions_empty_directory(self, tmp_path: Path) -> None:
        """Test merge workflow with no sessions."""
        orchestrator = MergeOrchestrator(base_path=tmp_path)

        results = orchestrator.merge_all_sessions()

        assert results["merged_schemas"] == {}
        assert results["saved_files"] == {}
        assert results["metadata"] == {}
        assert results["statistics"]["source_count"] == 0
        assert results["statistics"]["page_groups_count"] == 0

    def test_output_directory_creation(self, tmp_path: Path) -> None:
        """Test output directory is created if it doesn't exist."""
        output_subdir = "custom_merged"
        orchestrator = MergeOrchestrator(
            base_path=tmp_path, output_subdir=output_subdir
        )

        assert orchestrator.output_dir == tmp_path / output_subdir
        assert orchestrator.output_dir.exists()

    def test_multiple_page_groups(self, tmp_path: Path) -> None:
        """Test merging with multiple distinct page groups."""
        # Create two sessions with different pages
        session1 = tmp_path / "session1"
        session2 = tmp_path / "session2"
        session1.mkdir()
        session2.mkdir()

        # Schema 1 - Application page
        schema1 = FormSchema(
            page_identifier="page-1",
            form_name="Application",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/application",
                timestamp=None,
                page_headings=["Application"],
            ),
        )

        # Schema 2 - Contact page (different)
        schema2 = FormSchema(
            page_identifier="page-2",
            form_name="Contact",
            description="Test",
            sections=[],
            page_identification=PageIdentification(
                url="https://example.gov/contact",
                timestamp=None,
                page_headings=["Contact"],
            ),
        )

        with open(session1 / "app_schema.json", "w") as f:
            json.dump(schema1.model_dump(mode="json"), f)

        with open(session2 / "contact_schema.json", "w") as f:
            json.dump(schema2.model_dump(mode="json"), f)

        orchestrator = MergeOrchestrator(base_path=tmp_path)
        results = orchestrator.merge_all_sessions()

        # Should have 2 separate page groups
        assert len(results["merged_schemas"]) == 2
        assert results["statistics"]["page_groups_count"] == 2
