"""Session-level schema merging pipeline stage.

Merges schemas within a session after quartet processing completes.
This stage groups schemas by page similarity and creates merged schemas
that represent the consolidated form structure.
"""

import time
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from src.lib.logging import get_logger
from src.models.result import ProcessingResult
from src.models.schema import FormSchema
from src.services.merging import MergeOrchestrator
from src.services.storage import get_storage

logger = get_logger(__name__)


async def merge_session_schemas(
    session_id: UUID,
    form_similarity_threshold: float = 0.8,
    page_similarity_threshold: float = 0.5,
    retention_days: int = 30,
    debug_dir: Path | str | None = None,
) -> ProcessingResult:
    """Merge all schemas within a session by two-stage page similarity.

    Two-stage matching:
    1. Form Similarity: Are pages from the same multi-page form?
       (URL, page_headings, structure, navigation)
    2. Page Similarity: Are pages the same within that form?
       (form_headings - section titles unique to each page)

    Pipeline stages:
    1. Discover session schemas
    2. Group schemas by two-stage page matching
    3. Merge within groups
    4. Save merged schemas to merged/ subfolder
    5. Return processing result

    Args:
        session_id: Session UUID
        form_similarity_threshold: Threshold for same-form detection (0.0-1.0)
        page_similarity_threshold: Threshold for same-page detection (0.0-1.0)
        retention_days: Days to retain schema versions
        debug_dir: Directory to write page matching debug files. If None, no debug output.

    Returns:
        ProcessingResult: Result with success status and merge statistics
    """
    start_time = time.time()

    logger.info(
        "session_merge_start",
        session_id=str(session_id),
        form_similarity_threshold=form_similarity_threshold,
        page_similarity_threshold=page_similarity_threshold,
        retention_days=retention_days,
    )

    try:
        # Get storage instance
        storage = get_storage()
        session_dir = Path(f"sessions/{session_id}")

        # Stage 1: Discover schema files in session
        schema_files = await storage.list_files(str(session_dir))

        logger.debug(
            "session_merger_file_discovery",
            session_id=str(session_id),
            session_dir=str(session_dir),
            all_files_count=len(schema_files),
            all_files=schema_files[:10] if len(schema_files) <= 10 else f"{schema_files[:10]}... ({len(schema_files)} total)",
        )

        schema_paths = [f for f in schema_files if f.endswith(".schema.json")]

        logger.debug(
            "session_merger_schema_filter",
            session_id=str(session_id),
            schema_files_found=len(schema_paths),
            schema_paths=schema_paths,
        )

        if not schema_paths:
            logger.info(
                "no_schemas_found",
                session_id=str(session_id),
                message="No schema files to merge",
            )
            return ProcessingResult(
                session_id=session_id,
                sequence_number=1,
                operation="session_merge",
                success=True,
                duration_ms=0,
                metadata={"schema_count": 0, "message": "No schemas to merge"},
            )

        logger.info(
            "schemas_discovered",
            session_id=str(session_id),
            schema_count=len(schema_paths),
        )

        # Stage 2: Load schemas and prepare for merging
        schemas: list[tuple[FormSchema, datetime, str]] = []

        for schema_path in schema_paths:
            try:
                logger.debug(
                    "session_merger_loading_schema",
                    session_id=str(session_id),
                    schema_path=schema_path,
                )

                # Read schema file
                schema_content = await storage.read_file(schema_path)

                logger.debug(
                    "session_merger_schema_content_read",
                    session_id=str(session_id),
                    schema_path=schema_path,
                    content_size=len(schema_content),
                    content_preview=schema_content[:200] if len(schema_content) > 200 else schema_content,
                )

                schema_dict = FormSchema.model_validate_json(schema_content)

                logger.debug(
                    "session_merger_schema_validated",
                    session_id=str(session_id),
                    schema_path=schema_path,
                    form_name=schema_dict.form_name.value,
                    page_identifier=schema_dict.page_identifier.value,
                    section_count=len(schema_dict.sections),
                )

                # Get file metadata for timestamp
                # For now, use current time - in production could use file mtime
                timestamp = datetime.now()

                # Use file name as version ID
                version_id = Path(schema_path).stem

                schemas.append((schema_dict, timestamp, version_id))

            except Exception as e:
                logger.warning(
                    "schema_load_failed",
                    schema_path=schema_path,
                    error_type=type(e).__name__,
                    error=str(e),
                    exc_info=True,
                )
                continue

        if not schemas:
            logger.warning(
                "no_valid_schemas",
                session_id=str(session_id),
                message="All schema files failed to load",
            )
            return ProcessingResult(
                session_id=session_id,
                sequence_number=1,
                operation="session_merge",
                success=False,
                duration_ms=(time.time() - start_time) * 1000,
                error_message="All schema files failed to load",
            )

        # Stage 3: Create orchestrator and merge
        # Use in-memory orchestration for cloud storage
        from src.services.merging.page_matcher import PageMatcher
        from src.services.merging.schema_merger import SchemaMerger

        page_matcher = PageMatcher(
            form_similarity_threshold=form_similarity_threshold,
            page_similarity_threshold=page_similarity_threshold,
            debug_dir=debug_dir,
        )
        schema_merger = SchemaMerger(retention_days=retention_days, debug_dir=debug_dir)

        # Group schemas by page
        schema_objects = [s[0] for s in schemas]

        logger.debug(
            "session_merger_grouping_schemas",
            session_id=str(session_id),
            schema_count=len(schema_objects),
            schema_identifiers=[s.page_identifier.value for s in schema_objects],
        )

        page_groups = page_matcher.group_schemas_by_page(schema_objects)

        logger.info(
            "schemas_grouped",
            session_id=str(session_id),
            source_count=len(schemas),
            page_groups=len(page_groups),
            page_group_keys=list(page_groups.keys()),
        )

        for page_id, group_schemas in page_groups.items():
            logger.debug(
                "session_merger_page_group",
                session_id=str(session_id),
                page_id=page_id,
                schema_count=len(group_schemas),
                form_names=[s.form_name.value for s in group_schemas],
            )

        # Merge within each group
        merged_schemas: dict[str, FormSchema] = {}

        for page_id, group_schemas in page_groups.items():
            logger.debug(
                "session_merger_merging_group",
                session_id=str(session_id),
                page_id=page_id,
                group_size=len(group_schemas),
            )

            # Find matching schema versions for this group
            group_versions = [
                (schema, timestamp, version_id)
                for schema, timestamp, version_id in schemas
                if schema in group_schemas
            ]

            logger.debug(
                "session_merger_group_versions",
                session_id=str(session_id),
                page_id=page_id,
                version_count=len(group_versions),
                version_ids=[v[2] for v in group_versions],
            )

            # Merge using SchemaMerger
            merged_schema = schema_merger.merge_pydantic_models(group_versions)
            merged_schemas[page_id] = merged_schema

            logger.debug(
                "session_merger_group_merged",
                session_id=str(session_id),
                page_id=page_id,
                merged_form_name=merged_schema.form_name.value,
                merged_section_count=len(merged_schema.sections),
                merged_field_count=sum(len(section.fields) for section in merged_schema.sections),
            )

        # Stage 4: Save merged schemas to merged/ subfolder
        merged_dir = session_dir / "merged"
        saved_count = 0

        logger.debug(
            "session_merger_saving_schemas",
            session_id=str(session_id),
            merged_dir=str(merged_dir),
            schema_count=len(merged_schemas),
        )

        for page_id, schema in merged_schemas.items():
            try:
                # Generate a unique GUID for this merged group
                group_guid = str(uuid4())

                logger.debug(
                    "session_merger_saving_schema",
                    session_id=str(session_id),
                    page_id=page_id,
                    group_guid=group_guid,
                )

                # Convert to JSON
                schema_json = schema.model_dump_json(indent=2)

                # Save to merged/ subfolder with GUID filename
                merged_path = str(merged_dir / f"{group_guid}.json")

                logger.debug(
                    "session_merger_writing_file",
                    session_id=str(session_id),
                    page_id=page_id,
                    group_guid=group_guid,
                    merged_path=merged_path,
                    content_size=len(schema_json),
                )

                await storage.write_file(merged_path, schema_json.encode("utf-8"))

                saved_count += 1

                logger.info(
                    "merged_schema_saved",
                    session_id=str(session_id),
                    page_id=page_id,
                    group_guid=group_guid,
                    merged_path=merged_path,
                    field_count=sum(
                        len(section.fields) for section in schema.sections
                    ),
                )

            except Exception as e:
                logger.error(
                    "merged_schema_save_failed",
                    session_id=str(session_id),
                    page_id=page_id,
                    error_type=type(e).__name__,
                    error=str(e),
                    exc_info=True,
                )
                # Continue with other schemas

        # Stage 5: Calculate duration and return result
        duration_ms = (time.time() - start_time) * 1000

        result = ProcessingResult(
            session_id=session_id,
            sequence_number=1,
            operation="session_merge",
            success=True,
            duration_ms=duration_ms,
            metadata={
                "source_schema_count": len(schemas),
                "page_groups_count": len(page_groups),
                "merged_schemas_saved": saved_count,
                "form_similarity_threshold": form_similarity_threshold,
                "page_similarity_threshold": page_similarity_threshold,
                "retention_days": retention_days,
                "merged_directory": str(merged_dir),
            },
        )

        logger.info(
            "session_merge_complete",
            session_id=str(session_id),
            success=True,
            duration_ms=duration_ms,
            source_count=len(schemas),
            page_groups=len(page_groups),
            merged_saved=saved_count,
        )

        return result

    except Exception as e:
        # Calculate duration even on failure
        duration_ms = (time.time() - start_time) * 1000

        logger.error(
            "session_merge_failed",
            session_id=str(session_id),
            error_type=type(e).__name__,
            error_message=str(e),
            duration_ms=duration_ms,
            exc_info=True,
        )

        return ProcessingResult(
            session_id=session_id,
            sequence_number=1,
            operation="session_merge",
            success=False,
            duration_ms=duration_ms,
            error_type=type(e).__name__,
            error_message=str(e),
        )
