"""Orchestration service for schema merging across sessions.

Coordinates:
1. Page matching - Identify duplicate pages across sessions
2. Schema merging - Merge schemas for matching pages
3. Storage integration - Save merged results to subfolder
4. Metadata generation - Track merge provenance and statistics
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.schema import FormSchema
from src.services.merging.page_matcher import PageMatcher
from src.services.merging.schema_merger import SchemaMerger, SchemaVersion


class MergeOrchestrator:
    """Orchestrates end-to-end schema merging workflow.

    Workflow:
    1. Load schemas from session directories
    2. Group schemas by matched pages
    3. Merge schemas within each page group
    4. Save merged schemas to output directory
    5. Generate merge metadata and statistics

    Example:
        orchestrator = MergeOrchestrator(
            base_path=Path("data/sessions"),
            output_subdir="merged"
        )
        results = orchestrator.merge_all_sessions()
    """

    def __init__(
        self,
        base_path: Path | str,
        output_subdir: str = "merged",
        form_similarity_threshold: float = 0.8,
        page_similarity_threshold: float = 0.5,
        retention_days: int = 30,
        debug_dir: Path | str | None = None,
    ):
        """Initialize merge orchestrator.

        Args:
            base_path: Base directory containing session subdirectories
            output_subdir: Subdirectory name for merged output (created under base_path)
            form_similarity_threshold: Minimum form similarity for same-form detection
            page_similarity_threshold: Minimum page similarity for same-page detection
            retention_days: Days to retain schema versions
            debug_dir: Directory to write page matching debug files. If None, no debug output.
        """
        self.base_path = Path(base_path)
        self.output_dir = self.base_path / output_subdir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.page_matcher = PageMatcher(
            form_similarity_threshold=form_similarity_threshold,
            page_similarity_threshold=page_similarity_threshold,
            debug_dir=debug_dir,
        )
        self.schema_merger = SchemaMerger(retention_days=retention_days)

    def load_schemas_from_sessions(
        self, session_dirs: list[Path] | None = None
    ) -> list[tuple[FormSchema, datetime, str]]:
        """Load all schemas from session directories.

        Args:
            session_dirs: Specific session directories to load from.
                         If None, loads from all subdirectories under base_path.

        Returns:
            List of (schema, timestamp, version_id) tuples
        """
        if session_dirs is None:
            # Find all session directories (exclude output_subdir)
            session_dirs = [
                d
                for d in self.base_path.iterdir()
                if d.is_dir() and d.name != self.output_dir.name
            ]

        schemas: list[tuple[FormSchema, datetime, str]] = []

        for session_dir in session_dirs:
            # Look for schema files in session directory
            schema_files = list(session_dir.glob("*_schema.json"))

            for schema_file in schema_files:
                try:
                    # Load schema using Pydantic
                    import json

                    with open(schema_file) as f:
                        schema_data = json.load(f)

                    schema = FormSchema.model_validate(schema_data)

                    # Extract timestamp from file metadata or schema
                    timestamp = datetime.fromtimestamp(schema_file.stat().st_mtime)

                    # Use file name as version ID
                    version_id = schema_file.stem

                    schemas.append((schema, timestamp, version_id))

                except Exception as e:
                    # Log error but continue processing
                    print(f"Error loading schema from {schema_file}: {e}")
                    continue

        return schemas

    def group_and_merge_schemas(
        self, schemas: list[tuple[FormSchema, datetime, str]]
    ) -> dict[str, FormSchema]:
        """Group schemas by page and merge within groups.

        Args:
            schemas: List of (schema, timestamp, version_id) tuples

        Returns:
            Dictionary mapping page_identifier to merged schema
        """
        if not schemas:
            return {}

        # Extract FormSchema objects for grouping
        schema_objects = [s[0] for s in schemas]

        # Group by page similarity
        page_groups = self.page_matcher.group_schemas_by_page(schema_objects)

        # Merge within each group
        merged_schemas: dict[str, FormSchema] = {}

        for page_id, group_schemas in page_groups.items():
            # Find matching schema versions for this group
            group_versions = [
                (schema, timestamp, version_id)
                for schema, timestamp, version_id in schemas
                if schema in group_schemas
            ]

            # Merge using SchemaMerger
            merged_schema = self.schema_merger.merge_pydantic_models(group_versions)

            merged_schemas[page_id] = merged_schema

        return merged_schemas

    def save_merged_schemas(
        self, merged_schemas: dict[str, FormSchema], metadata: dict[str, Any] | None = None
    ) -> dict[str, Path]:
        """Save merged schemas to output directory.

        Args:
            merged_schemas: Dictionary mapping page_identifier to merged schema
            metadata: Optional merge metadata to include

        Returns:
            Dictionary mapping page_identifier to saved file path
        """
        import json

        saved_files: dict[str, Path] = {}

        for page_id, schema in merged_schemas.items():
            # Create filename from page_id
            filename = f"{page_id}_merged.json"
            output_path = self.output_dir / filename

            # Convert schema to dict
            schema_dict = schema.model_dump(mode="json", exclude_none=True)

            # Add metadata if provided
            if metadata:
                schema_dict["_merge_metadata"] = metadata

            # Save to file
            with open(output_path, "w") as f:
                json.dump(schema_dict, f, indent=2)

            saved_files[page_id] = output_path

        return saved_files

    def generate_merge_metadata(
        self,
        schemas: list[tuple[FormSchema, datetime, str]],
        merged_schemas: dict[str, FormSchema],
    ) -> dict[str, Any]:
        """Generate metadata about the merge operation.

        Args:
            schemas: Original schemas that were merged
            merged_schemas: Result of merging

        Returns:
            Metadata dictionary with merge statistics
        """
        return {
            "merge_timestamp": datetime.now().isoformat(),
            "source_count": len(schemas),
            "page_groups_count": len(merged_schemas),
            "retention_days": self.schema_merger.retention_days,
            "form_similarity_threshold": self.page_matcher.form_similarity_threshold,
            "page_similarity_threshold": self.page_matcher.page_similarity_threshold,
            "base_path": str(self.base_path),
            "output_dir": str(self.output_dir),
        }

    def merge_all_sessions(
        self, session_dirs: list[Path] | None = None, include_metadata: bool = True
    ) -> dict[str, Any]:
        """Execute complete merge workflow for all sessions.

        Args:
            session_dirs: Specific session directories to merge.
                         If None, merges all sessions under base_path.
            include_metadata: Whether to include merge metadata in output

        Returns:
            Dictionary with merge results and statistics:
            {
                "merged_schemas": {page_id: schema},
                "saved_files": {page_id: file_path},
                "metadata": {...},
                "statistics": {...}
            }
        """
        # Step 1: Load schemas from sessions
        schemas = self.load_schemas_from_sessions(session_dirs)

        if not schemas:
            return {
                "merged_schemas": {},
                "saved_files": {},
                "metadata": {},
                "statistics": {"source_count": 0, "page_groups_count": 0},
            }

        # Step 2: Group and merge schemas
        merged_schemas = self.group_and_merge_schemas(schemas)

        # Step 3: Generate metadata
        metadata = (
            self.generate_merge_metadata(schemas, merged_schemas)
            if include_metadata
            else None
        )

        # Step 4: Save merged schemas
        saved_files = self.save_merged_schemas(merged_schemas, metadata)

        # Step 5: Compile results
        return {
            "merged_schemas": merged_schemas,
            "saved_files": saved_files,
            "metadata": metadata,
            "statistics": {
                "source_count": len(schemas),
                "page_groups_count": len(merged_schemas),
                "output_dir": str(self.output_dir),
            },
        }
